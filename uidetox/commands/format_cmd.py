"""Format command: run detected formatter."""

import argparse
import subprocess
from uidetox.tooling import detect_all
from uidetox.state import load_config


def run(args: argparse.Namespace):
    config = load_config()
    tooling = config.get("tooling")

    if tooling and tooling.get("formatter"):
        formatter = tooling["formatter"]
    else:
        profile = detect_all()
        if not profile.formatter:
            print("No formatter detected. Install biome or prettier.")
            return
        formatter = {"name": profile.formatter.name, "run_cmd": profile.formatter.run_cmd,
                     "fix_cmd": profile.formatter.fix_cmd}

    fix = getattr(args, "fix", False)
    cmd = formatter["fix_cmd"] if fix and formatter.get("fix_cmd") else formatter["run_cmd"]

    print("==============================")
    print(f" UIdetox Format ({formatter['name']})")
    print("==============================")
    print(f"  Running: {cmd}")
    print()

    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True, text=True, cwd=".", timeout=120
        )
    except FileNotFoundError:
        print(f"Command not found. Install {formatter['name']}.")
        return
    except subprocess.TimeoutExpired:
        print("Format check timed out after 120s.")
        return

    output = result.stdout + result.stderr

    if result.returncode == 0:
        if fix:
            print("✅ Formatting applied successfully.")
        else:
            print("✅ All files properly formatted.")
    else:
        if fix:
            print("🔧 Formatting applied.")
        else:
            print("⚠️  Formatting issues found:")
        if output.strip():
            print(output[:2000])

    if not fix and result.returncode != 0:
        print(f"\nRun 'uidetox format --fix' to auto-fix formatting issues.")
