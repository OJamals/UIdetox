"""Suppress command: permanently silence issues matching a wildcard pattern."""

import argparse
import fnmatch
import sys
from uidetox.state import load_state, save_state, load_config, save_config

_MAX_PATTERN_LEN = 200


def _issue_matches_pattern(issue: object, pattern: str) -> bool:
    if not isinstance(issue, dict):
        return False

    file_path = issue.get("file", "")
    desc = issue.get("issue", "")

    # Match the file path or description using glob patterns.
    # fnmatch.fnmatch(path, f"*{pattern}*") already handles substring
    # matching when the pattern has no glob chars, so the plain
    # fnmatch.fnmatch(path, pattern) check would only add value for
    # explicit glob patterns (e.g. "*.tsx") — cover both cleanly here.
    matches_file = fnmatch.fnmatch(file_path, f"*{pattern}*") or fnmatch.fnmatch(file_path, pattern)
    matches_desc = fnmatch.fnmatch(desc, f"*{pattern}*") or fnmatch.fnmatch(desc, pattern)
    matches_exact = pattern.lower() in file_path.lower() or pattern.lower() in desc.lower()

    return matches_file or matches_desc or matches_exact


def _prune_matching_state_entries(pattern: str) -> tuple[int, int]:
    state = load_state()
    issues = state.get("issues", [])
    diff_baseline = state.get("diff_baseline", [])

    if not isinstance(issues, list):
        issues = []
    if not isinstance(diff_baseline, list):
        diff_baseline = []

    kept_issues = [issue for issue in issues if not _issue_matches_pattern(issue, pattern)]
    kept_baseline = [issue for issue in diff_baseline if not _issue_matches_pattern(issue, pattern)]

    removed_issues = len(issues) - len(kept_issues)
    removed_baseline = len(diff_baseline) - len(kept_baseline)

    if removed_issues > 0 or removed_baseline > 0:
        state["issues"] = kept_issues
        state["diff_baseline"] = kept_baseline
        save_state(state)

    return removed_issues, removed_baseline

def run(args: argparse.Namespace):
    pattern = getattr(args, "pattern", None)
    is_remove = getattr(args, "remove", False)

    # Treat common 'list' aliases as a request to show current suppressions,
    # but only when NOT combined with --remove (which means removing a pattern
    # that literally matches the word "list").
    _LIST_ALIASES = {"list", "show", "ls"}
    if not pattern or not pattern.strip() or (not is_remove and pattern.strip().lower() in _LIST_ALIASES):
        _list_suppressed()
        return

    if len(pattern) > _MAX_PATTERN_LEN:
        print(f"Error: Pattern too long ({len(pattern)} chars, max {_MAX_PATTERN_LEN}).")
        sys.exit(1)
        
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

    pattern_already_exists = pattern in patterns
    if not pattern_already_exists:
        patterns.add(pattern)
        config["ignore_patterns"] = sorted(list(patterns))
        save_config(config)

    removed_issues, removed_baseline = _prune_matching_state_entries(pattern)

    if pattern_already_exists:
        print(f"Pattern '{pattern}' is already suppressed.")
    else:
        print(f"Added suppress pattern: {pattern}")

    if removed_issues > 0:
        print(f"  Removed {removed_issues} matching issue(s) from the current queue.")
    if removed_baseline > 0:
        print(f"  Removed {removed_baseline} matching issue(s) from the diff baseline.")

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
