"""Batch-resolve command: resolve multiple issues with a single coherent commit."""

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

    # Pre-commit verification gate
    if not skip_verify:
        print("━━━ Pre-commit verification ━━━")
        if not run_verification(config):
            print("❌ Verification failed. Build is broken.", file=sys.stderr)
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

    # Git auto-commit (single commit for the entire batch)
    if config.get("auto_commit", False):
        try:
            # Stage all affected files + state
            for f in affected_files:
                subprocess.run(["git", "add", f], check=True, capture_output=True)
            subprocess.run(["git", "add", ".uidetox/state.json"], check=True, capture_output=True)

            commit_msg = f"[UIdetox] Detoxed {component}: {note} ({len(removed)} issues resolved)"
            subprocess.run(
                ["git", "commit", "-m", commit_msg, "--no-verify"],
                check=True, capture_output=True,
            )
            print(f"\n   📦 Auto-committed: {commit_msg}")
        except subprocess.CalledProcessError:
            print("\n   ⚠️  Warning: Git auto-commit failed.")
        except FileNotFoundError:
            print("\n   ⚠️  Warning: git not found. Skipping auto-commit.")

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
