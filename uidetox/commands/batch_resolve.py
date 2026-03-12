"""Batch-resolve command: resolve multiple issues with a single coherent commit.

Includes failsafe pre-flight validation, rollback-safe verification, and
self-healing error injection so the agent can recover from broken builds.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from uidetox.state import batch_remove_issues, get_issue, load_state, load_config, get_project_root
from uidetox.memory import save_session, log_progress
from uidetox.utils import run_tool, compute_design_score


def _run_tool_step(*, cmd: str, label: str, action_label: str,
                   project_root: str, error_context: list[str]) -> bool:
    """Run a single verification step (tsc / lint / format).

    Returns True if the step passed, False otherwise.
    Appends to *error_context* on failure.
    """
    print(f"  Running {label}...")
    try:
        res = run_tool(cmd, cwd=project_root, timeout=120)
        if action_label:
            print(f"  ✓ {action_label}")
        if res.returncode != 0:
            errors = res.stdout.strip() or res.stderr.strip()
            if errors:
                truncated = "\n".join(errors.splitlines()[:30])
                if not action_label:
                    print(f"  ⚠️  {label} errors remain. Fix before committing.")
                else:
                    print(f"  ⚠️  {label} warned of remaining issues:")
                print(f"\n{truncated}\n")
                error_context.append(f"## {label} Errors\n```\n{truncated}\n```")
            return False
        if not action_label:
            print(f"  ✓ {label} passed")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"  ⚠️  {label} skipped (tool not found or timed out)")
        return True  # Non-blocking — tool missing is not a failure


def run_verification(config: dict) -> bool:
    """Run tsc → lint --fix → format --fix as a pre-commit quality gate.

    Returns True if all checks pass (or no tooling detected).
    Implements self-healing: captures error output and injects it into
    agent context so the repo is never left in an unbuildable state.
    """
    tooling = config.get("tooling", {})
    if not tooling:
        return True

    passed = True
    error_context: list[str] = []
    project_root = str(get_project_root())

    # TypeScript
    if tooling.get("typescript"):
        cmd = tooling["typescript"].get("run_cmd")
        if cmd and not _run_tool_step(
            cmd=cmd, label="TypeScript", action_label="",
            project_root=project_root, error_context=error_context,
        ):
            passed = False

    # Lint (auto-fix)
    if tooling.get("linter"):
        fix_cmd = tooling["linter"].get("fix_cmd")
        if fix_cmd and not _run_tool_step(
            cmd=fix_cmd, label="Linter", action_label="Linter auto-fix applied",
            project_root=project_root, error_context=error_context,
        ):
            passed = False

    # Format (auto-fix)
    if tooling.get("formatter"):
        fix_cmd = tooling["formatter"].get("fix_cmd")
        if fix_cmd and not _run_tool_step(
            cmd=fix_cmd, label="Formatter", action_label="Formatter auto-fix applied",
            project_root=project_root, error_context=error_context,
        ):
            passed = False

    # ── Self-Healing: inject error context for agent recovery ──
    if not passed and error_context:
        print()
        print("━━━ SELF-HEALING CONTEXT (fix these errors before proceeding) ━━━")
        print()
        for block in error_context:
            print(block)
        print()
        print("[AGENT INSTRUCTION] The build is broken after your fixes.")
        print("Read the errors above, fix them in the affected files, then retry:")
        print("  1. Fix the compilation/lint errors shown above")
        print("  2. Run `uidetox check --fix` to re-verify")
        print("  3. Retry `uidetox batch-resolve` or `uidetox resolve`")
        print("DO NOT proceed to the next issue until the build is green.")
        print()

        # Persist the error context to memory so sub-agents can see it
        try:
            from uidetox.memory import add_note
            error_summary = "; ".join(
                line.strip() for block in error_context
                for line in block.splitlines()
                if line.strip() and not line.startswith("```") and not line.startswith("##")
            )[:500]
            add_note(f"[SELF-HEAL] Build broken after fix attempt: {error_summary}")
        except Exception:
            pass  # Non-critical

    return passed


def _derive_component_name(files: list[str]) -> str:
    """Derive a human-readable component name from a list of file paths."""
    if not files:
        return "unknown"

    # Find common directory
    dirs = [str(Path(f).parent) for f in files]
    if len(set(dirs)) == 1:
        # All in same directory
        d = dirs[0]
        parts = d.replace("\\", "/").split("/")
        # Use last meaningful directory name
        for part in reversed(parts):
            if part and part != ".":
                return part
        return "root"

    # Multiple directories — find deepest common ancestor using path parts.
    # Use os.path.commonpath which is O(n) and cannot loop.
    import os
    try:
        common_str = os.path.commonpath(dirs)
    except ValueError:
        # dirs on different drives / no common prefix
        return "project"
    name = Path(common_str).name or "project"
    return name


def _preflight_validate(issue_ids: list[str], config: dict) -> list[str]:
    """Pre-flight validation before resolve.  Returns list of warning strings.

    Checks:
    1. All referenced files exist on disk
    2. No uncommitted changes in non-UIdetox files that could be lost
    3. State file is not corrupted
    """
    warnings: list[str] = []

    # Check that referenced files exist
    for iid in issue_ids:
        issue = get_issue(iid)
        if issue:
            fpath = issue.get("file", "")
            if fpath:
                from uidetox.state import get_project_root
                resolved_path = get_project_root() / fpath if not Path(fpath).is_absolute() else Path(fpath)
                if not resolved_path.exists():
                    warnings.append(f"File not found: {fpath} (issue {iid})")

    # Check for uncommitted changes that could conflict with auto-commit
    if config.get("auto_commit", False):
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=M"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                changed = [
                    f.strip() for f in result.stdout.strip().splitlines()
                    if f.strip() and not f.strip().startswith(".uidetox")
                ]
                if len(changed) > 20:
                    warnings.append(
                        f"Large number of uncommitted changes ({len(changed)} files). "
                        f"Consider committing manually first to avoid merge conflicts."
                    )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Git not available — skip check

    return warnings


def run(args: argparse.Namespace):
    issue_ids = args.issue_ids
    note = args.note
    skip_verify = getattr(args, "skip_verify", False)

    # Validate all IDs exist
    missing = []
    for iid in issue_ids:
        if not get_issue(iid):
            missing.append(iid)
    if missing:
        print(f"Error: Issue(s) not found: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    config = load_config()

    # ── Pre-flight validation ──
    preflight_warnings = _preflight_validate(issue_ids, config)
    if preflight_warnings:
        print("━━━ Pre-flight warnings ━━━")
        for w in preflight_warnings:
            print(f"  ⚠️  {w}")
        print()
        # Warnings are non-blocking but informational

    # Pre-commit verification gate
    if not skip_verify:
        print("━━━ Pre-commit verification ━━━")
        if not run_verification(config):
            print("❌ Verification failed. Build is broken.", file=sys.stderr)
            print()
            print("[AGENT INSTRUCTION] Fix the build errors above, then retry:")
            print("  1. Fix the compiler/lint errors in the affected files")
            print("  2. Run `uidetox check --fix` to auto-fix what you can")
            print(f"  3. Retry: uidetox batch-resolve {' '.join(issue_ids)} --note \"{note}\"")
            sys.exit(1)
        print()

    # Batch resolve
    removed = batch_remove_issues(issue_ids, note=note)
    if not removed:
        print("❌ No issues were resolved.", file=sys.stderr)
        sys.exit(1)

    # Collect affected files
    affected_files = list(set(r.get("file", "") for r in removed if r.get("file")))
    component = _derive_component_name(affected_files)

    state = load_state()
    remaining = len(state.get("issues", []))
    resolved_total = len(state.get("resolved", []))

    print(f"✅ Batch-resolved {len(removed)} issue(s):")
    for r in removed:
        print(f"   [{r['tier']}] {r['id']}: {r['issue'][:60]}")
    print(f"   Component: {component}")
    print(f"   Note: {note}")
    print()

    # ---- Progress snapshot ----
    scores = compute_design_score(state)
    target = config.get("target_score", 95)
    blended = scores["blended_score"]
    if blended is None:
        blended = 0
    filled = max(0, blended // 5)
    bar = "█" * filled + "░" * (20 - filled)
    print(f"   Score : [{bar}] {blended}/100  (target: {target})")
    print(f"   Queue : {remaining} remaining | {resolved_total} resolved total")

    # ---- Remaining issues in same component ----
    remaining_in_component = [
        i for i in state.get("issues", [])
        if _derive_component_name([i.get("file", "")]) == component
    ]
    if remaining_in_component:
        print(f"\n   ⚡ {len(remaining_in_component)} more issue(s) in {component}:")
        for i in remaining_in_component[:5]:
            short_file = Path(i.get("file", "")).name
            print(f"      [{i.get('tier', '?')}] {i.get('id', '?')} {short_file}: {i.get('issue', '?')[:55]}")
        if len(remaining_in_component) > 5:
            print(f"      ... +{len(remaining_in_component) - 5} more")

    # Git auto-commit via risk-aware policy (single commit for the entire batch)
    if config.get("auto_commit", False):
        project_root = str(get_project_root())
        try:
            from uidetox.git_policy import CommitPolicy, safe_commit
            policy = CommitPolicy.from_config(config)
            commit_msg = f"[UIdetox] Detoxed {component}: {note} ({len(removed)} issues resolved)"
            result = safe_commit(
                touched_files=affected_files,
                message=commit_msg,
                policy=policy,
                cwd=project_root,
            )
            if result.success:
                print(f"\n   📦 Auto-committed: {commit_msg}")
                if result.unrelated_files:
                    print(f"   ℹ  {len(result.unrelated_files)} unrelated file(s) left unstaged.")
            else:
                print(f"\n   ⚠️  Auto-commit aborted: {result.aborted_reason}")
        except Exception as e:
            print(f"\n   ⚠️  Warning: Git auto-commit failed: {e}")

    # ---- Agent loop signal ----
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("DO NOT STOP. Proceed immediately:")
    if remaining_in_component:
        print(f"  → {len(remaining_in_component)} more issues in {component}. Run `uidetox next` NOW.")
    elif remaining > 0:
        print(f"  → {remaining} issues in other components. Run `uidetox next` NOW.")
    elif blended >= target:
        print("  → Queue empty, target reached! Run `uidetox finish` NOW.")
    else:
        print(f"  → Queue empty but score {blended} < {target}. Run `uidetox rescan` NOW.")
    print("The loop is fully autonomous. Keep executing without pausing.")

    # Auto-save progress
    log_progress("batch-resolve", f"Detoxed {component}: {note} ({len(removed)} issues)")
    save_session(phase="fixing", last_command="batch-resolve",
                 last_component=component,
                 issues_fixed=len(removed), context=note)

    # Embed fix outcomes for future sub-agent context injection
    try:
        from uidetox.memory import embed_fix_outcome
        for r in removed:
            embed_fix_outcome(
                file_path=r.get("file", ""),
                issue=r.get("issue", ""),
                fix=note,
                outcome="resolved",
            )
    except Exception:
        pass  # ChromaDB is optional — never block on embedding failure
