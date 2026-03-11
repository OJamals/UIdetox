"""Lint command: run detected linter and queue errors as issues."""

import argparse
import subprocess
import re
import uuid
from uidetox.tooling import detect_all
from uidetox.state import add_issue, load_config


def run(args: argparse.Namespace):
    config = load_config()
    tooling = config.get("tooling")

    if tooling and tooling.get("linter"):
        linter = tooling["linter"]
    else:
        profile = detect_all()
        if not profile.linter:
            print("No linter detected. Install biome or eslint.")
            return
        linter = {"name": profile.linter.name, "run_cmd": profile.linter.run_cmd,
                  "fix_cmd": profile.linter.fix_cmd}

    fix = getattr(args, "fix", False)
    cmd = linter["fix_cmd"] if fix and linter.get("fix_cmd") else linter["run_cmd"]

    print("==============================")
    print(f" UIdetox Lint ({linter['name']})")
    print("==============================")
    print(f"  Running: {cmd}")
    print()

    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True, text=True, cwd=".", timeout=120
        )
    except FileNotFoundError:
        print(f"Command not found. Install {linter['name']}.")
        return
    except subprocess.TimeoutExpired:
        print("Lint check timed out after 120s.")
        return

    output = result.stdout + result.stderr

    if result.returncode == 0:
        print("✅ No lint errors found.")
        return

    if fix:
        print("🔧 Auto-fix applied. Re-run without --fix to verify.")
        if output.strip():
            print(output[:1000])
        return

    # Generic parser that catches file.ts:line:col (with optional trailing colon)
    # Works for ESLint (unix/stylish), Biome, TSC, and standard GNU outputs
    pattern = re.compile(r"^([^:\n]+?):(\d+):(\d+)(?::\s*|\s+-\s*|\s+)(.+)$", re.MULTILINE)
    errors = pattern.findall(output)

    queued = 0
    for file_path, line, col, msg in errors:
        if file_path.startswith("/") or file_path.startswith(".") or ":" not in file_path:
            issue_id = f"LINT-{str(uuid.uuid4())[:6].upper()}"
            add_issue({
                "id": issue_id,
                "file": file_path,
                "tier": "T1",
                "issue": f"Lint: {msg.strip()} (line {line})",
                "command": "lint-fix",
            })
            queued += 1
            if queued <= 10:
                print(f"  {issue_id}: {file_path}:{line} — {msg.strip()}")

    if queued > 10:
        print(f"  ... and {queued - 10} more")

    if queued > 0:
        print(f"\n📋 Queued {queued} lint error(s) as T1 issues.")
        print("Run 'uidetox next' to start fixing, or 'uidetox lint --fix' to auto-fix.")
    else:
        # Couldn't parse, just show raw output
        print(output[:2000])
