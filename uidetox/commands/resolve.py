"""Resolve command: marks an issue as fixed and signals loop continuation."""

import argparse
import sys
import subprocess
from uidetox.state import remove_issue, get_issue, load_state, load_config, get_project_root
from uidetox.memory import save_session, log_progress, embed_fix_outcome
from uidetox.commands.batch_resolve import run_verification


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
        if not run_verification(config):
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

        # Git Auto-Commit via risk-aware policy
        if config.get("auto_commit", False):
            project_root = str(get_project_root())
            try:
                from uidetox.git_policy import CommitPolicy, safe_commit
                policy = CommitPolicy.from_config(config)
                commit_msg = f"[UIdetox] Fixed {issue_id}: {args.note}"
                result = safe_commit(
                    touched_files=[issue["file"]],
                    message=commit_msg,
                    policy=policy,
                    cwd=project_root,
                )
                if result.success:
                    print(f"   📦 Auto-committed to git: {commit_msg}")
                    if result.unrelated_files:
                        print(f"   ℹ  {len(result.unrelated_files)} unrelated file(s) left unstaged.")
                else:
                    print(f"   ⚠️  Auto-commit aborted: {result.aborted_reason}")
            except Exception as e:
                print(f"   ⚠️  Warning: Git auto-commit failed: {e}")

        print()
        print("[AUTONOMOUS LOOP SIGNAL]")
        if remaining > 0:
            print(f"{remaining} issues remain. Run `uidetox next` NOW to continue.")
        else:
            print("Queue empty. Run `uidetox status` to check if target is met.")
            print("If score < target, run `uidetox rescan` for deeper analysis.")
        print("DO NOT STOP. The loop is fully autonomous.")

        # Auto-save progress
        log_progress("resolve", f"Fixed {issue_id}: {args.note}")
        save_session(phase="fixing", last_command="resolve",
                     last_component=issue.get('file', ''),
                     issues_fixed=1, context=args.note)

        # Embed fix outcome for future sub-agent context injection
        try:
            embed_fix_outcome(
                file_path=issue.get("file", ""),
                issue=issue.get("issue", ""),
                fix=args.note,
                outcome="resolved",
            )
        except Exception:
            pass  # ChromaDB is optional — never block on embedding failure
    else:
        print(f"❌ Failed to remove {issue_id} from state.", file=sys.stderr)
        sys.exit(1)
