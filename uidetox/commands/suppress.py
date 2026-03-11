"""Suppress command: permanently silence issues matching a wildcard pattern."""

import argparse
import fnmatch
from uidetox.state import load_state, save_state, load_config, save_config

def run(args: argparse.Namespace):
    pattern = getattr(args, "pattern", None)
    
    if not pattern:
        _list_suppressed()
        return
        
    if getattr(args, "remove", False):
        _remove_pattern(pattern)
    else:
        _add_pattern(pattern)

def _list_suppressed():
    config = load_config()
    patterns = config.get("ignore_patterns", [])
    
    print("\nSuppressed Patterns (issues matching these will be ignored):")
    if not patterns:
        print("  (None active)")
    for p in patterns:
        print(f"  - {p}")
        
    print("\nTo add:    uidetox suppress <pattern>")
    print("To remove: uidetox suppress --remove <pattern>")

def _add_pattern(pattern: str):
    config = load_config()
    patterns = set(config.get("ignore_patterns", []))
    
    if pattern in patterns:
        print(f"Pattern '{pattern}' is already suppressed.")
        return
        
    patterns.add(pattern)
    config["ignore_patterns"] = sorted(list(patterns))
    save_config(config)
    
    # Prune existing issues
    state = load_state()
    issues = state.get("issues", [])
    before_count = len(issues)
    
    # A pattern could match the file path OR the issue description itself
    # Desloppify supports wildcards
    kept_issues = []
    
    for issue in issues:
        file_path = issue.get("file", "")
        desc = issue.get("issue", "")
        
        # Simple glob matching on file or desc
        matches_file = fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(file_path, f"*{pattern}*")
        matches_desc = fnmatch.fnmatch(desc, pattern) or fnmatch.fnmatch(desc, f"*{pattern}*")
        matches_exact = pattern.lower() in file_path.lower() or pattern.lower() in desc.lower()
        
        if not (matches_file or matches_desc or matches_exact):
            kept_issues.append(issue)
            
    removed = before_count - len(kept_issues)
    if removed > 0:
        state["issues"] = kept_issues
        save_state(state)
        
    print(f"Added suppress pattern: {pattern}")
    if removed > 0:
        print(f"  Removed {removed} matching issue(s) from the current queue.")

def _remove_pattern(pattern: str):
    config = load_config()
    patterns = set(config.get("ignore_patterns", []))
    
    if pattern in patterns:
        patterns.remove(pattern)
        config["ignore_patterns"] = sorted(list(patterns))
        save_config(config)
        print(f"Removed suppress pattern: {pattern}")
        print("  (Run 'uidetox rescan' to catch issues that were previously ignored.)")
    else:
        print(f"Pattern '{pattern}' not found.")
