"""Show command: display details of a specific issue or filter by file/tier."""

import argparse
from uidetox.state import load_state

def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])
    
    if not issues:
        print("No issues in queue. Run 'uidetox scan' first.")
        return
    
    pattern = getattr(args, "pattern", None)
    
    if not pattern:
        # Show all issues
        _render_all(issues)
        return
    
    # Filter by pattern: match against issue ID, file path, or tier
    matches = [
        i for i in issues
        if pattern.lower() in i.get("id", "").lower()
        or pattern.lower() in i.get("file", "").lower()
        or pattern.upper() == i.get("tier", "").upper()
    ]
    
    if not matches:
        print(f"No issues matching '{pattern}'.")
        return
    
    _render_all(matches)

def _render_all(issues: list[dict]):
    print(f"{'ID':<14} {'Tier':<5} {'File':<40} Issue")
    print("-" * 90)
    for i in issues:
        print(f"{i.get('id', '?'):<14} {i.get('tier', '?'):<5} {i.get('file', '?'):<40} {i.get('issue', '?')}")
    print(f"\nTotal: {len(issues)} issue(s)")
