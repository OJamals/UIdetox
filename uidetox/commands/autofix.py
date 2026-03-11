"""Autofix command: automatically apply safe T1 fixes."""

import argparse
from uidetox.state import load_state, save_state, load_config

def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])
    
    t1_issues = [i for i in issues if i.get("tier") == "T1"]
    
    if not t1_issues:
        print("No T1 (quick fix) issues found. Nothing to autofix.")
        return
    
    dry_run = getattr(args, "dry_run", False)
    
    print("==============================")
    print(" UIdetox Autofix")
    print("==============================")
    print(f"Found {len(t1_issues)} T1 issue(s) eligible for autofix:\n")
    
    for issue in t1_issues:
        print(f"  [{issue['id']}] {issue['file']}: {issue['issue']}")
        print(f"    → Fix: {issue.get('command', 'manual')}")
    
    if dry_run:
        print(f"\n[DRY RUN] No changes applied. Remove --dry-run to apply.")
        return
    
    config = load_config()
    auto_commit = config.get("auto_commit", False)

    print(f"\n[AGENT INSTRUCTION]")
    print(f"Apply all {len(t1_issues)} T1 fixes listed above. For each:")
    print(f"  1. Open the file")
    print(f"  2. Apply the fix described above")
    print(f"  3. Run `uidetox resolve <issue_id> --note \"what you changed\"` when done")
    if auto_commit:
        print(f"\n  📦 AUTO-COMMIT is ON — each `resolve` will atomically commit the fix to git.")
    print(f"\nThese are safe, mechanical changes (font swaps, color replacements, spacing).")
    print(f"Apply them all before moving to T2+ issues.")
