"""Lint command: run detected linter and queue errors as issues."""

import argparse
import subprocess
import re
import uuid
from dataclasses import asdict
from uidetox.tooling import detect_all  # type: ignore
from uidetox.state import add_issue, load_config, get_project_root  # type: ignore
from uidetox.utils import run_tool  # type: ignore

_LINT_ERROR_PATTERN = re.compile(
    r"^([^:\n]+?):(\d+):(\d+)(?::\s*|\s+-\s*|\s+)(.+)$", re.MULTILINE
)


def run(args: argparse.Namespace):
    config = load_config()
    tooling = config.get("tooling")

    linters = []
    if tooling and tooling.get("all_linters"):
        linters = tooling["all_linters"]
    elif tooling and tooling.get("linter"):
        linters = [tooling["linter"]]
    else:
        profile = detect_all()
        if not profile.all_linters:
            print("No linters detected. Install biome, eslint, stylelint, or markuplint.")
            return
        linters = [asdict(l) for l in profile.all_linters]

    fix = getattr(args, "fix", False)
    total_queued = 0
    project_root = str(get_project_root())

    for linter in linters:
        cmd = linter["fix_cmd"] if fix and linter.get("fix_cmd") else linter["run_cmd"]

        print("==============================")
        print(f" UIdetox Lint ({linter['name']})")
        print("==============================")
        print(f"  Running: {cmd}")
        print()

        try:
            result = run_tool(cmd, cwd=project_root, timeout=120)
        except FileNotFoundError:
            print(f"Command not found. Install {linter['name']}.")
            continue
        except subprocess.TimeoutExpired:
            print(f"Lint check ({linter['name']}) timed out after 120s.")
            continue

        output = result.stdout + result.stderr

        if result.returncode == 0:
            print(f"✅ {linter['name']}: No lint errors found.")
            continue

        if fix:
            print(f"🔧 {linter['name']}: Auto-fix applied. Re-run without --fix to verify.")
            if output.strip():
                print(output[:1000])
            continue

        # Generic parser that catches file.ts:line:col
        errors = _LINT_ERROR_PATTERN.findall(output)

        queued = 0
        for file_path, line, col, msg in errors:
            fp = file_path.strip()
            if not fp or fp.startswith("(") or fp.startswith("["):
                continue
            issue_id = f"LINT-{uuid.uuid4().hex[:6].upper()}"  # type: ignore
            add_issue({  # type: ignore
                "id": issue_id,
                "file": file_path,
                "tier": "T1",
                "issue": f"{str(linter.get('name', '')).capitalize()} Lint: {msg.strip()} (line {line})",  # type: ignore
                "command": "lint-fix",
            })
            queued += 1
            if total_queued + queued <= 10:  # type: ignore
                print(f"  {issue_id}: {file_path}:{line} — {msg.strip()}")

        total_queued += queued  # type: ignore
        if queued > 0:
            print(f"  Found {queued} issue(s) with {linter['name']}.")  # type: ignore
        else:
            # Couldn't parse, just show raw output
            print(output[:1000])

    if total_queued > 10:  # type: ignore
        print(f"  ... and {total_queued - 10} more across all linters")  # type: ignore

    if total_queued > 0:  # type: ignore
        print(f"\n📋 Queued {total_queued} total lint error(s) as T1 issues.")
        print("Run 'uidetox next' to start fixing, or 'uidetox lint --fix' to auto-fix.")
