"""Check command: runs tsc → lint → format in sequence."""

import argparse
import subprocess
from pathlib import Path
from uidetox.tooling import detect_all
from uidetox.state import get_project_root, load_config, save_config
from uidetox.utils import prepare_subprocess_cmd, tracked_changed_files
from uidetox.commands import tsc as tsc_cmd
from uidetox.commands import lint as lint_cmd
from uidetox.commands import format_cmd


def _auto_commit_changed_files(files: set[str], message: str) -> None:
    """Stage specific changed files and commit them."""
    project_root = get_project_root()

    for f in sorted(files):
        path = Path(f)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        subprocess.run(["git", "add", str(path)], check=False, cwd=project_root)

    subprocess.run(["git", "commit", "-m", message, "--no-verify"], check=False, cwd=project_root)


def _tracked_changed_files() -> set[str]:
    """Return tracked files with staged or unstaged changes."""
    return tracked_changed_files()


def run(args: argparse.Namespace):
    # First, ensure tooling is detected
    project_root = get_project_root()
    config = load_config()
    if not config.get("tooling"):
        profile = detect_all(project_root)
        config["tooling"] = profile.to_dict()
        save_config(config)
        print("Auto-detected project tooling.\n")

    tooling = config.get("tooling", {})

    print("╔══════════════════════════════╗")
    print("║   UIdetox Mechanical Check   ║")
    print("╚══════════════════════════════╝")
    print()

    fix = getattr(args, "fix", False)
    steps_run = 0
    pre_existing_changes: set[str] = set()

    if fix and config.get("auto_commit", False):
        pre_existing_changes = _tracked_changed_files()

    if fix and (tooling.get("linter") or tooling.get("formatter")):
        print("━━━ Phase 1: Iterative Auto-Fix ━━━")
        for iteration in range(1, 4):
            print(f"Iteration {iteration}...")
            changed = False
            
            if tooling.get("formatter"):
                cmd = tooling["formatter"].get("fix_cmd")
                if cmd:
                    try:
                        argv, env = prepare_subprocess_cmd(cmd)
                        res = subprocess.run(argv, capture_output=True, text=True, cwd=project_root, env=env)
                        if "fixed" in res.stdout.lower() or "formatted" in res.stdout.lower():
                            changed = True
                    except FileNotFoundError:
                        print(f"Warning: Formatter command not found ({cmd})")

            if tooling.get("linter"):
                cmd = tooling["linter"].get("fix_cmd")
                if cmd:
                    try:
                        argv, env = prepare_subprocess_cmd(cmd)
                        res = subprocess.run(argv, capture_output=True, text=True, cwd=project_root, env=env)
                        # If linter fixed files, it might still have exit code 1 if some remain
                        # We assume it changed things if the output mentions fixes, or just run max 3 times anyway
                        if "fixed" in res.stdout.lower() or "fixed" in res.stderr.lower():
                            changed = True
                    except FileNotFoundError:
                        print(f"Warning: Linter command not found ({cmd})")
            
            if not changed:
                print("Code is clean or no more auto-fixes available.\n")
                break
        print("Auto-fix phase complete.\n")

        if config.get("auto_commit", False):
            try:
                post_fix_changes = _tracked_changed_files()
                if pre_existing_changes:
                    print("  ⚠️  Skipped git auto-commit because tracked changes already existed before mechanical fixes.\n")
                else:
                    new_changes = post_fix_changes - pre_existing_changes
                    if new_changes:
                        _auto_commit_changed_files(new_changes, "[UIdetox] Mechanical auto-fix (formatting/linting)")
                        print("  📦 Auto-committed mechanical fixes to git.\n")
            except Exception as e:
                print(f"  ⚠️  Warning: Git auto-commit failed during mechanical check: {e}\n")

    print("━━━ Phase 2: Diagnostic Checks ━━━")

    # Step 1: TypeScript
    if tooling.get("typescript"):
        print("  Running TypeScript check...")
        tsc_args = argparse.Namespace(fix=False)
        tsc_cmd.run(tsc_args)
        steps_run += 1
        print()
    else:
        print("  TypeScript: skipped (not detected)\n")

    # Step 2: Lint
    if tooling.get("linter"):
        print("  Running Linter check...")
        lint_args = argparse.Namespace(fix=False)
        lint_cmd.run(lint_args)
        steps_run += 1
        print()
    else:
        print("  Linter: skipped (not detected)\n")

    # Step 3: Format
    if tooling.get("formatter"):
        print("  Running Formatter check...")
        fmt_args = argparse.Namespace(fix=False)
        format_cmd.run(fmt_args)
        steps_run += 1
        print()
    else:
        print("  Formatter: skipped (not detected)\n")

    if steps_run == 0:
        print("No tooling detected. Run 'uidetox detect' to configure tooling.")
        return

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Ran {steps_run} mechanical check(s).")
    print("Run 'uidetox status' to see the updated health score.")
    print("Run 'uidetox next' to start fixing any queued issues.")
