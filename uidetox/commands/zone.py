"""Zone command: show, set, and clear zone classifications for files."""

import argparse
from pathlib import Path
from uidetox.state import load_state, save_state, load_config, save_config

VALID_ZONES = {"production", "test", "config", "generated", "script", "vendor"}

def run(args: argparse.Namespace):
    action = getattr(args, "zone_action", "show")
    
    if action == "show":
        _zone_show()
    elif action == "set":
        _zone_set(getattr(args, "zone_path"), getattr(args, "zone_value"))
    elif action == "clear":
        _zone_clear(getattr(args, "zone_path"))
    else:
        print("Usage: uidetox zone {show|set|clear}")

def _determine_zone(filepath: str) -> str:
    """Basic fallback heuristics if not explicitly set."""
    p = filepath.lower()
    if "node_modules" in p or "vendor" in p:
        return "vendor"
    if "test" in p or "spec" in p:
        return "test"
    if p.endswith(".config.js") or p.endswith(".config.ts") or "config" in p:
        return "config"
    if "dist" in p or "build" in p or "out" in p or ".next" in p:
        return "generated"
    if p.endswith(".sh") or p.endswith(".py") or "scripts" in p:
        return "script"
    return "production"

def _zone_show():
    state = load_state()
    config = load_config()
    issues = state.get("issues", [])
    overrides = config.get("zone_overrides", {})
    
    # We only know about files that have issues currently, unless we do a full tree walk.
    # To keep it snappy and relevant, we'll show zones for files currently in the queue.
    unique_files = list(set(i.get("file") for i in issues if i.get("file")))
    
    by_zone = {z: [] for z in VALID_ZONES}
    for f in unique_files:
        if f in overrides:
            zone = overrides[f]
        else:
            zone = _determine_zone(f)
            
        if zone in by_zone:
            by_zone[zone].append(f)
        else:
            by_zone["production"].append(f)
            
    print(f"\nZone classifications (based on {len(unique_files)} files in queue)\n")
    for zone in ["production", "test", "config", "generated", "script", "vendor"]:
        files = by_zone.get(zone, [])
        if not files:
            continue
        print(f"  {zone} ({len(files)} files)")
        for f in sorted(files):
            suffix = " (override)" if f in overrides else ""
            print(f"    {f}{suffix}")
        print()
        
    print(f"  {len(overrides)} override(s) active in config")
    print("  Set:   uidetox zone set <file> <zone>")
    print("  Clear: uidetox zone clear <file>")

def _zone_set(filepath: str, zone_value: str):
    if not filepath or not zone_value:
        print("Error: Missing file or zone.")
        return
        
    if zone_value not in VALID_ZONES:
        print(f"Error: Invalid zone '{zone_value}'. Valid: {', '.join(sorted(VALID_ZONES))}")
        return
        
    config = load_config()
    overrides = config.get("zone_overrides", {})
    overrides[filepath] = zone_value
    config["zone_overrides"] = overrides
    save_config(config)
    
    print(f"  Set {filepath} → {zone_value}")
    
    # Cascade to state
    state = load_state()
    updated = 0
    for issue in state.get("issues", []):
        if issue.get("file") == filepath:
            issue["zone"] = zone_value
            updated += 1
            
    if updated > 0:
        save_state(state)
        print(f"  Applied to {updated} issue(s) in the current queue.")

def _zone_clear(filepath: str):
    if not filepath:
        print("Error: Missing file.")
        return
        
    config = load_config()
    overrides = config.get("zone_overrides", {})
    
    if filepath in overrides:
        del overrides[filepath]
        config["zone_overrides"] = overrides
        save_config(config)
        print(f"  Cleared override for {filepath}")
        
        state = load_state()
        updated = 0
        default_zone = _determine_zone(filepath)
        for issue in state.get("issues", []):
            if issue.get("file") == filepath:
                issue["zone"] = default_zone
                updated += 1
                
        if updated > 0:
            save_state(state)
            print(f"  Re-stamped {updated} issue(s) to '{default_zone}'.")
    else:
        print(f"  No override found for {filepath}")
