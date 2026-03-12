"""Format command: run detected formatter."""

import argparse
import subprocess
from dataclasses import asdict
from uidetox.tooling import detect_all  # type: ignore
from uidetox.state import load_config, get_project_root  # type: ignore
from uidetox.utils import run_tool  # type: ignore


def run(args: argparse.Namespace):
    config = load_config()
    tooling = config.get("tooling")

    formatters = []
    if tooling and tooling.get("all_formatters"):
        formatters = tooling["all_formatters"]
    elif tooling and tooling.get("formatter"):
        formatters = [tooling["formatter"]]
    else:
        profile = detect_all()
        if not profile.all_formatters:
            print("No formatter detected. Install biome or prettier.")
            return
        formatters = [asdict(f) for f in profile.all_formatters]

    fix = getattr(args, "fix", False)
    project_root = str(get_project_root())

    for formatter in formatters:
        cmd = formatter["fix_cmd"] if fix and formatter.get("fix_cmd") else formatter["run_cmd"]

        print("==============================")
        print(f" UIdetox Format ({formatter['name']})")
        print("==============================")
        print(f"  Running: {cmd}")
        print()

        try:
            result = run_tool(cmd, cwd=project_root, timeout=120)
        except FileNotFoundError:
            print(f"Command not found. Install {formatter['name']}.")
            continue
        except subprocess.TimeoutExpired:
            print(f"Format check ({formatter['name']}) timed out after 120s.")
            continue

        output = result.stdout + result.stderr

        if result.returncode == 0:
            if fix:
                print(f"✅ {formatter['name']}: Formatting applied successfully.")
            else:
                print(f"✅ {formatter['name']}: All files properly formatted.")
        else:
            if fix:
                print(f"🔧 {formatter['name']}: Formatting applied.")
            else:
                print(f"⚠️  {formatter['name']}: Formatting issues found:")
            if output.strip():
                print(output[:1000])

    # Final footer
    if not fix:
        print(f"\nRun 'uidetox format --fix' to auto-fix formatting issues.")
