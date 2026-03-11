"""TSC command: run TypeScript compiler and queue errors as issues."""

import argparse
import subprocess
import re
from uidetox.tooling import detect_all
from uidetox.state import add_issue, load_config
import uuid


def run(args: argparse.Namespace):
    config = load_config()
    tooling = config.get("tooling")

    if tooling and tooling.get("typescript"):
        tsc_cmd = tooling["typescript"]["run_cmd"]
    else:
        profile = detect_all()
        if not profile.typescript:
            print("No TypeScript configuration found in this project.")
            return
        tsc_cmd = profile.typescript.run_cmd

    fix = getattr(args, "fix", False)

    print("==============================")
    print(" UIdetox TypeScript Check")
    print("==============================")
    print(f"  Running: {tsc_cmd}")
    print()

    try:
        result = subprocess.run(
            tsc_cmd.split(),
            capture_output=True, text=True, cwd=".", timeout=120
        )
    except FileNotFoundError:
        print(f"Command not found. Install TypeScript: npm install -D typescript")
        return
    except subprocess.TimeoutExpired:
        print("TypeScript check timed out after 120s.")
        return

    output = result.stdout + result.stderr

    if result.returncode == 0:
        print("✅ No TypeScript errors found.")
        return

    # Parse tsc errors: file(line,col): error TSxxxx: message
    error_pattern = re.compile(r"^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)$", re.MULTILINE)
    errors = error_pattern.findall(output)

    if not errors:
        # Fallback: just print raw output
        print(output[:2000])
        return

    queued = 0
    for file_path, line, col, code, msg in errors:
        issue_id = f"TSC-{str(uuid.uuid4())[:6].upper()}"
        add_issue({
            "id": issue_id,
            "file": file_path.strip(),
            "tier": "T1",
            "issue": f"[{code}] {msg.strip()} (line {line})",
            "command": "tsc-fix",
        })
        queued += 1
        if queued <= 10:
            print(f"  {issue_id}: {file_path}:{line} — {msg.strip()}")

    if queued > 10:
        print(f"  ... and {queued - 10} more")

    print(f"\n📋 Queued {queued} TypeScript error(s) as T1 issues.")
    print("Run 'uidetox next' to start fixing them.")
