"""TSC command: run TypeScript compiler and queue errors as issues."""

import argparse

from uidetox.mechanical import diagnostic_finding, run_diagnostics
from uidetox.state import add_issue, get_project_root, load_config
from uidetox.tooling import detect_all


def run(args: argparse.Namespace):
    project_root = get_project_root()
    config = load_config()
    tooling = config.get("tooling")

    if tooling and tooling.get("typescript"):
        tsc_cmd = tooling["typescript"]["run_cmd"]
    else:
        profile = detect_all(project_root)
        if not profile.typescript:
            print("No TypeScript configuration found in this project.")
            return
        tsc_cmd = profile.typescript.run_cmd

    print("==============================")
    print(" UIdetox TypeScript Check")
    print("==============================")
    print(f"  Running: {tsc_cmd}")
    print()

    result, errors = run_diagnostics("typescript", tsc_cmd, project_root)
    if result.error == "command_not_found":
        print("Command not found. Install TypeScript: npm install -D typescript")
        return
    if result.error == "timeout":
        print("TypeScript check timed out after 120s.")
        return
    if result.returncode == 0:
        print("✅ No TypeScript errors found.")
        return
    if not errors:
        print(result.output[:2000])
        return
    queued = 0
    for error in errors:
        finding = diagnostic_finding("typescript", error)
        add_issue(finding)
        queued += 1
        if queued <= 10:
            print(
                f"  {finding.to_dict()['id']}: "
                f"{error.path}:{error.line} — {error.message}"
            )
    if queued > 10:
        print(f"  ... and {queued - 10} more")

    print(f"\n📋 Queued {queued} TypeScript error(s) as T1 issues.")
    print("Run 'uidetox next' to start fixing them.")
