"""Rescan command: clears the queue and re-scans the project."""

import argparse
import uuid
from uidetox.analyzer import analyze_directory
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import load_state, load_config, clear_issues, add_issue, increment_scans
from uidetox.history import save_run_snapshot

def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    old_count = len(state.get("issues", []))
    
    # Clear existing issues and track the rescan
    clear_issues()
    increment_scans()
    
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    
    path = getattr(args, "path", ".")
    
    print("==============================")
    print(" UIdetox Rescan")
    print("==============================")
    print(f"Cleared {old_count} previous issue(s).")
    print(f"Path: {path}")
    print(f"Vibe: Variance={variance}, Motion={intensity}, Density={density}")

    # Run static slop analyzer automatically
    ignore_patterns = config.get("ignore_patterns", [])
    print(f"\n[!] RUNNING STATIC SLOP ANALYZER...")
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(path, exclude_paths=exclude_paths, zone_overrides=zone_overrides)
    queued_count = 0
    for issue in slop_issues:
        if not _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            issue_id = f"SCAN-{str(uuid.uuid4())[:6].upper()}"
            new_issue = {
                "id": issue_id,
                "file": issue['file'],
                "tier": issue["tier"],
                "issue": issue["issue"],
                "command": issue["command"]
            }
            add_issue(new_issue)
            queued_count += 1
            
    if queued_count > 0:
        print(f"  ✓ Auto-queued {queued_count} deterministic AI slop anti-patterns.")
    else:
        print(f"  ✓ No deterministic AI slop detected by static analysis.")

    print(f"\n[AGENT INSTRUCTION]")
    print(f"Re-read all frontend files in '{path}'.")
    
    if ignore_patterns:
        print("\n  [!] ACTIVE SUPPRESSIONS (Do NOT flag issues matching these patterns):")
        for p in ignore_patterns:
            print(f"      - {p}")
            
    print("\n  [!] ZONING RULES:")
    print("      SKIP all files in 'vendor' or 'generated' zones (e.g., node_modules, dist, .next).")
    print("      ONLY audit 'production' and 'config' zones.")
    
    print(f"\nCompare against SKILL.md with fresh eyes.")
    print(f"For each NEW issue found, run:")
    print(f"  uidetox add-issue --file <path> --tier <T1-T4> --issue <description> --fix-command <cmd>")
    print(f"Then run `uidetox plan` and `uidetox status` to see the new health score.")
    save_run_snapshot(trigger="rescan")
