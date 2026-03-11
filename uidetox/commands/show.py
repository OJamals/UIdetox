"""Show command: display issues with color-coded tiers, grouping, and rich detail."""

import argparse
from pathlib import Path
from collections import defaultdict
from uidetox.state import load_state

# ANSI color codes for terminal output
_COLORS = {
    "T1": "\033[92m",   # Green — quick fix
    "T2": "\033[93m",   # Yellow — targeted refactor
    "T3": "\033[91m",   # Red — design judgment
    "T4": "\033[95m",   # Magenta — major redesign
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
}


def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])

    if not issues:
        print("No issues in queue. Run 'uidetox scan' first.")
        return

    pattern = getattr(args, "pattern", None)

    if not pattern:
        _render_grouped(issues)
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

    if len(matches) <= 5:
        _render_detailed(matches)
    else:
        _render_grouped(matches)


def _render_grouped(issues: list[dict]):
    """Group issues by file and render with color-coded tiers."""
    by_file: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        by_file[i.get("file", "unknown")].append(i)

    # Sort files by issue count (most issues first)
    sorted_files = sorted(by_file.items(), key=lambda x: -len(x[1]))

    # Tier summary
    tiers = defaultdict(int)
    for i in issues:
        tiers[i.get("tier", "T4")] += 1

    tier_summary = " | ".join(
        f"{_COLORS.get(t, '')}{t}: {c}{_COLORS['reset']}"
        for t, c in sorted(tiers.items())
    )

    print(f"\n  {_COLORS['bold']}UIdetox Issue Queue{_COLORS['reset']}  ({len(issues)} issues across {len(sorted_files)} files)")
    print(f"  {tier_summary}")
    print()

    for filepath, file_issues in sorted_files:
        # Shorten path for display
        short_path = _shorten_path(filepath)
        file_tiers = defaultdict(int)
        for i in file_issues:
            file_tiers[i.get("tier", "T4")] += 1
        tier_str = " ".join(f"{t}:{c}" for t, c in sorted(file_tiers.items()))

        print(f"  {_COLORS['bold']}{short_path}{_COLORS['reset']}  ({len(file_issues)} issues: {tier_str})")

        for i in sorted(file_issues, key=lambda x: {"T1": 0, "T2": 1, "T3": 2, "T4": 3}.get(x.get("tier", "T4"), 4)):
            tier = i.get("tier", "T4")
            color = _COLORS.get(tier, "")
            reset = _COLORS["reset"]
            dim = _COLORS["dim"]
            issue_text = i.get("issue", "?")
            # Truncate long issue descriptions
            if len(issue_text) > 80:
                issue_text = issue_text[:77] + "..."
            print(f"    {color}[{tier}]{reset} {i.get('id', '?'):<14} {issue_text}")

        print()

    print(f"  {_COLORS['dim']}Use: uidetox show <ID> for detail | uidetox show <T1-T4> to filter by tier{_COLORS['reset']}")


def _render_detailed(issues: list[dict]):
    """Render full detail for a small number of issues."""
    for i in issues:
        tier = i.get("tier", "T4")
        color = _COLORS.get(tier, "")
        reset = _COLORS["reset"]
        bold = _COLORS["bold"]

        print(f"\n  {bold}{i.get('id', '?')}{reset}  {color}[{tier}]{reset}")
        print(f"  File    : {i.get('file', '?')}")
        print(f"  Issue   : {i.get('issue', '?')}")
        print(f"  Fix     : {i.get('command', '?')}")
        print()


def _shorten_path(filepath: str) -> str:
    """Shorten an absolute or long path for display."""
    p = Path(filepath)
    parts = p.parts
    # Find a meaningful starting point
    for i, part in enumerate(parts):
        if part in ("src", "app", "pages", "components", "features", "lib", "modules", "views", "layouts"):
            return str(Path(*parts[i:]))
    # If path is long, show last 3 segments
    if len(parts) > 4:
        return ".../" + str(Path(*parts[-3:]))
    return filepath
