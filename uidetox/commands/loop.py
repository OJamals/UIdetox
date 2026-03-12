"""Loop command: bootstraps the autonomous UIdetox remediation cycle.

Flow (fully autonomous, self-propagating):

  1. SCAN CODEBASE -> generate score (static + subjective)
  2. TARGET SCORE? -> YES: finish | NO: continue
  3. AUTOPILOT: execute automated commands (check --fix, rescan, scan,
     skills, subagent prompts) via subprocess pipeline.
  4. POST-EXECUTION CHECKPOINT: reload state and decide:
     a. Target reached              → ``uidetox finish``
     b. Automated commands changed  → re-enter with fresh context
        state (rescan found issues,
        check --fix resolved some)
     c. Agent must apply manual     → print step-by-step directive
        fixes (queue has issues       and exit, letting the agent
        the agent must hand-fix)      work then re-invoke ``uidetox loop``

The agent NEVER needs to decide which command to run. The loop tells
it exactly what to do. Self-propagation happens because the agent
directive always ends with ``uidetox loop`` re-entry.
"""

import argparse
from datetime import datetime
import pathlib
import re
import shlex
import subprocess
import sys
import uuid

from ..state import (
    load_config, save_config, load_state,
    save_checkpoint, get_recent_checkpoints, get_recent_errors,
    log_error, get_loop_progress, save_state,
)
from ..tooling import detect_all
from ..memory import get_patterns, get_notes, get_session, get_last_scan, log_progress
from ..utils import compute_design_score, get_score_freshness, now_iso
from ..skills import (
    recommend_skills_for_issues,
    recommend_review_skills,
    format_skill_recommendations,
    list_all_skills,
)
from ..gitnexus_cache import (
    set_iteration as _set_cache_iteration,
    cache_stats as _cache_stats,
    get_cached_result as _get_cached_gitnexus,
    cache_query_result as _cache_gitnexus,
)

# Maximum iterations to prevent infinite loops in edge cases
_MAX_LOOP_ITERATIONS = 20
_QUEUE_EMPTY_ONLY_TAG = "[queue-empty-only]"

# Circuit breaker thresholds
_MAX_CONSECUTIVE_SAME_SCORE = 5  # Stop if score doesn't change for N iterations
_MAX_ERROR_RATE = 10  # Stop if more than N errors in last 5 iterations
_RECOVERY_COOLDOWN = 3  # Wait N iterations before retrying after failure


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _issues_since(items: list[dict], opened_at: datetime | None) -> list[dict]:
    """Return issues created after the review follow-up window opened."""
    if opened_at is None:
        return list(items)
    selected: list[dict] = []
    for issue in items:
        created_at = _parse_iso(issue.get("created_at"))
        if created_at is None:
            created_at = _parse_iso(issue.get("resolved_at"))
        if created_at is not None and created_at >= opened_at:
            selected.append(issue)
    return selected


def _activate_review_followup_window(state: dict) -> dict:
    """Mark that a review pass started and must be followed by implementation."""
    subjective = state.setdefault("subjective", {})
    followup = subjective.get("review_followup")
    if isinstance(followup, dict) and followup.get("active"):
        return followup

    marker = {
        "active": True,
        "opened_at": now_iso(),
        "completed_at": None,
        "closed_reason": None,
    }
    subjective["review_followup"] = marker
    save_state(state)
    return marker


def _review_followup_snapshot(state: dict) -> dict:
    """Inspect/maintain the post-review implementation gate."""
    subjective = state.get("subjective", {})
    followup = subjective.get("review_followup")
    if not isinstance(followup, dict) or not followup.get("active"):
        return {
            "active": False,
            "score_recorded": False,
            "pending_count": 0,
            "resolved_count": 0,
            "opened_at": None,
        }

    opened_at_raw = str(followup.get("opened_at", "")).strip() or None
    opened_at = _parse_iso(opened_at_raw)
    reviewed_at = _parse_iso(subjective.get("reviewed_at"))
    score_recorded = bool(reviewed_at is not None and opened_at is not None and reviewed_at >= opened_at)

    pending_followup = _issues_since(state.get("issues", []), opened_at)
    resolved_followup = _issues_since(state.get("resolved", []), opened_at)

    # Auto-close the gate once review score is recorded and follow-up
    # issues created during the review window are fully resolved.
    if score_recorded and not pending_followup and resolved_followup:
        followup["active"] = False
        followup["completed_at"] = now_iso()
        followup["closed_reason"] = "followup_issues_resolved"
        subjective["review_followup"] = followup
        state["subjective"] = subjective
        save_state(state)
        return {
            "active": False,
            "score_recorded": score_recorded,
            "pending_count": 0,
            "resolved_count": len(resolved_followup),
            "opened_at": opened_at_raw,
            "just_closed": True,
        }

    # Score was recorded but no review-window issues were ever queued/resolved.
    # Keep the gate active to prevent the loop from launching another review
    # without implementing review findings.
    if score_recorded and not pending_followup and not resolved_followup:
        return {
            "active": True,
            "score_recorded": True,
            "pending_count": 0,
            "resolved_count": 0,
            "opened_at": opened_at_raw,
            "awaiting_implementation": True,
        }

    return {
        "active": True,
        "score_recorded": score_recorded,
        "pending_count": len(pending_followup),
        "resolved_count": len(resolved_followup),
        "opened_at": opened_at_raw,
    }


def _resolve_gitnexus_repo(config: dict) -> str | None:
    """Resolve GitNexus repo name for CLI commands in multi-index environments."""
    configured = str(config.get("gitnexus_repo", "")).strip()
    if configured:
        return configured

    try:
        status = subprocess.run(
            ["npx", "gitnexus", "status"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if status.returncode == 0:
            for line in status.stdout.splitlines():
                if line.startswith("Repository:"):
                    repo_path = line.split(":", 1)[1].strip()
                    if repo_path:
                        name = pathlib.Path(repo_path).name.strip()
                        if name:
                            return name
    except Exception:
        pass

    try:
        return pathlib.Path.cwd().resolve().name.strip() or None
    except Exception:
        return None


def _gitnexus_cmd(subcommand: str, arg: str, repo: str | None) -> str:
    """Build GitNexus CLI command with explicit repo when supported."""
    base = f"npx gitnexus {subcommand}"
    if repo and subcommand in {"query", "context", "impact", "cypher"}:
        base += f" -r {shlex.quote(repo)}"
    if arg:
        base += f" {arg}"
    return base


def _parse_multi_repo_error(output: str) -> list[str]:
    """Parse available repo names from GitNexus multi-repo error output."""
    if not output:
        return []
    m = re.search(r'Available:\s*([^\n\r]+)', output)
    if not m:
        return []
    raw = m.group(1)
    names = [part.strip().strip('"').strip("'") for part in raw.split(",")]
    return [name for name in names if name]


def _select_repo_from_candidates(candidates: list[str], preferred: str | None = None) -> str | None:
    """Choose the best repo from candidates, preferring explicit/current project names."""
    if not candidates:
        return None
    preferred_clean = str(preferred or "").strip()
    if preferred_clean:
        for candidate in candidates:
            if candidate == preferred_clean:
                return candidate

    cwd_name = pathlib.Path.cwd().resolve().name
    for candidate in candidates:
        if candidate == cwd_name:
            return candidate

    return candidates[0]


def _gitnexus_cmd_with_repo(parts: list[str], repo: str) -> list[str]:
    """Inject `-r <repo>` into an `npx gitnexus ...` argv when missing."""
    if len(parts) < 3:
        return parts
    if parts[0] not in {"npx", "bunx", "node"} or parts[1] != "gitnexus":
        return parts
    if "-r" in parts or "--repo" in parts:
        return parts

    # npx gitnexus <subcommand> -r <repo> <args...>
    return [*parts[:3], "-r", repo, *parts[3:]]


def run(args: argparse.Namespace):
    target = getattr(args, "target", 95)
    is_manual = getattr(args, "manual", False)
    max_commands = getattr(args, "max_commands", 50)
    dry_run = getattr(args, "dry_run", False)
    iteration = getattr(args, "_iteration", 0)  # internal: loop re-entry counter

    # Iterative loop replaces the previous recursive run() re-entry.
    # Each pass through the while-True body is one autonomous iteration.
    while True:
        _run_iteration(
            target=target,
            is_manual=is_manual,
            max_commands=max_commands,
            dry_run=dry_run,
            iteration=iteration,
            args=args,
        )
        # _run_iteration stashes a "should_continue" flag on args when
        # the post-execution checkpoint determines the loop should re-enter.
        if getattr(args, "_continue", False):
            args._continue = False  # type: ignore[attr-defined]
            iteration += 1
            continue
        break


def _run_iteration(
    *,
    target: int,
    is_manual: bool,
    max_commands: int,
    dry_run: bool,
    iteration: int,
    args: argparse.Namespace,
) -> None:
    """Execute one full iteration of the autonomous loop."""

    # ---- Auto-detect tooling ----
    config = load_config()
    if not config.get("tooling"):
        print("Auto-detecting project tooling...")
        profile = detect_all()
        config["tooling"] = profile.to_dict()
        save_config(config)

    # Store target in config for scan to reference
    config["target_score"] = target
    save_config(config)

    state = load_state()
    issues = state.get("issues", [])
    resolved = len(state.get("resolved", []))
    tooling = config.get("tooling", {})
    has_mechanical = tooling.get("typescript") or tooling.get("linter") or tooling.get("formatter")

    # ---- Codebase sizing (cached across loop iterations) ----
    frontend_count = getattr(args, "_frontend_count", None)
    if frontend_count is None:
        frontend_exts = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".css", ".scss", ".sass"}
        exclude_dirs = {"node_modules", ".git", "dist", "build", ".next", "out", ".uidetox"}
        frontend_count = 0
        for p in pathlib.Path('.').rglob('*'):
            if p.is_file() and p.suffix in frontend_exts and not (set(p.parts) & exclude_dirs):
                frontend_count += 1
        args._frontend_count = frontend_count  # type: ignore[attr-defined]
    unique_files = len(set(i.get("file", "") for i in issues))
    spread = unique_files if unique_files > 0 else (frontend_count // 5)
    auto_parallel = max(1, min(5, spread))
    is_orchestrator = bool(getattr(args, "orchestrator", True))
    gitnexus_repo = _resolve_gitnexus_repo(config)
    if gitnexus_repo and str(config.get("gitnexus_repo", "")).strip() != gitnexus_repo:
        config["gitnexus_repo"] = gitnexus_repo
        save_config(config)

    # ---- GitNexus codebase indexing (early — before any analysis) ----
    # Advance the GitNexus cache iteration so stale entries are pruned.
    _set_cache_iteration(iteration)
    stats = _cache_stats()
    if stats["total_entries"] > 0:
        print(f"  GitNexus cache: {stats['total_entries']} entries (iter {stats['iteration']})")

    # Run as pre-phase so the call graph is fresh for all downstream
    # commands (observe, diagnose, review, impact analysis, etc.).
    # Non-fatal: if npx/gitnexus aren't installed, we silently continue.
    print("  Refreshing GitNexus codebase index...")
    rc = _exec_cmd("npx gitnexus analyze", "pre-phase codebase indexing", dry_run=dry_run)
    if rc != 0:
        print("  ℹ  GitNexus not available or index refresh failed — continuing without it.")
    elif gitnexus_repo:
        print(f"  GitNexus repo target: {gitnexus_repo}")
    print()

    # ---- Git workspace isolation ----
    if config.get("auto_commit"):
        _ensure_session_branch()

    # ---- Compute current scores ----
    scores = compute_design_score(state)
    blended = scores["blended_score"]
    if blended is None:
        blended = 0
    queue_size = len(issues)
    review_followup = _review_followup_snapshot(state)

    # ---- Header ----
    print()
    print("=" * 60)
    print("  UIdetox Autonomous Loop")
    print("=" * 60)
    print(f"  Target: {target}  |  Score: {blended}  |  Queue: {queue_size}  |  Resolved: {resolved}")
    # Show score breakdown so agent understands the curve
    raw_sub = scores.get("subjective_score")
    eff_sub = scores.get("effective_subjective")
    obj_s = scores.get("objective_score")
    score_parts = []
    if obj_s is not None:
        score_parts.append(f"obj={obj_s}")
    if eff_sub is not None and raw_sub is not None and eff_sub != raw_sub:
        score_parts.append(f"sub={eff_sub}eff (raw {raw_sub}, Δ-{raw_sub - eff_sub})")
    elif raw_sub is not None:
        score_parts.append(f"sub={raw_sub}")
    if score_parts:
        print(f"  Score breakdown: {' | '.join(score_parts)}")
    print(f"  Files: {frontend_count}  |  Orchestrator: {'ON' if is_orchestrator else 'off'}")
    print(f"  Mode: {'AUTOPILOT' if not is_manual else 'MANUAL'}  |  Iteration: {iteration + 1}")
    if review_followup["active"]:
        print("  Post-review gate: ACTIVE")
        if review_followup["score_recorded"]:
            print(
                f"    Review score recorded; follow-up pending issues: {review_followup['pending_count']} "
                f"(resolved: {review_followup['resolved_count']})"
            )
        else:
            print("    Waiting for subjective review score + queued follow-up issues.")
    print()

    # If review prompts were already emitted, the loop must not skip
    # directly to another discovery cycle. Enforce review -> implement.
    if review_followup["active"] and not review_followup["score_recorded"]:
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  REVIEW GATE — COMPLETE SUBJECTIVE REVIEW FIRST     ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print("  A review pass is in progress. Finish it before continuing:")
        print("    1. Queue all issues discovered by the review.")
        print("    2. Run `uidetox check --fix`.")
        print("    3. Record score: `uidetox review --score <N>`.")
        print("    4. Run `uidetox loop` again (it will force implementation of review findings).")
        print()
        return

    if (
        review_followup["active"]
        and review_followup["score_recorded"]
        and review_followup["pending_count"] == 0
        and review_followup["resolved_count"] == 0
        and blended < target
    ):
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  REVIEW GATE — IMPLEMENT FINDINGS BEFORE RE-REVIEW  ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print("  Review score was recorded, but no review-window issues were queued.")
        print("  The loop will NOT launch another subjective review yet.")
        print()
        print("  Required next actions:")
        print("    1. Queue every concrete finding from the completed review:")
        print('       uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
        print("    2. Run `uidetox loop` to enter the fix phase.")
        print("    3. Resolve all queued review findings via `uidetox batch-resolve ...`.")
        print("    4. Re-run `uidetox loop` (only then will a fresh review be allowed).")
        print()
        return

    # ---- IMMEDIATE TERMINATION CHECK ----
    freshness = get_score_freshness(state)
    if blended >= target and queue_size == 0 and freshness["target_ready"]:
        print("  ✅ TARGET REACHED — Score {blended} >= {target}, Queue EMPTY.".format(blended=blended, target=target))
        print("  Finishing session...")
        _exec_cmd("uidetox finish", "target reached — finishing session", dry_run=dry_run)
        log_progress("loop_complete", f"target={target}, score={blended}, iterations={iteration + 1}")
        return
    elif blended >= target and queue_size == 0:
        print("  ⚠️  High score detected, but finish is blocked because the score is stale.")
        for reason in freshness.get("reasons", [])[:2]:
            print(f"     - {reason}")
        print("  Re-running analysis/review before allowing finish.")
        print()

    # ---- ITERATION GUARD ----
    if iteration >= _MAX_LOOP_ITERATIONS:
        print(f"  ⚠️  Max loop iterations ({_MAX_LOOP_ITERATIONS}) reached.")
        print(f"  Score: {blended}, Queue: {queue_size}")
        print("  Run `uidetox status` to review, then `uidetox loop` to resume.")
        log_progress("loop_max_iterations", f"score={blended}, queue={queue_size}")
        log_error("loop_max_iterations", f"Max iterations reached", {
            "iteration": iteration,
            "score": blended,
            "queue": queue_size,
        })
        return

    # ---- SAVE CHECKPOINT ----
    save_checkpoint(iteration, blended, queue_size, f"Iteration {iteration + 1}")

    # ---- CIRCUIT BREAKER: Score Stagnation ----
    recent_checkpoints = get_recent_checkpoints(limit=_MAX_CONSECUTIVE_SAME_SCORE + 1)
    if len(recent_checkpoints) >= _MAX_CONSECUTIVE_SAME_SCORE:
        recent_scores = [cp.get("score", 0) for cp in recent_checkpoints[-_MAX_CONSECUTIVE_SAME_SCORE:]]
        if len(set(recent_scores)) == 1 and recent_scores[0] < target:
            print(f"  ╔══════════════════════════════════════════════════════╗")
            print(f"  ║  🛑 CIRCUIT BREAKER: Score Stagnation Detected       ║")
            print(f"  ╚══════════════════════════════════════════════════════╝")
            print(f"  Score stuck at {recent_scores[0]} for {_MAX_CONSECUTIVE_SAME_SCORE} iterations.")
            print(f"  This indicates the current approach is not making progress.")
            print()
            print("  RECOVERY ACTIONS:")
            print("    1. Review the lowest-scoring subjective review domains")
            print("    2. Read reference/*.md files for deeper improvement criteria")
            print("    3. Consider a different fix strategy (not just cosmetic tweaks)")
            print("    4. Run `uidetox status` to see detailed breakdown")
            print("    5. Run `uidetox loop` to resume after making changes")
            print()
            log_progress("circuit_breaker_stagnation", f"score={recent_scores[0]}, iterations={iteration + 1}")
            log_error("circuit_breaker", "Score stagnation detected", {
                "score": recent_scores[0],
                "iterations": _MAX_CONSECUTIVE_SAME_SCORE,
                "total_iterations": iteration + 1,
            })
            return

    # ---- CIRCUIT BREAKER: High Error Rate ----
    recent_errors = get_recent_errors(limit=10)
    recent_loop_errors = [e for e in recent_errors if e.get("type", "").startswith(("loop_", "circuit_breaker", "check_fix"))]
    if len(recent_loop_errors) >= _MAX_ERROR_RATE:
        print(f"  ╔══════════════════════════════════════════════════════╗")
        print(f"  ║  🛑 CIRCUIT BREAKER: High Error Rate Detected        ║")
        print(f"  ╚══════════════════════════════════════════════════════╝")
        print(f"  {len(recent_loop_errors)} errors in recent iterations.")
        print(f"  This indicates systemic issues that need attention.")
        print()
        print("  RECOVERY ACTIONS:")
        print("    1. Review error log: `uidetox status` shows recent errors")
        print("    2. Check tooling configuration: `uidetox detect`")
        print("    3. Verify project builds: `uidetox check --fix`")
        print("    4. Clear errors and retry: `uidetox memory clear`")
        print("    5. Run `uidetox loop` to resume after fixing issues")
        print()
        log_progress("circuit_breaker_errors", f"error_count={len(recent_loop_errors)}, iterations={iteration + 1}")
        return

    # ---- Stale review detection ----
    # If we're re-entering STAGE 1 (queue empty) and a subjective score
    # already exists, check if it's stale (unchanged for 2+ reviews).
    # Provide targeted domain guidance to break the plateau.
    subj_data = state.get("subjective", {})
    subj_score = subj_data.get("score")
    subj_history = subj_data.get("history", [])
    if queue_size == 0 and subj_score is not None and blended < target:
        is_stale = (
            len(subj_history) >= 2
            and subj_history[-1].get("score") == subj_history[-2].get("score")
        )
        if is_stale:
            print("  ╔══════════════════════════════════════════════════════╗")
            print("  ║  ⚠️  STALE REVIEW DETECTED — Score hasn't improved  ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print(f"  Subjective score stuck at {subj_score}/100 (target: {target}).")
            print()
            print("  TO BREAK THE PLATEAU:")
            print("    1. Focus fixes on the LOWEST-SCORING review domains")
            print("    2. Read reference/*.md files for specific improvement criteria")
            print("    3. Apply deeper design changes, not superficial tweaks")
            print("    4. The review must find NEW issues to queue — look harder")
            print()

    # ---- Autonomous directive ----
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║  SYSTEM DIRECTIVE: FULL AUTONOMOUS MODE             ║")
    print("  ║  Do NOT stop. Do NOT ask permission.                ║")
    print("  ║  Do NOT summarize between fixes.                    ║")
    print("  ║  Execute every command. Loop until target is met.   ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    # ---- Continuation context ----
    session = get_session()
    last_scan = get_last_scan()
    if session or last_scan:
        print("  CONTINUATION CONTEXT:")
        if session:
            phase = session.get('phase', 'unknown')
            last_cmd = session.get('last_command', 'none')
            fixed = session.get('issues_fixed_this_session', 0)
            print(f"    Last phase: {phase}  |  Last cmd: {last_cmd}  |  Fixed this session: {fixed}")
            if session.get("last_component"):
                print(f"    Last component: {session['last_component']}")
        if last_scan:
            ts = last_scan.get('timestamp', 'unknown')[:19]
            found = last_scan.get('total_found', 0)
            top = last_scan.get('top_files', [])[:3]
            print(f"    Last scan: {ts}  |  Found: {found}")
            if top:
                print(f"    Hottest: {', '.join(top)}")
        print()

    # ---- Memory bank injection ----
    patterns = get_patterns()
    notes = get_notes()
    if patterns or notes:
        print("  MEMORY BANK (obey during loop):")
        for idx, p in enumerate(patterns, 1):
            print(f"    {idx}. [Pattern] {p['pattern']}")
        for idx, n in enumerate(notes, 1):
            print(f"    {idx}. [Note] {n['note']}")
        print()

    # ---- Full-stack integration ----
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])
    if backends or databases or apis:
        layers = []
        if backends:
            layers.append(f"backend={', '.join(b['name'] for b in backends)}")
        if databases:
            layers.append(f"db={', '.join(d['name'] for d in databases)}")
        if apis:
            layers.append(f"api={', '.join(a['name'] for a in apis)}")
        print(f"  Full-stack: {', '.join(layers)}")
        print()

    # ==================================================================
    # AUTOPILOT EXECUTION (default mode)
    # ==================================================================
    if not is_manual:
        plan = _build_autopilot_plan(
            issues=issues,
            config=config,
            has_mechanical=bool(has_mechanical),
            blended=blended,
            target=target,
            is_orchestrator=is_orchestrator,
            auto_parallel=auto_parallel,
            queue_size=queue_size,
            tooling=tooling,
            gitnexus_repo=gitnexus_repo,
        )

        print("=" * 60)
        print("  AUTOPILOT COMMAND PLAN")
        print("=" * 60)
        _print_autopilot_plan(plan)

        if dry_run:
            print("\n  [DRY RUN] No commands executed.")
        else:
            # Snapshot pre-execution state for change detection
            pre_queue = queue_size
            pre_resolved = resolved

            halt_stage = _run_autopilot_plan(
                plan,
                max_commands=max_commands,
                gitnexus_repo=gitnexus_repo,
            )

            # ---- POST-EXECUTION CHECKPOINT ----
            _post_execution_checkpoint(
                args=args,
                target=target,
                iteration=iteration,
                dry_run=dry_run,
                pre_queue=pre_queue,
                pre_resolved=pre_resolved,
                subagent_halt_stage=halt_stage,
            )

        # Log the loop invocation
        log_progress("loop_autopilot", f"target={target}, score={blended}, queue={queue_size}, iteration={iteration + 1}")
        return

    # ==================================================================
    # MANUAL MODE (--manual flag): print full protocol for human agents
    # ==================================================================
    _print_manual_protocol(
        issues=issues,
        config=config,
        has_mechanical=has_mechanical,
        is_orchestrator=is_orchestrator,
        auto_parallel=auto_parallel,
        blended=blended,
        target=target,
        session=session,
        last_scan=last_scan,
    )
    log_progress("loop_manual", f"target={target}, score={blended}, queue={queue_size}")


def _post_execution_checkpoint(
    *,
    args: argparse.Namespace,
    target: int,
    iteration: int,
    dry_run: bool,
    pre_queue: int,
    pre_resolved: int,
    subagent_halt_stage: str | None = None,
) -> None:
    """Reload state after autopilot execution and decide continuation strategy.

    Three outcomes:
    1. Target reached → run ``uidetox finish`` and exit.
    2. Automated commands changed state (e.g. check --fix resolved issues,
       rescan found new ones) → re-enter the loop ONE more time so the
       agent gets an updated context dump.
    3. State unchanged → the agent needs to apply manual fixes. Print an
       explicit step-by-step directive and exit so the agent can work.

    This replaces the old recursive ``_self_propagate`` which blindly
    re-entered the loop even when nothing had changed, causing the agent
    to spin without making progress.
    """
    # ── Post-fix GitNexus change detection ──
    # Verify that the automated commands only affected expected files
    # and symbols.  Non-fatal — skips if GitNexus isn't available.
    if not dry_run:
        print("  Verifying change scope via GitNexus...")
        rc = _exec_cmd(
            "npx gitnexus detect_changes",
            "post-execution scope check",
            dry_run=dry_run,
        )
        if rc != 0:
            print("  ℹ  GitNexus change detection unavailable — continuing.")
        print()

    # Reload fresh state after commands executed
    state = load_state()
    scores = compute_design_score(state)
    blended = scores["blended_score"]
    if blended is None:
        blended = 0
    queue_size = len(state.get("issues", []))
    resolved_total = len(state.get("resolved", []))

    print()
    print("─" * 60)
    print("  LOOP CHECKPOINT")
    print("─" * 60)
    filled = max(0, blended // 5)
    bar = "█" * filled + "░" * (20 - filled)
    print(f"  Score: [{bar}] {blended}/100  (target: {target})")
    # Score breakdown for agent curve awareness
    raw_sub = scores.get("subjective_score")
    eff_sub = scores.get("effective_subjective")
    obj_s = scores.get("objective_score")
    if eff_sub is not None and raw_sub is not None and eff_sub != raw_sub:
        print(f"  Breakdown: obj={obj_s} | sub={eff_sub}eff (raw {raw_sub}, Δ-{raw_sub - eff_sub})")
    elif raw_sub is not None and obj_s is not None:
        print(f"  Breakdown: obj={obj_s} | sub={raw_sub}")
    print(f"  Queue: {queue_size} pending  |  {resolved_total} resolved")

    # ── OUTCOME 1: Target reached ──
    freshness = get_score_freshness(state)
    if blended >= target and queue_size == 0 and freshness["target_ready"]:
        print()
        print("  ✅ TARGET REACHED. Finishing session...")
        _exec_cmd("uidetox finish", "target reached", dry_run=dry_run)
        return
    elif blended >= target and queue_size == 0:
        print()
        print("  ⚠️  Score is above target, but finish is blocked until analysis/review are fresh.")
        for reason in freshness.get("reasons", [])[:2]:
            print(f"     - {reason}")

    state_changed = (queue_size != pre_queue) or (resolved_total != pre_resolved)
    can_recurse = iteration + 1 < _MAX_LOOP_ITERATIONS

    # ── OUTCOME 2: Autopilot halted on an agent-action command ──
    # These MUST be handled BEFORE the state-changed auto-continuation
    # because the agent needs to act on the printed prompts/context
    # regardless of whether state changed.  Without this ordering the
    # review and fix directives were swallowed by auto-continuation,
    # causing the agent to spin without executing them.

    if subagent_halt_stage == "next":
        # ``next`` already printed the full batch context, skill rules,
        # design dials, and [AGENT INSTRUCTION] steps.  The agent must
        # now fix ALL issues in that batch before re-entering the loop.
        if queue_size == 0:
            # Queue was drained by check --fix — move to discovery/review
            if can_recurse:
                print()
                print("  ⟳  Queue drained — continuing to discovery + review phase...")
                print()
                args._continue = True  # type: ignore[attr-defined]
                return
        else:
            print()
            print("  ╔══════════════════════════════════════════════════════╗")
            print("  ║  AGENT DIRECTIVE — FIX THE BATCH SHOWN ABOVE       ║")
            print("  ║  `uidetox next` printed the issues + instructions.  ║")
            print("  ║  Follow the [AGENT INSTRUCTION] steps above.        ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print()
            print(f"  {queue_size} issue(s) pending. The batch above is your focus.")
            print()
            print("  STEPS (already shown by `next`, reinforced here):")
            print("    1. Run GitNexus impact analysis on batch targets")
            print("       (context + impact commands shown in the batch output above)")
            print("    2. Read the listed files")
            print("    3. Fix ALL issues in the batch in ONE pass")
            print("    4. uidetox check --fix")
            print("    5. npx gitnexus detect_changes  (verify only expected files changed)")
            print('    6. uidetox batch-resolve <IDs> --note "what you changed"')
            print("    7. uidetox loop")
            print()
            print("  DO NOT run format/lint separately — `check --fix` does tsc→lint→format.")
            print("  DO NOT run `uidetox next` again — the batch is already shown above.")
            print("  Fix ALL issues in the batch, not just one file.")
            print()
            return

    if subagent_halt_stage == "review":
        from uidetox.subagent import (
            REVIEW_DOMAINS,
            SCORED_REVIEW_DOMAINS,
            REVIEW_WAVE_1,
            REVIEW_WAVE_2,
            PERFECTION_GATE,
        )
        total_max = sum(d.get("max_score", 0) for d in SCORED_REVIEW_DOMAINS)
        followup_marker = _activate_review_followup_window(state)

        # Check for existing objective issues already in the queue
        # (from rescan/scan/audit that ran BEFORE the review)
        obj_issues_note = ""
        if queue_size > 0:
            obj_issues_note = (
                f"\n  NOTE: {queue_size} objective issue(s) are already in the queue"
                f"\n  from the static analysis phase. These will be fixed in STAGE 2"
                f"\n  after you complete this review and re-enter the loop.\n"
            )

        # Check for stale reviews (score unchanged)
        subj_hist = state.get("subjective", {}).get("history", [])
        stale_warning = ""
        if (
            len(subj_hist) >= 2
            and subj_hist[-1].get("score") == subj_hist[-2].get("score")
        ):
            prev_score = subj_hist[-1].get("score", "?")
            stale_warning = (
                f"\n  ⚠️  STALE REVIEW WARNING: Score stuck at {prev_score}/100."
                f"\n  You MUST find NEW issues this time. Focus on the lowest-scoring"
                f"\n  domains and apply deeper design changes, not superficial tweaks.\n"
            )

        print()
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  AGENT DIRECTIVE — EXECUTE SUBJECTIVE REVIEW NOW    ║")
        print("  ║  The review prompts are printed above.              ║")
        print("  ║  You MUST perform the review, not just read them.   ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print(f"  Review follow-up window opened: {followup_marker.get('opened_at')}")
        if obj_issues_note:
            print(obj_issues_note)
        if stale_warning:
            print(stale_warning)
        print()
        print(f"  The subjective score is 70% of the blended Design Score.")
        print(
            f"  {len(SCORED_REVIEW_DOMAINS)} scored domains + "
            f"{'Perfection Gate' if PERFECTION_GATE else 'no gate'}, {total_max} total points."
        )
        print(f"  Wave split: {len(REVIEW_WAVE_1)} domain(s) in Wave 1, {len(REVIEW_WAVE_2)} in Wave 2.")
        print()
        print("  EXECUTE THESE STEPS IN ORDER:")
        print()
        print("    1. READ every reference file listed in the review prompts above.")
        print("       These are the scoring authority:")
        for ref in sorted(set(r for d in REVIEW_DOMAINS for r in d.get("references", []))):
            print(f"         - {ref}")
        print()
        print("    2. READ every frontend file in the codebase.")
        print("       Use `npx gitnexus query \"frontend components\"` to discover them.")
        print()
        print("    3. SCORE each scored domain using the rubric in the prompts above:")
        for d in SCORED_REVIEW_DOMAINS:
            wave = d.get('wave', '?')
            print(f"         Wave {wave}: {d['label']} (0-{d.get('max_score', '?')})")
        print()
        print("       For each domain:")
        print("         a. Start at the max score")
        print("         b. Walk the checklist — mark each item PASS or FAIL")
        print("         c. Measure every hard threshold — cite actual values")
        print("         d. Apply every matching automatic deduction")
        print("         e. Final score = max - deductions (clamped to [0, max])")
        print()
        print("    4. QUEUE every issue found during review:")
        print('       uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
        print()
        print("    5. Run:  uidetox check --fix")
        print("       → Ensure code is clean before scoring.")
        print()
        print(f"    6. COMPUTE your combined score (sum all domains, normalize to 0-100):")
        print(f"       Raw total: <sum>/{total_max} → Normalized: <0-100>")
        print()
        print("    7. RECORD the score:")
        print("       uidetox review --score <NORMALIZED_SCORE>")
        print()
        print("    8. Run:  uidetox loop")
        print("       → Re-enters the loop.")
        print("       → The loop WILL enforce implementation of all issues queued in this review window.")
        print("       → Only after that can the review gate close.")
        print()
        print("  DO NOT SKIP THE REVIEW. DO NOT just record a score without evaluating.")
        print("  READ the files. SCORE the domains. QUEUE the issues. THEN re-enter.")
        print()
        if not can_recurse:
            print(f"  ⚠️  Max iterations reached ({_MAX_LOOP_ITERATIONS}).")
            print("  The loop will resume from here when you run `uidetox loop`.")
            print()
        return

    if subagent_halt_stage == "fix":
        print()
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  AGENT DIRECTIVE — EXECUTE FIX PROMPTS NOW          ║")
        print("  ║  The fix prompts are printed above.                 ║")
        print("  ║  You MUST apply the fixes, not just read them.      ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print(f"  {queue_size} issue(s) pending across the fix shards above.")
        print()
        print("  EXECUTE THESE STEPS IN ORDER:")
        print()
        print("    1. For EACH fix shard prompt above:")
        print("       a. Read the target files listed")
        print("       b. Apply ALL fixes following SKILL.md rules and design dials")
        print("       c. Follow the deconfliction rules (only edit your shard's files)")
        print()
        print("    2. Run:  uidetox check --fix")
        print("       → MUST pass (tsc → lint → format) BEFORE committing.")
        print()
        print('    3. Run:  uidetox batch-resolve <IDs> --note "what you changed"')
        print("       → Marks issues resolved. ONLY after check --fix passes.")
        print()
        print("    4. Run:  uidetox loop")
        print("       → Re-enters the loop with fresh state.")
        print()
        print("  DO NOT SKIP. Apply fixes now, then re-enter the loop.")
        print()
        if not can_recurse:
            print(f"  ⚠️  Max iterations reached ({_MAX_LOOP_ITERATIONS}).")
            print("  The loop will resume from here when you run `uidetox loop`.")
            print()
        return

    # ── OUTCOME 3: Automated commands changed state → refresh context ──
    # This is checked AFTER halt-stage handling so that agent directives
    # are never swallowed by auto-continuation.
    if state_changed and can_recurse:
        print()
        print("  ⟳  State changed (automated commands did work). Refreshing context...")
        print()
        args._continue = True  # type: ignore[attr-defined]
        return

    # ── OUTCOME 4: Standard agent directive (no halt, no state change) ──
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║  AGENT DIRECTIVE — Apply fixes, then re-enter loop  ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

    if queue_size > 0:
        # Issues in queue — agent needs to fix them
        print(f"  {queue_size} issue(s) pending. Follow these steps IN ORDER:")
        print()
        print("    1. Run:  uidetox next")
        print("       → Shows the highest-priority batch with full context + skill rules.")
        print("       → Includes GitNexus impact analysis commands — RUN THEM.")
        print()
        print("    2. Run GitNexus impact analysis on the batch targets:")
        print("       npx gitnexus context \"<component>\"  — callers, callees, execution flows")
        print("       npx gitnexus impact \"<symbol>\" --direction upstream  — blast radius")
        print()
        print("    3. Read the target files and apply ALL fixes in one pass.")
        print("       Obey SKILL.md rules and design dials shown in the output.")
        print()
        print("    4. Run:  uidetox check --fix")
        print("       → Runs tsc → lint → format. Do NOT run these separately.")
        print()
        print("    5. Run:  npx gitnexus detect_changes")
        print("       → Verify only expected files/symbols were modified.")
        print()
        print('    6. Run:  uidetox batch-resolve <IDs> --note "what you changed"')
        print("       → Marks issues resolved, auto-commits if enabled.")
        print("       → ONLY run after check --fix passes.")
        print()
        print("    7. Run:  uidetox loop")
        print("       → Re-enters the autonomous loop with fresh state.")
        print("       → Repeats until target score is reached.")
    else:
        # Queue empty but score below target — needs subjective review
        from uidetox.subagent import SCORED_REVIEW_DOMAINS
        total_max = sum(d.get("max_score", 0) for d in SCORED_REVIEW_DOMAINS)
        print(f"  Queue is empty but score ({blended}) < target ({target}).")
        print(f"  The subjective review (70% weight) must be performed.")
        print()
        print("    1. Run GitNexus codebase analysis FIRST (enriches review context):")
        print('       npx gitnexus query "component page route layout view"')
        print('       npx gitnexus query "shared utility hook context provider store"')
        print('       npx gitnexus query "import dependency coupling circular"')
        print("       → Gives you architectural awareness for the scoring phase.")
        print()
        review_parallel = len(SCORED_REVIEW_DOMAINS)
        print(f"    2. Run:  uidetox subagent --stage-prompt review --parallel {review_parallel}")
        print(
            f"       → Generates domain-sharded review prompts "
            f"({review_parallel} scored domains + perfection gate)."
        )
        print("       → READ the prompts and EXECUTE the review (see above for full protocol).")
        print()
        print("    3. READ every frontend file and SCORE each domain using the rubric.")
        print("       For each domain: start at max → checklist → thresholds → deductions.")
        print()
        print("    4. QUEUE every issue found:")
        print('       uidetox add-issue --file <path> --tier <T1-T4> --issue "..." --fix-command "..."')
        print()
        print("    5. Run:  uidetox check --fix")
        print("       → Ensure code is clean before scoring.")
        print()
        print(f"    6. COMPUTE and RECORD the combined score (0-{total_max} → normalized 0-100):")
        print("       uidetox review --score <NORMALIZED_SCORE>")
        print()
        print("    7. Run:  uidetox loop")
        print("       → Re-enters with fresh state. Fixes queued issues, then re-reviews.")

    if not can_recurse:
        print()
        print(f"  ⚠️  Max iterations reached ({_MAX_LOOP_ITERATIONS}).")
        print("  The loop will resume from here when you run `uidetox loop`.")

    print()
    print("  DO NOT STOP. DO NOT ask permission. Execute these steps immediately.")
    print()


def _exec_cmd(cmd: str, reason: str, *, dry_run: bool = False) -> int:
    """Execute a single uidetox command. Returns the process exit code."""
    if dry_run:
        print(f"  [DRY RUN] {cmd}  ({reason})")
        return 0
    parts = shlex.split(cmd)
    if parts and parts[0] == "uidetox":
        parts = [sys.executable, "-m", "uidetox.cli", *parts[1:]]
    try:
        proc = subprocess.run(parts, text=True)
        return proc.returncode
    except Exception as e:
        print(f"  ⚠️  Command failed: {e}")
        return 1


def _persist_git_session(*, active_branch: str, base_branch: str | None = None) -> None:
    """Persist session-branch metadata for deterministic finish targets."""
    try:
        config = load_config()
        existing = config.get("git_session", {})
        if not isinstance(existing, dict):
            existing = {}

        resolved_base = str(base_branch or existing.get("base_branch", "")).strip()
        config["git_session"] = {
            "active_branch": active_branch,
            "base_branch": resolved_base,
        }
        save_config(config)
    except Exception:
        # Branch metadata is helpful but non-critical to loop execution.
        pass


def _ensure_session_branch():
    """Create or resume a UIdetox session branch for workspace isolation."""
    try:
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        if not current.startswith("uidetox-session-"):
            base_branch = current
            session_id = uuid.uuid4().hex[:12]
            branch = f"uidetox-session-{session_id}"
            print(f"  Git: switching to session branch {branch}")
            subprocess.run(["git", "checkout", "-b", branch], check=True,
                           capture_output=True)
            _persist_git_session(active_branch=branch, base_branch=base_branch)
        else:
            print(f"  Git: resuming session branch {current}")
            _persist_git_session(active_branch=current)
    except subprocess.CalledProcessError:
        print("  Git: not initialized or branching failed. Proceeding without isolation.")


def _derive_target_path(issues: list[dict]) -> str:
    """Pick a practical target path for skill invocation.

    Uses the highest-priority issue's directory when available; otherwise '.'.
    """
    tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
    if not issues:
        return "."
    sorted_issues = sorted(issues, key=lambda x: tiers_order.get(x.get("tier", "T4"), 5))
    top_file = sorted_issues[0].get("file")
    if not top_file:
        return "."
    return str(pathlib.Path(top_file).parent or ".")


def _collect_batch_target_files(issues: list[dict]) -> list[str]:
    """Identify the files for the next fix batch (mirrors next.py batching logic).

    Returns a list of file paths that the next ``uidetox next`` invocation
    will target — used to run pre-fix GitNexus impact analysis.
    """
    tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
    if not issues:
        return []
    sorted_issues = sorted(issues, key=lambda x: tiers_order.get(x.get("tier", "T4"), 5))
    target_file = sorted_issues[0].get("file")
    if not target_file:
        return []
    target_dir = str(pathlib.Path(target_file).parent)
    batch = [
        i for i in sorted_issues
        if str(pathlib.Path(i.get("file", "")).parent) == target_dir
    ][:15]
    return list(dict.fromkeys(i.get("file", "") for i in batch if i.get("file")))


def _build_autopilot_plan(
    *,
    issues: list[dict],
    config: dict,
    has_mechanical: bool,
    blended: int,
    target: int,
    is_orchestrator: bool,
    auto_parallel: int,
    queue_size: int | None = None,
    tooling: dict | None = None,
    gitnexus_repo: str | None = None,
) -> list[tuple[str, str]]:
    """Build an ordered command plan for autonomous loop execution.

    Returns a list of (command, reason).
    The plan is comprehensive: it covers a full scan→fix→verify cycle
    so the agent never has to decide what to run next.
    """
    if queue_size is None:
        queue_size = len(issues)
    if tooling is None:
        tooling = config.get("tooling", {})
    freshness = get_score_freshness(load_state())
    is_fullstack = bool(
        tooling.get("backend") or tooling.get("database") or tooling.get("api")
    )
    target_path = _derive_target_path(issues)
    plan: list[tuple[str, str]] = []

    # ──────────────────────────────────────────────────────────────
    # STAGE 1 / REDISCOVERY (queue empty, score below target)
    # ──────────────────────────────────────────────────────────────
    if queue_size == 0:
        # ── Pre-analysis mechanical gate ──
        if has_mechanical:
            plan.append(("uidetox check --fix", "clear mechanical issues before deeper analysis"))

        # ── GitNexus codebase intelligence (enriches agent context) ──
        # Run BEFORE rescan/audit so the agent has architectural
        # awareness when interpreting static analysis results.
        plan.append((
            _gitnexus_cmd("query", '"component page route layout view"', gitnexus_repo),
            "codebase analysis: map frontend component architecture via call graph",
        ))
        plan.append((
            _gitnexus_cmd("query", '"shared utility hook context provider store"', gitnexus_repo),
            "codebase analysis: map shared infrastructure and state management",
        ))
        plan.append((
            _gitnexus_cmd("query", '"export default function interface type"', gitnexus_repo),
            "impact mapping: identify public API surfaces for blast-radius awareness",
        ))

        plan.append(("uidetox rescan --path .", "refresh issue queue from latest code"))

        # Contract + UX-state validation (deterministic gates)
        plan.append(("uidetox scan --path .", "contract validation + UX-state coverage check"))

        # Run audit for comprehensive analysis
        plan.append(("uidetox audit .", "comprehensive quality audit (a11y, perf, theming, responsive)"))

        # Orchestrator observation pass
        if is_orchestrator and auto_parallel > 1:
            plan.append((
                f"uidetox subagent --stage-prompt observe --parallel {auto_parallel}",
                "orchestrator: parallel file observation",
            ))
            plan.append((
                "uidetox subagent --stage-prompt diagnose",
                "orchestrator: diagnosis from observations",
            ))

        # Review-phase skill commands
        review_recs = recommend_review_skills(
            config=config,
            issues_remaining=0,
            blended_score=blended,
        )
        for rec in review_recs[:3]:
            plan.append((f"uidetox {rec['skill']} .", f"review skill: {rec.get('reason', 'recommended')}"))

        # ── Parallel domain-sharded subjective review ──
        # The subjective score carries 70% weight in the blended Design Score.
        # Use scored domains for shard count; perfection gate has max_score=0.
        from uidetox.subagent import SCORED_REVIEW_DOMAINS, REVIEW_WAVE_1, REVIEW_WAVE_2
        review_parallel = len(SCORED_REVIEW_DOMAINS)
        plan.append((
            f"uidetox subagent --stage-prompt review --parallel {review_parallel}",
            (
                "parallel domain-sharded subjective review "
                f"({review_parallel} scored domains; wave1={len(REVIEW_WAVE_1)}, "
                f"wave2={len(REVIEW_WAVE_2)}, 70% of blended score)"
            ),
        ))

        # ── Full-stack cross-layer validation (only for full-stack projects) ──
        if is_fullstack:
            plan.append((
                _gitnexus_cmd("query", '"API endpoint route handler DTO"', gitnexus_repo),
                "full-stack gate: map backend surface for cross-layer validation",
            ))
            plan.append((
                _gitnexus_cmd("query", '"fetch request mutation query"', gitnexus_repo),
                "full-stack gate: map frontend data-fetching surfaces",
            ))
            plan.append((
                _gitnexus_cmd("query", '"validation constraint required schema"', gitnexus_repo),
                "full-stack gate: map validation rules for frontend↔backend alignment",
            ))
            plan.append((
                _gitnexus_cmd("query", '"error status code exception boundary"', gitnexus_repo),
                "full-stack gate: map error-handling surfaces across layers",
            ))

        # ── Codebase coupling & impact snapshot ──
        # Gives the agent awareness of tightly-coupled modules so the
        # review and fix phases can prioritize high-impact areas.
        plan.append((
            _gitnexus_cmd("query", '"import dependency coupling circular"', gitnexus_repo),
            "dependency analysis: detect tightly-coupled modules for targeted fixes",
        ))

        plan.append(("uidetox status", "check blended score and queue after domain reviews"))

        # ── Post-review: parallel implementation subagents for new issues ──
        # Scale implementation subagents with scored review shard count.
        fix_parallel = max(1, min(len(SCORED_REVIEW_DOMAINS), max(auto_parallel, len(SCORED_REVIEW_DOMAINS))))
        if is_orchestrator:
            plan.append((
                f"uidetox subagent --stage-prompt fix --parallel {fix_parallel}",
                f"parallel implementation subagents ({fix_parallel} shards) for review-discovered issues",
            ))

        # ── Post-fix verification ──
        plan.append(("uidetox status", "check blended score and queue"))

        if blended >= target and freshness["target_ready"]:
            plan.append(("uidetox finish", "target reached with empty queue"))
        return plan

    # ──────────────────────────────────────────────────────────────
    # STAGE 2 / FIX LOOP (queue has issues)
    # ──────────────────────────────────────────────────────────────
    #
    # Intentionally focused: mechanical gate + impact analysis + next.
    # ``next`` already outputs the full batch context, skill
    # recommendations, design dials, and [AGENT INSTRUCTION] steps.
    # The autopilot halts after ``next`` so the agent can focus on
    # fixing ONE batch, then re-enters the loop for the next batch.
    #
    # GitNexus queries run BEFORE next to give the agent dependency
    # and impact awareness for the files it is about to modify.
    #
    # Discovery (rescan) and subjective review run in STAGE 1 once
    # the queue is drained.  This ensures the agent does focused
    # fix work in STAGE 2 without distractions.

    # Pre-fix mechanical gate — auto-fix lint/format/tsc ONCE
    if has_mechanical:
        plan.append(("uidetox check --fix", "mechanical quality gate — auto-fix lint/format before manual fixes"))

    # ── GitNexus pre-fix impact analysis ──
    # Query the call graph for the batch's target files so the agent
    # knows which callers / shared utilities may be affected before
    # it starts editing.  Results are cached per iteration.
    batch_files = _collect_batch_target_files(issues)
    if batch_files:
        # Query context for the primary target component
        primary = batch_files[0]
        plan.append((
            _gitnexus_cmd("context", f'"{primary}"', gitnexus_repo),
            f"pre-fix context: trace callers/callees for {primary}",
        ))
        # Impact analysis on the primary symbol
        plan.append((
            _gitnexus_cmd("impact", f'"{primary}" --direction upstream', gitnexus_repo),
            f"pre-fix impact: blast radius check for {primary}",
        ))

    # Full-stack alignment check for the batch being fixed
    if is_fullstack and batch_files:
        plan.append((
            _gitnexus_cmd("query", '"fetch request mutation query"', gitnexus_repo),
            "pre-fix full-stack: verify data-fetching alignment before modifying components",
        ))

    # Context dump — prints batch issues, skill rules, design dials,
    # and full [AGENT INSTRUCTION] steps.  Autopilot halts here.
    plan.append(("uidetox next", "prioritized batch with full context — agent must fix ALL issues shown, then re-enter loop"))

    return plan


def _print_autopilot_plan(plan: list[tuple[str, str]]) -> None:
    """Pretty-print the autopilot command plan."""
    if not plan:
        print("  No autopilot actions generated.")
        return
    print(f"  {len(plan)} command(s) queued for autonomous execution:")
    print()
    for idx, (cmd, reason) in enumerate(plan, 1):
        queue_empty_only = reason.startswith(_QUEUE_EMPTY_ONLY_TAG)
        display_reason = reason
        if queue_empty_only:
            display_reason = reason.replace(_QUEUE_EMPTY_ONLY_TAG, "", 1).strip()
            display_reason += " [runs only when queue is empty at runtime]"
        print(f"    {idx:2d}. {cmd}")
        print(f"        └─ {display_reason}")
    print()
    print("  NOTE: After these commands dump context, you will receive a")
    print("  step-by-step AGENT DIRECTIVE telling you exactly what to fix")
    print("  and which commands to run next. Follow it precisely.")


def _run_autopilot_plan(
    plan: list[tuple[str, str]],
    *,
    max_commands: int = 50,
    gitnexus_repo: str | None = None,
) -> str | None:
    """Execute autopilot commands in order with failure-aware continuation.

    Commands fall into two categories:
    - **State-changing**: ``check --fix``, ``rescan``, ``scan`` — these actually
      modify the project or issue queue.  Fatal errors halt the pipeline.
    - **Context-injecting**: ``next``, ``review``, ``status``, ``finish``,
      skill commands, ``subagent`` — these print information for the agent.
      Non-zero exits are informational signals, not failures.
    - **Agent-action**: ``subagent --stage-prompt review``, ``subagent --stage-prompt fix``
      — these print prompts that the agent MUST execute.  The autopilot halts
      after printing them so the agent can act on the prompts before the loop
      continues.

    Returns the subagent stage name (``"review"`` or ``"fix"``) if the plan
    halted on an agent-action command, or ``None`` if the plan ran to completion.
    """
    if not plan:
        return None

    effective = plan[: max(1, max_commands)]
    print(f"\n  ▶ Executing {len(effective)} command(s)...")
    print()

    # Commands whose non-zero exit is a signal, not a fatal error
    _signal_commands = {"next", "review", "status", "finish", "subagent", "gitnexus"}
    # External tool prefixes (npx, node, etc.) — non-zero exit is never fatal
    _external_prefixes = {"npx", "node", "bunx"}
    # Per-command timeout (seconds) — prevents infinite hangs
    _CMD_TIMEOUT = 300  # 5 minutes per command (generous for large projects)
    _LONG_CMD_TIMEOUT = 600  # 10 minutes for known-slow commands
    _slow_commands = {"subagent", "check", "scan", "rescan", "audit"}

    consecutive_failures = 0
    _MAX_CONSECUTIVE_FAILURES = 3  # Bail after 3 consecutive fatal failures

    for idx, (cmd, reason) in enumerate(effective, 1):
        print(f"  [{idx}/{len(effective)}] {cmd}")
        print(f"      └─ {reason}")

        if reason.startswith(_QUEUE_EMPTY_ONLY_TAG):
            live_queue = len(load_state().get("issues", []))
            if live_queue > 0:
                print(f"      ↷ Skipping queue-empty-only step ({live_queue} issue(s) pending).")
                print()
                continue

        parts = shlex.split(cmd)
        if not parts:
            continue

        # ── Detect subagent review/fix commands that need agent action ──
        # These commands print prompts the agent MUST execute.  After
        # running them, halt the autopilot so the checkpoint can instruct
        # the agent to act on the printed prompts.
        _is_subagent_action = (
            len(parts) >= 4
            and parts[0] == "uidetox"
            and parts[1] == "subagent"
            and "--stage-prompt" in parts
        )
        _subagent_action_stage: str | None = None
        if _is_subagent_action:
            try:
                sp_idx = parts.index("--stage-prompt")
                _subagent_action_stage = parts[sp_idx + 1] if sp_idx + 1 < len(parts) else None
            except (ValueError, IndexError):
                pass

        is_external = parts[0] in _external_prefixes

        # Cache expensive GitNexus graph calls to avoid repeated query/context/impact
        # invocations within an iteration and improve deterministic behavior.
        is_gitnexus_cacheable = (
            len(parts) >= 3
            and parts[0] in _external_prefixes
            and parts[1] == "gitnexus"
            and parts[2] in {"query", "context", "impact"}
        )
        gitnexus_kind = parts[2] if is_gitnexus_cacheable else ""
        gitnexus_payload = " ".join(parts[3:]) if is_gitnexus_cacheable else ""
        if is_gitnexus_cacheable:
            cached = _get_cached_gitnexus(gitnexus_payload, kind=gitnexus_kind)
            if cached is not None:
                print(f"      ♻️  Cache hit: gitnexus {gitnexus_kind} ({gitnexus_payload[:80]})")
                if isinstance(cached, dict):
                    out = str(cached.get("stdout", "") or "").strip()
                    if out:
                        preview = "\n".join(out.splitlines()[:40])
                        print(preview)
                        if len(out.splitlines()) > 40:
                            print("      … (cached output truncated)")
                print()
                continue

        # Detect which uidetox subcommand this is (or external tool name)
        cmd_name = parts[1] if len(parts) > 1 and parts[0] == "uidetox" else parts[0]

        # Choose timeout based on command type
        timeout = _LONG_CMD_TIMEOUT if cmd_name in _slow_commands else _CMD_TIMEOUT

        # Skill commands (dynamic skills) are also context-injecting
        is_skill = cmd_name not in {
            "check", "rescan", "scan", "next", "review", "status",
            "finish", "subagent", "batch-resolve", "resolve", "loop",
            "detect", "tsc", "lint", "format", "autofix",
        }

        if parts[0] == "uidetox":
            parts = [sys.executable, "-m", "uidetox.cli", *parts[1:]]

        try:
            if is_gitnexus_cacheable:
                proc = subprocess.run(parts, text=True, timeout=timeout, capture_output=True)
                combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
                if combined:
                    preview = "\n".join(combined.splitlines()[:60])
                    print(preview)
                    if len(combined.splitlines()) > 60:
                        print("      … (output truncated)")
                if proc.returncode == 0:
                    _cache_gitnexus(
                        gitnexus_payload,
                        {
                            "stdout": proc.stdout,
                            "stderr": proc.stderr,
                            "command": cmd,
                        },
                        kind=gitnexus_kind,
                    )
            else:
                proc = subprocess.run(parts, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"      ⏰ Command timed out after {timeout}s — skipping.")
            log_error("loop_autopilot_cmd_timeout", "Autopilot command timed out", {
                "command": cmd,
                "reason": reason,
                "timeout": timeout,
                "cmd_name": cmd_name,
            })
            continue
        except Exception as e:
            print(f"      ⚠️  Command exception: {e}")
            log_error("loop_autopilot_cmd_exception", "Autopilot command raised exception", {
                "command": cmd,
                "reason": reason,
                "cmd_name": cmd_name,
                "error": str(e),
            })
            continue

        if proc.returncode != 0:
            # Self-heal for multi-repo GitNexus setups:
            # retry once with explicit `-r <repo>` if command omitted repo.
            if is_external and len(parts) >= 3 and parts[0] in _external_prefixes and parts[1] == "gitnexus":
                output = ""
                if is_gitnexus_cacheable:
                    output = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
                candidates = _parse_multi_repo_error(output)
                selected_repo = _select_repo_from_candidates(candidates, gitnexus_repo)
                retriable = bool(selected_repo and "-r" not in parts and "--repo" not in parts)
                if retriable:
                    retry_parts = _gitnexus_cmd_with_repo(parts, selected_repo)
                    print(f"      ↻ Retrying GitNexus with explicit repo: {selected_repo}")
                    try:
                        if is_gitnexus_cacheable:
                            retry_proc = subprocess.run(
                                retry_parts,
                                text=True,
                                timeout=timeout,
                                capture_output=True,
                            )
                            combined = ((retry_proc.stdout or "") + (retry_proc.stderr or "")).strip()
                            if combined:
                                preview = "\n".join(combined.splitlines()[:60])
                                print(preview)
                                if len(combined.splitlines()) > 60:
                                    print("      … (output truncated)")
                        else:
                            retry_proc = subprocess.run(retry_parts, text=True, timeout=timeout)
                    except Exception as retry_exc:
                        print(f"      ⚠️  GitNexus retry failed: {retry_exc}")
                    else:
                        if retry_proc.returncode == 0:
                            proc = retry_proc
                            if is_gitnexus_cacheable:
                                _cache_gitnexus(
                                    gitnexus_payload,
                                    {
                                        "stdout": retry_proc.stdout,
                                        "stderr": retry_proc.stderr,
                                        "command": " ".join(retry_parts),
                                    },
                                    kind=gitnexus_kind,
                                )
                        else:
                            proc = retry_proc

            if proc.returncode == 0:
                consecutive_failures = 0
                print()
                # Continue with halt checks below.
                if _subagent_action_stage in ("review", "fix"):
                    remaining = len(effective) - idx
                    if remaining > 0:
                        print(f"  ⏸  Autopilot paused — {remaining} command(s) deferred.")
                        print(f"      The agent must execute the {_subagent_action_stage.upper()} prompts above")
                        print(f"      before the loop can continue.  Re-enter with `uidetox loop`.")
                        print()
                    return _subagent_action_stage
                if cmd_name == "next":
                    remaining = len(effective) - idx
                    if remaining > 0:
                        print(f"  ⏸  Autopilot paused — fix the batch above, then re-enter with `uidetox loop`.")
                        print()
                    return "next"
                continue

            if cmd_name in _signal_commands or is_skill or is_external:
                print(f"      ℹ  Signal exit ({proc.returncode}) — continuing.")
                log_error("loop_autopilot_signal_exit", "Autopilot signal exit", {
                    "command": cmd,
                    "reason": reason,
                    "cmd_name": cmd_name,
                    "returncode": proc.returncode,
                })
                consecutive_failures = 0  # Reset: signal exits aren't real failures
            else:
                consecutive_failures += 1
                print(f"\n  ⚠️  Command failed (exit {proc.returncode}).")
                log_error("loop_autopilot_cmd_failed", "Autopilot fatal command failed", {
                    "command": cmd,
                    "reason": reason,
                    "cmd_name": cmd_name,
                    "returncode": proc.returncode,
                    "consecutive_failures": consecutive_failures,
                })
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    print(f"  ❌ {_MAX_CONSECUTIVE_FAILURES} consecutive failures — halting pipeline.")
                    print(f"  [SELF-HEAL] Fix the errors above, then run `uidetox loop`.")
                    break
                print(f"  [SELF-HEAL] Fix the error above, then run `uidetox loop`.")
                print(f"  The loop will self-propagate from where it left off.")
                break
        else:
            consecutive_failures = 0  # Reset on success

        print()

        # ── Halt after agent-action commands ──
        # These commands print context/prompts the agent MUST execute.
        # Halt the autopilot so the checkpoint can instruct the agent.

        # Subagent review/fix: prompts the agent must act on
        if _subagent_action_stage in ("review", "fix"):
            remaining = len(effective) - idx
            if remaining > 0:
                print(f"  ⏸  Autopilot paused — {remaining} command(s) deferred.")
                print(f"      The agent must execute the {_subagent_action_stage.upper()} prompts above")
                print(f"      before the loop can continue.  Re-enter with `uidetox loop`.")
                print()
            return _subagent_action_stage

        # ``next``: the batch context + fix instructions were just printed.
        # Halt so the agent focuses on fixing THIS batch before moving on.
        if cmd_name == "next" and proc.returncode == 0:
            remaining = len(effective) - idx
            if remaining > 0:
                print(f"  ⏸  Autopilot paused — fix the batch above, then re-enter with `uidetox loop`.")
                print()
            return "next"

    return None


def _print_manual_protocol(
    *,
    issues: list[dict],
    config: dict,
    has_mechanical: bool,
    is_orchestrator: bool,
    auto_parallel: int,
    blended: int,
    target: int,
    session: dict | None,
    last_scan: dict | None,
) -> None:
    """Print the full manual loop protocol (only used with --manual flag)."""
    queue_size = len(issues)

    print("=" * 60)
    print("  THE LOOP PROTOCOL (MANUAL MODE)")
    print("=" * 60)
    print()

    # ---- STAGE 1 ----
    print("  STAGE 1: SCAN CODEBASE")
    print("  " + "-" * 40)
    print("    1a. Run `npx gitnexus analyze`  (index codebase — run FIRST, takes ~10-30s)")
    print("    1b. Run `npx gitnexus query \"frontend components\"` (map codebase)")
    if has_mechanical:
        print("    1c. Run `uidetox check --fix`  (tsc -> lint -> format)")
    print("    1d. Run `uidetox scan --path .`")
    print("    1e. Run `uidetox audit .`  (comprehensive quality audit)")
    if is_orchestrator:
        print(f"    1f. `uidetox subagent --stage-prompt observe --parallel {auto_parallel}`")
        print(f"        `uidetox subagent --stage-prompt diagnose`")
    print()

    # ---- STAGE 2 ----
    print("  STAGE 2: FIX LOOP (repeat until queue empty)")
    print("  " + "-" * 40)
    print("    2a. `uidetox next`              — get batch + skills")
    print("    2b. Apply fixes following SKILL.md rules")
    print("    2c. `uidetox check --fix`       — tsc/lint/format BEFORE commit")
    print("    2d. `uidetox batch-resolve IDs --note '...'`")
    print("    2e. `uidetox status`            — check score")
    print("    Loop back to 2a until queue is empty.")
    print()

    # ---- STAGE 3 ----
    from uidetox.subagent import SCORED_REVIEW_DOMAINS, REVIEW_WAVE_1, REVIEW_WAVE_2
    review_parallel = len(SCORED_REVIEW_DOMAINS)
    print("  STAGE 3: RE-SCAN & POLISH")
    print("  " + "-" * 40)
    print("    3a. `npx gitnexus analyze`      — refresh codebase index")
    print("    3b. `uidetox rescan`            — fresh analysis")
    print("    3c. `uidetox critique .`        — design review")
    print("    3d. `uidetox polish .`          — final pass")
    print(f"    3e. `uidetox subagent --stage-prompt review --parallel {review_parallel}`")
    print(
        f"        → Spawns {review_parallel} parallel scored-domain review subagents "
        f"(wave1={len(REVIEW_WAVE_1)}, wave2={len(REVIEW_WAVE_2)}):"
    )
    print("          Wave 1: " + ", ".join(d["name"] for d in REVIEW_WAVE_1))
    print("          Wave 2: " + ", ".join(d["name"] for d in REVIEW_WAVE_2))
    print("    3f. `uidetox check --fix`       — tsc/lint/format before scoring")
    print("    3g. `uidetox review --score N`  — record combined score")
    print("    3h. `uidetox status`            — check blended score (30% obj + 70% subj)")
    print(f"    3i. Score >= {target}? → `uidetox finish`")
    print()

    # ---- Skill recommendations ----
    if issues:
        fix_recs = recommend_skills_for_issues(issues, config=config, phase="fix")
        if fix_recs:
            print("  ━━━ RECOMMENDED SKILLS ━━━")
            formatted = format_skill_recommendations(fix_recs, indent="    ", target="<path>")
            if formatted:
                print(formatted)

    # ---- Quick reference ----
    all_skills = list_all_skills()
    print(f"  Skills ({len(all_skills)} available):")
    for i in range(0, len(all_skills), 6):
        chunk = all_skills[i:i+6]
        print(f"    {', '.join(chunk)}")
    print()

    # ---- START HERE ----
    print("=" * 60)
    print("  START HERE")
    print("=" * 60)

    if blended >= target and queue_size == 0:
        print(f"  Score: {blended} (>= {target}), Queue: EMPTY → `uidetox finish`")
    elif queue_size == 0:
        print(f"  Score: {blended} (< {target}), Queue: EMPTY → `uidetox rescan`")
    elif queue_size > 0:
        print(f"  Score: {blended}, Queue: {queue_size} → `uidetox next`")
    else:
        print("  → `uidetox scan --path .`")
    print()
