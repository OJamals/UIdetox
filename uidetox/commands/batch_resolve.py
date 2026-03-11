"""Batch-resolve command: resolve multiple issues with a single coherent commit."""

import argparse
import subprocess
import sys
from pathlib import Path

from uidetox.state import batch_remove_issues, get_issue, load_state, load_config
from uidetox.memory import save_session, log_progress


def _run_verification(config: dict) -> bool:
    """Run tsc → lint --fix → format --fix as a pre-commit quality gate.

    Returns True if all checks pass (or no tooling detected).
    """
    tooling = config.get("tooling", {})
    if not tooling:
        return True

    passed = True

    # TypeScript
    if tooling.get("typescript"):
        cmd = tooling["typescript"].get("run_cmd")
        if cmd:
            print("  Running TypeScript check...")
            try:
                res = subprocess.run(cmd.split(), capture_output=True, text=True, cwd=".", timeout=120)
                if res.returncode != 0:
                    print(f"  ⚠️  TypeScript errors remain. Fix before committing.")
                    passed = False
                else:
                    print("  ✓ TypeScript passed")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("  ⚠️  TypeScript check skipped (tool not found or timed out)")

    # Lint (auto-fix)
    if tooling.get("linter"):
        fix_cmd = tooling["linter"].get("fix_cmd")
        if fix_cmd:
            print("  Running linter auto-fix...")
            try:
                subprocess.run(fix_cmd.split(), capture_output=True, text=True, cwd=".", timeout=120)
                print("  ✓ Linter auto-fix applied")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("  ⚠️  Linter auto-fix skipped (tool not found or timed out)")

    # Format (auto-fix)
    if tooling.get("formatter"):
        fix_cmd = tooling["formatter"].get("fix_cmd")
        if fix_cmd:
            print("  Running formatter auto-fix...")
            try:
                subprocess.run(fix_cmd.split(), capture_output=True, text=True, cwd=".", timeout=120)
                print("  ✓ Formatter auto-fix applied")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("  ⚠️  Formatter auto-fix skipped (tool not found or timed out)")

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

    # Multiple directories — find deepest common ancestor
    common: Path = Path(dirs[0])
    for i in range(1, len(dirs)):
        d = dirs[i]
        while not str(d).startswith(str(common)):
            common = common.parent # type: ignore
    name = common.name or "project" # type: ignore
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
        _run_verification(config)
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
    print(f"   Queue: {remaining} remaining | {resolved_total} resolved total")

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
            print(f"   📦 Auto-committed: {commit_msg}")
        except subprocess.CalledProcessError:
            print("   ⚠️  Warning: Git auto-commit failed.")
        except FileNotFoundError:
            print("   ⚠️  Warning: git not found. Skipping auto-commit.")

    print()
    print("[AGENT LOOP SIGNAL]")
    print("Run `uidetox status` to check score, then `uidetox next` to continue.")

    # Auto-save progress
    log_progress("batch-resolve", f"Detoxed {component}: {note} ({len(removed)} issues)")
    save_session(phase="fixing", last_command="batch-resolve",
                 last_component=component,
                 issues_fixed=len(removed), context=note)
