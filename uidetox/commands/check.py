"""Check command: runs tsc → lint → format in sequence."""

import argparse
import subprocess
from uidetox.tooling import detect_all
from uidetox.state import load_config, save_config, get_project_root
from uidetox.utils import run_tool
from uidetox.commands import tsc as tsc_cmd
from uidetox.commands import lint as lint_cmd
from uidetox.commands import format_cmd


def run(args: argparse.Namespace):
    # First, ensure tooling is detected
    config = load_config()
    if not config.get("tooling"):
        profile = detect_all()
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
    project_root = str(get_project_root())

    if fix and (tooling.get("linter") or tooling.get("formatter")):
        print("━━━ Phase 1: Iterative Auto-Fix ━━━")
        for iteration in range(1, 4):
            print(f"Iteration {iteration}...")
            changed = False
            
            if tooling.get("formatter"):
                cmd = tooling["formatter"].get("fix_cmd")
                if cmd:
                    try:
                        res = run_tool(cmd, cwd=project_root)
                        # If formatter changed files, it usually outputs file names or has exit code
                        if res.returncode != 0 or "fixed" in res.stdout.lower() or "formatted" in res.stdout.lower():
                            changed = True
                    except FileNotFoundError:
                        print(f"Warning: Formatter command not found ({cmd})")

            if tooling.get("linter"):
                cmd = tooling["linter"].get("fix_cmd")
                if cmd:
                    try:
                        res = run_tool(cmd, cwd=project_root)
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
                status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=project_root)
                changed_files = [
                    line[3:].strip() for line in status.stdout.strip().splitlines()
                    if line and len(line) >= 3 and line[1] == 'M'
                    # Only work-tree modifications (column 2 = 'M') — these are
                    # files the formatter/linter just changed.  Avoids staging
                    # the user's unrelated manually-modified files.
                ]
                if changed_files:
                    # Stage only files modified by linter/formatter, not all tracked files
                    for f in changed_files:
                        subprocess.run(["git", "add", f], cwd=project_root, capture_output=True)
                    subprocess.run(
                        ["git", "commit", "-m", "[UIdetox] Mechanical auto-fix (formatting/linting)", "--no-verify"],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        cwd=project_root,
                    )
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
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("Mechanical checks complete. Continue the autonomous loop:")
    print("  → Run `uidetox next` to fix the next batch of issues.")
    print("  → Or run `uidetox loop` to re-enter the full autonomous cycle.")
    print("DO NOT STOP.")
