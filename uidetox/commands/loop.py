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
import pathlib
import shlex
import subprocess
import sys
import uuid

from ..state import load_config, save_config, load_state
from ..tooling import detect_all
from ..memory import get_patterns, get_notes, get_session, get_last_scan, log_progress
from ..utils import compute_design_score
from ..skills import (
    recommend_skills_for_issues,
    recommend_review_skills,
    format_skill_recommendations,
    list_all_skills,
)
from ..gitnexus_cache import (
    set_iteration as _set_cache_iteration,
    cache_stats as _cache_stats,
)

# Maximum iterations to prevent infinite loops in edge cases
_MAX_LOOP_ITERATIONS = 20
_QUEUE_EMPTY_ONLY_TAG = "[queue-empty-only]"


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

    # ---- Codebase sizing ----
    frontend_exts = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".css", ".scss", ".sass"}
    exclude_dirs = {"node_modules", ".git", "dist", "build", ".next", "out", ".uidetox"}
    frontend_count = 0
    for p in pathlib.Path('.').rglob('*'):
        if p.is_file() and p.suffix in frontend_exts and not (set(p.parts) & exclude_dirs):
            frontend_count += 1
    unique_files = len(set(i.get("file", "") for i in issues))
    spread = unique_files if unique_files > 0 else (frontend_count // 5)
    auto_parallel = max(1, min(5, spread))
    is_orchestrator = bool(getattr(args, "orchestrator", True))

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

    # ---- Header ----
    print()
    print("=" * 60)
    print("  UIdetox Autonomous Loop")
    print("=" * 60)
    print(f"  Target: {target}  |  Score: {blended}  |  Queue: {queue_size}  |  Resolved: {resolved}")
    print(f"  Files: {frontend_count}  |  Orchestrator: {'ON' if is_orchestrator else 'off'}")
    print(f"  Mode: {'AUTOPILOT' if not is_manual else 'MANUAL'}  |  Iteration: {iteration + 1}")
    print()

    # ---- IMMEDIATE TERMINATION CHECK ----
    if blended >= target and queue_size == 0:
        print("  ✅ TARGET REACHED — Score {blended} >= {target}, Queue EMPTY.".format(blended=blended, target=target))
        print("  Finishing session...")
        _exec_cmd("uidetox finish", "target reached — finishing session", dry_run=dry_run)
        log_progress("loop_complete", f"target={target}, score={blended}, iterations={iteration + 1}")
        return

    # ---- ITERATION GUARD ----
    if iteration >= _MAX_LOOP_ITERATIONS:
        print(f"  ⚠️  Max loop iterations ({_MAX_LOOP_ITERATIONS}) reached.")
        print(f"  Score: {blended}, Queue: {queue_size}")
        print("  Run `uidetox status` to review, then `uidetox loop` to resume.")
        log_progress("loop_max_iterations", f"score={blended}, queue={queue_size}")
        return

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

            _run_autopilot_plan(plan, max_commands=max_commands)

            # ---- POST-EXECUTION CHECKPOINT ----
            _post_execution_checkpoint(
                args=args,
                target=target,
                iteration=iteration,
                dry_run=dry_run,
                pre_queue=pre_queue,
                pre_resolved=pre_resolved,
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
    print(f"  Queue: {queue_size} pending  |  {resolved_total} resolved")

    # ── OUTCOME 1: Target reached ──
    if blended >= target and queue_size == 0:
        print()
        print("  ✅ TARGET REACHED. Finishing session...")
        _exec_cmd("uidetox finish", "target reached", dry_run=dry_run)
        return

    # ── OUTCOME 2: Automated commands changed state → refresh context ──
    state_changed = (queue_size != pre_queue) or (resolved_total != pre_resolved)
    can_recurse = iteration + 1 < _MAX_LOOP_ITERATIONS

    if state_changed and can_recurse:
        print()
        print("  ⟳  State changed (automated commands did work). Refreshing context...")
        print()
        # Signal the iterative loop in run() to continue rather than
        # recursively calling run() (which can stack-overflow and wastes memory).
        args._continue = True  # type: ignore[attr-defined]
        return

    # ── OUTCOME 3: Agent must apply manual fixes ──
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
        print()
        print("    2. Read the target files and apply ALL fixes in one pass.")
        print("       Obey SKILL.md rules and design dials shown in the output.")
        print()
        print("    3. Run:  uidetox check --fix")
        print("       → MUST pass (tsc → lint → format) BEFORE committing.")
        print()
        print('    4. Run:  uidetox batch-resolve <IDs> --note "what you changed"')
        print("       → Marks issues resolved, auto-commits if enabled.")
        print("       → ONLY run after check --fix passes.")
        print()
        print("    5. Run:  uidetox loop")
        print("       → Re-enters the autonomous loop with fresh state.")
        print("       → Repeats until target score is reached.")
    else:
        # Queue empty but score below target — needs review/rescan
        print(f"  Queue is empty but score ({blended}) < target ({target}).")
        print()
        print("    1. Run:  npx gitnexus query \"frontend components\"")
        print("       → Map the component graph before reviewing.")
        print()
        print("    2. Run:  uidetox check --fix")
        print("       → Ensure code is clean (tsc → lint → format) before scoring.")
        print()
        print("    3. Run:  uidetox review")
        print("       → Perform a subjective UX review and score the design.")
        print("       → (or `uidetox review --parallel 5` for domain-sharded review)")
        print()
        print("    4. Run:  uidetox review --score <N>")
        print("       → Record your subjective score (0-100).")
        print()
        print("    5. Queue any new issues found during review:")
        print('       uidetox add-issue --file <path> --tier <T1-T4> --issue "..." --fix-command "..."')
        print()
        print("    6. Run:  uidetox loop")
        print("       → Re-enters with fresh state. Rescans if queue remains empty.")

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


def _ensure_session_branch():
    """Create or resume a UIdetox session branch for workspace isolation."""
    try:
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        if not current.startswith("uidetox-session-"):
            session_id = uuid.uuid4().hex[:12]
            branch = f"uidetox-session-{session_id}"
            print(f"  Git: switching to session branch {branch}")
            subprocess.run(["git", "checkout", "-b", branch], check=True,
                           capture_output=True)
        else:
            print(f"  Git: resuming session branch {current}")
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

        # ── Parallel domain-sharded subjective review (10 domains, 2 waves of 5) ──
        # The subjective score carries 70% weight in the blended Design Score.
        # Spawn 10 parallel domain review subagents for maximum granularity:
        #   Wave 1 (5): typography, color, interaction, content, motion
        #   Wave 2 (5): spatial, materiality, consistency, identity, architecture
        from uidetox.subagent import REVIEW_DOMAINS, REVIEW_WAVE_1, REVIEW_WAVE_2
        review_parallel = len(REVIEW_DOMAINS)  # 10 domains = 10 shards
        plan.append((
            f"uidetox subagent --stage-prompt review --parallel {review_parallel}",
            f"parallel domain-sharded subjective review ({review_parallel} domains in 2 waves of 5, 70% of blended score)",
        ))

        # ── Full-stack cross-layer validation (only for full-stack projects) ──
        if is_fullstack:
            plan.append((
                'npx gitnexus query "API endpoint route handler DTO"',
                "full-stack gate: map backend surface for cross-layer validation",
            ))
            plan.append((
                'npx gitnexus query "fetch request mutation query"',
                "full-stack gate: map frontend data-fetching surfaces",
            ))

        # ── Pre-score verification gate ──
        if has_mechanical:
            plan.append(("uidetox check --fix", "lint/format/typecheck before scoring"))
        plan.append(("uidetox status", "check blended score and queue after domain reviews"))

        # ── Post-review: parallel implementation subagents for new issues ──
        # Spawn 2 waves of 5 fix subagents (10 total) matching the review
        # domain count.  Each wave handles issues from its corresponding
        # review domains.
        fix_parallel = max(1, min(10, max(auto_parallel, len(REVIEW_DOMAINS))))
        if is_orchestrator:
            plan.append((
                f"uidetox subagent --stage-prompt fix --parallel {fix_parallel}",
                f"parallel implementation subagents ({fix_parallel} shards, 2 waves of 5) for review-discovered issues",
            ))

        # ── Post-fix verification ──
        if has_mechanical:
            plan.append(("uidetox check --fix", "verify code is clean after implementation"))
        plan.append(("uidetox subagent --stage-prompt verify", "verification subagent: confirm improvements"))
        plan.append(("uidetox status", "check blended score and queue"))

        if blended >= target:
            plan.append(("uidetox finish", "target reached with empty queue"))
        return plan

    # ──────────────────────────────────────────────────────────────
    # STAGE 2 / FIX LOOP (queue has issues)
    # ──────────────────────────────────────────────────────────────

    # Pre-fix mechanical gate
    if has_mechanical:
        plan.append(("uidetox check --fix", "mechanical quality gate — auto-fix lint/format before manual fixes"))

    # Get next batch context (prints issue details + skill rules + design dials)
    plan.append(("uidetox next", "context dump: prioritized batch + skill recommendations + design dials"))

    # Skill commands matched to current issues (inject domain-specific rules)
    fix_recs = recommend_skills_for_issues(issues, config=config, phase="fix", limit=4)
    for rec in fix_recs:
        plan.append((
            f"uidetox {rec['skill']} {target_path}",
            f"skill context: {rec.get('reason', 'issue-matched')}",
        ))

    # Orchestrator: parallel fix prompts
    if is_orchestrator and auto_parallel > 1:
        plan.append((
            f"uidetox subagent --stage-prompt fix --parallel {auto_parallel}",
            "orchestrator: generate parallel fix prompts for sub-agents",
        ))

    # Status check for trajectory awareness
    plan.append(("uidetox status", "show current score + queue state for trajectory awareness"))

    # ── Additional context rounds for large queues ──
    # Each `uidetox next` prints the next component batch so the agent
    # has full awareness of everything that needs fixing.
    dirs_with_issues: set[str] = set()
    for iss in issues:
        f = iss.get("file", "")
        if f:
            dirs_with_issues.add(str(pathlib.Path(f).parent))

    extra_cycles = min(3, max(0, len(dirs_with_issues) - 1))
    for cycle in range(extra_cycles):
        plan.append(("uidetox next", f"context dump: batch {cycle + 2} of {len(dirs_with_issues)}"))

    # ── Full-stack cross-layer validation after fixes ──
    if is_fullstack:
        plan.append((
            "npx gitnexus detect_changes",
            "full-stack gate: verify changes only affect expected symbols",
        ))
        plan.append((
            'npx gitnexus query "DTO type interface schema"',
            "full-stack gate: verify frontend types still match backend DTOs after fixes",
        ))

    # ── Post-fix quality gate — MUST pass before committing ──
    if has_mechanical:
        plan.append(("uidetox check --fix", "quality gate: tsc → lint → format BEFORE any commit"))

    # Final rescan to discover deeper issues after fixes
    plan.append(("uidetox rescan --path .", "rescan after fix phase — discover deeper issues"))
    plan.append(("uidetox status", "post-rescan status — check score trajectory"))

    # ── Seamless objective→subjective transition ──
    # If the fix loop emptied the queue, immediately trigger subjective
    # review rather than requiring a full loop re-entry to reach Stage 1.
    # Use 10 parallel domain-sharded review subagents (2 waves of 5).
    from uidetox.subagent import REVIEW_DOMAINS
    review_parallel = len(REVIEW_DOMAINS)  # 10 domains
    if is_orchestrator:
        plan.append((
            f"uidetox subagent --stage-prompt review --parallel {review_parallel}",
            f"{_QUEUE_EMPTY_ONLY_TAG} seamless transition: parallel domain-sharded subjective review ({review_parallel} domains, 2 waves of 5, 70% weight)",
        ))
    else:
        plan.append(("uidetox review", f"{_QUEUE_EMPTY_ONLY_TAG} seamless transition: subjective review (70% weight)"))

    if has_mechanical:
        plan.append(("uidetox check --fix", f"{_QUEUE_EMPTY_ONLY_TAG} final quality gate before scoring"))
    plan.append(("uidetox status", f"{_QUEUE_EMPTY_ONLY_TAG} final score check — blended objective + subjective"))

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


def _run_autopilot_plan(plan: list[tuple[str, str]], *, max_commands: int = 50) -> None:
    """Execute autopilot commands in order with failure-aware continuation.

    Commands fall into two categories:
    - **State-changing**: ``check --fix``, ``rescan``, ``scan`` — these actually
      modify the project or issue queue.  Fatal errors halt the pipeline.
    - **Context-injecting**: ``next``, ``review``, ``status``, ``finish``,
      skill commands, ``subagent`` — these print information for the agent.
      Non-zero exits are informational signals, not failures.

    The plan runs all commands so the agent sees the full context dump
    in one terminal read.  After the plan completes, the caller's
    checkpoint logic decides whether to re-enter or hand off to the agent.
    """
    if not plan:
        return

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

        is_external = parts[0] in _external_prefixes

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
            proc = subprocess.run(parts, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"      ⏰ Command timed out after {timeout}s — skipping.")
            continue
        except Exception as e:
            print(f"      ⚠️  Command exception: {e}")
            continue

        if proc.returncode != 0:
            if cmd_name in _signal_commands or is_skill or is_external:
                print(f"      ℹ  Signal exit ({proc.returncode}) — continuing.")
                consecutive_failures = 0  # Reset: signal exits aren't real failures
            else:
                consecutive_failures += 1
                print(f"\n  ⚠️  Command failed (exit {proc.returncode}).")
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
    from uidetox.subagent import REVIEW_DOMAINS, REVIEW_WAVE_1, REVIEW_WAVE_2
    review_parallel = len(REVIEW_DOMAINS)  # 10 domain shards
    print("  STAGE 3: RE-SCAN & POLISH")
    print("  " + "-" * 40)
    print("    3a. `npx gitnexus analyze`      — refresh codebase index")
    print("    3b. `uidetox rescan`            — fresh analysis")
    print("    3c. `uidetox critique .`        — design review")
    print("    3d. `uidetox polish .`          — final pass")
    print(f"    3e. `uidetox subagent --stage-prompt review --parallel {review_parallel}`")
    print(f"        → Spawns {review_parallel} parallel domain review subagents (2 waves of 5):")
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
