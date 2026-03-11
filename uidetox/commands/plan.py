"""Plan command."""

import argparse
from uidetox.state import load_state

def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])
    
    if not issues:
        print("No issues in queue. Run 'uidetox scan' to find slop.")
        return
        
    print(f"==============================")
    print(f" UIdetox Queue Plan")
    print(f"==============================")
    
    tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
    sorted_issues = sorted(issues, key=lambda x: tiers_order.get(x.get("tier", "T4"), 5))
    
    grouped = {"T1": [], "T2": [], "T3": [], "T4": []}
    for issue in sorted_issues:
        tier = issue.get("tier", "T4")
        if tier in grouped:
            grouped[tier].append(issue)
            
    total = len(issues)
    print(f"Total Issues: {total}")
    for tier in ["T1", "T2", "T3", "T4"]:
        count = len(grouped[tier])
        if count > 0:
            print(f"\n[{tier}] ({count} issues)")
            for i in grouped[tier]:
                print(f"  - {i['id']} : {i['file']} - {i['issue']}")

    print(f"\n[AGENT INSTRUCTION]")
    print(f"Run 'uidetox next' to start fixing the highest priority issue.")
