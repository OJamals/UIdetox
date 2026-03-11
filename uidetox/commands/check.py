"""Check command: runs tsc → lint → format in sequence."""

import argparse
import subprocess
from uidetox.tooling import detect_all
from uidetox.state import load_config, save_config
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

    if fix and (tooling.get("linter") or tooling.get("formatter")):
        print("━━━ Phase 1: Iterative Auto-Fix ━━━")
        for iteration in range(1, 4):
            print(f"Iteration {iteration}...")
            changed = False
            
            if tooling.get("formatter"):
                cmd = tooling["formatter"].get("fix_cmd")
                if cmd:
                    try:
                        res = subprocess.run(cmd.split(), capture_output=True, text=True, cwd=".")
                        # If formatter changed files, it usually outputs file names or has exit code
                        if res.returncode != 0 or "fixed" in res.stdout.lower() or "formatted" in res.stdout.lower():
                            changed = True
                    except FileNotFoundError:
                        print(f"Warning: Formatter command not found ({cmd})")

            if tooling.get("linter"):
                cmd = tooling["linter"].get("fix_cmd")
                if cmd:
                    try:
                        res = subprocess.run(cmd.split(), capture_output=True, text=True, cwd=".")
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
