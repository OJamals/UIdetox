"""Resolve command: marks an issue as fixed and signals loop continuation."""

import argparse
import sys
import subprocess
from uidetox.state import remove_issue, get_issue, load_state, load_config


def run(args: argparse.Namespace):
    issue_id = args.issue_id
    issue = get_issue(issue_id)
    if not issue:
        print(f"Error: Issue {issue_id} not found in the queue.", file=sys.stderr)
        sys.exit(1)

    success = remove_issue(issue_id, note=args.note)
    if success:
        state = load_state()
        remaining = len(state.get("issues", []))
        resolved_total = len(state.get("resolved", []))

        print(f"✅ Resolved {issue_id}: [{issue['tier']}] {issue['issue']}")
        print(f"   File: {issue['file']}")
        print(f"   Note: {args.note}")
        print(f"   Queue: {remaining} remaining | {resolved_total} resolved total")
        
        # Git Auto-Commit Integration
        config = load_config()
        if config.get("auto_commit", False):
            try:
                # Stage the fixed file AND the state tracking file
                subprocess.run(["git", "add", issue["file"]], check=True, capture_output=True)
                subprocess.run(["git", "add", ".uidetox/state.json"], check=True, capture_output=True)
                # Commit with standard UIdetox prefix
                commit_msg = f"[UIdetox] Fixed {issue_id}: {args.note}"
                subprocess.run(["git", "commit", "-m", commit_msg], check=True, capture_output=True)
                print(f"   📦 Auto-committed to git: {commit_msg}")
            except subprocess.CalledProcessError:
                print(f"   ⚠️  Warning: Git auto-commit failed. Is this a git repo?")
            except FileNotFoundError:
                print(f"   ⚠️  Warning: git command not found. Skipping auto-commit.")

        print()
        print("[AGENT LOOP SIGNAL]")
        print("Run `uidetox status` now to check score and continue the loop.")
    else:
        print(f"❌ Failed to remove {issue_id} from state.", file=sys.stderr)
        sys.exit(1)
