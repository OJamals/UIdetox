"""Lint command: run detected linter and queue errors as issues."""

import argparse

from uidetox.mechanical import diagnostic_finding, resolve_tool, run_diagnostics
from uidetox.state import add_issue, get_project_root, load_config


def run(args: argparse.Namespace):
    project_root = get_project_root()
    config = load_config()
    linter = resolve_tool("linter", project_root, config)
    if not linter:
        print("No linter detected. Install biome or eslint.")
        return

    fix = getattr(args, "fix", False)
    cmd = linter["fix_cmd"] if fix and linter.get("fix_cmd") else linter["run_cmd"]

    print("==============================")
    print(f" UIdetox Lint ({linter['name']})")
    print("==============================")
    print(f"  Running: {cmd}")
    print()

    result, errors = run_diagnostics("linter", cmd, project_root)
    if result.error == "command_not_found":
        print(f"Command not found. Install {linter['name']}.")
        return
    if result.error == "timeout":
        print("Lint check timed out after 120s.")
        return
    if result.returncode == 0:
        print("✅ No lint errors found.")
        return
    if fix:
        print("🔧 Auto-fix applied. Re-run without --fix to verify.")
        if result.output.strip():
            print(result.output[:1000])
        return
    queued = 0
    for error in errors:
        finding = diagnostic_finding("linter", error)
        add_issue(finding)
        queued += 1
        if queued <= 10:
            print(
                f"  {finding.to_dict()['id']}: "
                f"{error.path}:{error.line} — {error.message}"
            )
    if queued > 10:
        print(f"  ... and {queued - 10} more")

    if queued > 0:
        print(f"\n📋 Queued {queued} lint error(s) as T1 issues.")
        print(
            "Run 'uidetox next' to start fixing, or 'uidetox lint --fix' to auto-fix."
        )
    else:
        print(result.output[:2000])
