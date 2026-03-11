"""Resolve command: marks an issue as fixed and signals loop continuation."""

import argparse
import sys
import subprocess
from uidetox.state import remove_issue, get_issue, load_state, load_config
from uidetox.memory import save_session, log_progress
from uidetox.commands.batch_resolve import _run_verification


def run(args: argparse.Namespace):
    issue_id = args.issue_id
    issue = get_issue(issue_id)
    if not issue:
        print(f"Error: Issue {issue_id} not found in the queue.", file=sys.stderr)
        sys.exit(1)

    skip_verify = getattr(args, "skip_verify", False)
    config = load_config()

    if not skip_verify:
        print("━━━ Pre-commit verification ━━━")
        if not _run_verification(config):
            print("❌ Verification failed. Build is broken. Fix it before resolving.", file=sys.stderr)
            sys.exit(1)
        print()

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
                subprocess.run(["git", "commit", "-m", commit_msg, "--no-verify"], check=True, capture_output=True)
                print(f"   📦 Auto-committed to git: {commit_msg}")
            except subprocess.CalledProcessError:
                print(f"   ⚠️  Warning: Git auto-commit failed. Is this a git repo?")
            except FileNotFoundError:
                print(f"   ⚠️  Warning: git command not found. Skipping auto-commit.")

        print()
        print("[AGENT LOOP SIGNAL]")
        print("Run `uidetox status` now to check score and continue the loop.")

        # Auto-save progress
        log_progress("resolve", f"Fixed {issue_id}: {args.note}")
        save_session(phase="fixing", last_command="resolve",
                     last_component=issue.get('file', ''),
                     issues_fixed=1, context=args.note)
    else:
        print(f"❌ Failed to remove {issue_id} from state.", file=sys.stderr)
        sys.exit(1)
