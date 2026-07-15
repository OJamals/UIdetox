"""Resolve command: marks an issue as fixed and signals loop continuation."""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from uidetox.state import remove_issue, get_issue, get_project_root, load_state, load_config
from uidetox.memory import save_session, log_progress, embed_fix_outcome
from uidetox.commands.batch_resolve import _run_verification
from uidetox.utils import tracked_changed_entries, untracked_changed_files


def run(args: argparse.Namespace):
    issue_id = args.issue_id
    issue = get_issue(issue_id)
    if not issue:
        print(f"Error: Issue {issue_id} not found in the queue.", file=sys.stderr)
        sys.exit(1)

    if not args.note or not args.note.strip():
        print("Error: --note cannot be empty. Provide a brief description of the fix.", file=sys.stderr)
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
        if config.get("auto_commit", False):
            project_root = get_project_root()

            def _normalize(path: str) -> str:
                return str((project_root / path).resolve()) if not os.path.isabs(path) else os.path.abspath(path)

            allowed_tracked_changes = {
                _normalize(issue["file"]),
                _normalize(".uidetox/state.json"),
            }
            stage_paths = {_normalize(issue["file"])}
            issue_path = _normalize(issue["file"])
            issue_parent_dir = Path(issue_path).parent
            unexpected_tracked_changes = {
                _normalize(current_path)
                for original_path, current_path in tracked_changed_entries()
                if not ({_normalize(original_path), _normalize(current_path)} & allowed_tracked_changes)
            }
            untracked_paths = {_normalize(path) for path in untracked_changed_files()}
            sibling_untracked_paths = {path for path in untracked_paths if Path(path).parent == issue_parent_dir}
            allowed_untracked_changes: set[str] = set()
            if not Path(issue_path).exists() and len(sibling_untracked_paths) == 1:
                allowed_untracked_changes.update(sibling_untracked_paths)
            unexpected_untracked_changes = untracked_paths - allowed_untracked_changes
            for original_path, current_path in tracked_changed_entries():
                normalized_paths = {_normalize(original_path), _normalize(current_path)}
                if normalized_paths & allowed_tracked_changes:
                    stage_paths.update(normalized_paths)
            stage_paths.update(allowed_untracked_changes)
            if unexpected_tracked_changes or unexpected_untracked_changes:
                print("   ⚠️  Skipped git auto-commit because changes exist outside the resolved file.")
            else:
                try:
                    # Stage the fixed file AND the state tracking file
                    for path in sorted(stage_paths):
                        subprocess.run(["git", "add", path], check=True, capture_output=True, cwd=project_root)
                    subprocess.run(["git", "add", str((project_root / ".uidetox/state.json").resolve())], check=True, capture_output=True, cwd=project_root)
                    # Commit with standard UIdetox prefix
                    commit_msg = f"[UIdetox] Fixed {issue_id}: {args.note}"
                    subprocess.run(["git", "commit", "-m", commit_msg, "--no-verify"], check=True, capture_output=True, cwd=project_root)
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
