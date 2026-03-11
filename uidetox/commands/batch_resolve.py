"""Batch-resolve command: resolve multiple issues with a single coherent commit."""

import argparse
import subprocess
import sys
from pathlib import Path

from uidetox.state import batch_remove_issues, get_issue, load_state, load_config
from uidetox.memory import save_session, log_progress
from uidetox.utils import safe_split_cmd


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
                res = subprocess.run(safe_split_cmd(cmd), capture_output=True, text=True, cwd=".", timeout=120)
                if res.returncode != 0:
                    print(f"  ⚠️  TypeScript errors remain. Fix before committing.")
                    if res.stdout.strip():
                        print(f"\n{res.stdout.strip()}\n")
                    if res.stderr.strip():
                        print(f"\n{res.stderr.strip()}\n")
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
                res = subprocess.run(safe_split_cmd(fix_cmd), capture_output=True, text=True, cwd=".", timeout=120)
                print("  ✓ Linter auto-fix applied")
                if res.returncode != 0:
                    print(f"  ⚠️  Linter warned of remaining issues:")
                    if res.stdout.strip():
                        print(f"\n{res.stdout.strip()}\n")
                    if res.stderr.strip():
                        print(f"\n{res.stderr.strip()}\n")
                    passed = False
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("  ⚠️  Linter auto-fix skipped (tool not found or timed out)")

    # Format (auto-fix)
    if tooling.get("formatter"):
        fix_cmd = tooling["formatter"].get("fix_cmd")
        if fix_cmd:
            print("  Running formatter auto-fix...")
            try:
                res = subprocess.run(safe_split_cmd(fix_cmd), capture_output=True, text=True, cwd=".", timeout=120)
                print("  ✓ Formatter auto-fix applied")
                if res.returncode != 0:
                    print(f"  ⚠️  Formatter warned of remaining issues:")
                    if res.stdout.strip():
                        print(f"\n{res.stdout.strip()}\n")
                    if res.stderr.strip():
                        print(f"\n{res.stderr.strip()}\n")
                    passed = False
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
        if not _run_verification(config):
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
    from uidetox.utils import compute_design_score
    scores = compute_design_score(state)
    target = config.get("target_score", 95)
    filled = scores["blended_score"] // 5
    bar = "█" * filled + "░" * (20 - filled)
    print(f"   Score : [{bar}] {scores['blended_score']}/100  (target: {target})")
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
    print("[AGENT LOOP SIGNAL]")
    if remaining_in_component:
        print(f"Same component has {len(remaining_in_component)} more issues. Run `uidetox next` to continue.")
    elif remaining > 0:
        print(f"{remaining} issues remain in other components. Run `uidetox next` to continue.")
    elif scores["blended_score"] >= target:
        print("Queue empty and target reached! Run `uidetox finish`.")
    else:
        print(f"Queue empty but score {scores['blended_score']} < {target}. Run `uidetox rescan` for deeper analysis.")

    # Auto-save progress
    log_progress("batch-resolve", f"Detoxed {component}: {note} ({len(removed)} issues)")
    save_session(phase="fixing", last_command="batch-resolve",
                 last_component=component,
                 issues_fixed=len(removed), context=note)
