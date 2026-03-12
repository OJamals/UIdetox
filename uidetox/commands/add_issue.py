"""Add issue command."""

import argparse
import fnmatch
import uuid
from uidetox.state import add_issue, load_config

def _is_suppressed(file_path: str, description: str, patterns: list[str]) -> bool:
    """Check if this issue matches any active suppress pattern."""
    for pattern in patterns:
        if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(file_path, f"*{pattern}*"):
            return True
        if fnmatch.fnmatch(description, pattern) or fnmatch.fnmatch(description, f"*{pattern}*"):
            return True
        if pattern.lower() in file_path.lower() or pattern.lower() in description.lower():
            return True
    return False

def run(args: argparse.Namespace):
    config = load_config()
    ignore_patterns = config.get("ignore_patterns", [])
    
    if ignore_patterns and _is_suppressed(args.file, args.issue, ignore_patterns):
        print(f"Suppressed: [{args.tier}] {args.issue} in {args.file} (matches active ignore pattern)")
        return
    
    issue_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"
    new_issue = {
        "id": issue_id,
        "file": args.file,
        "tier": args.tier,
        "issue": args.issue,
        "command": args.fix_command
    }
    outcome = add_issue(new_issue)
    if outcome == "added":
        print(f"Added issue {issue_id}: [{args.tier}] {args.issue} in {args.file}")
    elif outcome == "updated":
        print(f"Updated existing pending issue: [{args.tier}] {args.issue} in {args.file}")
    else:
        print(f"Skipped duplicate pending issue: [{args.tier}] {args.issue} in {args.file}")

