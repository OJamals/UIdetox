"""uidetox watch — poll directory for file changes and re-scan on modification."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from uidetox.analyzer import analyze_file
from uidetox.state import get_project_root

# All extensions the analyzer cares about (mirrors _FE_EXTS + _JSX_EXTS + .ts/.js/.svelte etc.)
_WATCH_EXTS = {
    ".css", ".scss", ".less",
    ".tsx", ".jsx", ".ts", ".js",
    ".html", ".svelte", ".vue", ".svg",
}

# Colour helpers (same palette used in show.py)
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"

_TIER_COLOUR = {1: _DIM, 2: _YELLOW, 3: _RED, 4: _RED + _BOLD}
_TIER_LABEL = {1: "T1", 2: "T2", 3: "T3", 4: "T4"}


def _colour_tier(tier: int, text: str) -> str:
    return f"{_TIER_COLOUR.get(tier, '')}{text}{_RESET}"


def _snapshot(root: Path) -> dict[str, float]:
    """Return a mapping of {absolute_path: mtime} for all watched files under *root*."""
    result: dict[str, float] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden dirs and common noise dirs
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", ".git", "dist", "build", ".next", ".turbo"}
        ]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _WATCH_EXTS:
                try:
                    result[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
    return result


def _parse_tier(raw) -> int:
    """Normalize tier value to int. Handles both int (2) and string ('T2') forms."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.upper().startswith("T"):
        try:
            return int(raw[1:])
        except ValueError:
            pass
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 2


def _print_issues(issues: list[dict], filepath: str) -> None:
    rel = os.path.relpath(filepath)
    if not issues:
        print(f"  {_GREEN}✓{_RESET} {rel} — no issues")
        return

    print(f"  {_BOLD}{rel}{_RESET} — {len(issues)} issue(s):")
    for issue in issues:
        tier = _parse_tier(issue.get("tier", 2))
        rule_id = issue.get("id", "")
        description = issue.get("issue", "")
        line = issue.get("line")
        col = issue.get("column")
        loc = f":{line}:{col}" if line else ""
        label = _colour_tier(tier, _TIER_LABEL.get(tier, f"T{tier}"))
        print(f"    [{label}] {_DIM}{rule_id}{_RESET}  {description}{_DIM}{loc}{_RESET}")


def run(args) -> None:
    path_arg = getattr(args, "path", ".")
    root = (Path(get_project_root()) if path_arg in (None, "", ".") else Path(path_arg)).resolve()
    interval: float = getattr(args, "interval", 1.0)
    clear: bool = getattr(args, "clear", True)

    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"{_BOLD}uidetox watch{_RESET}  {_DIM}{root}{_RESET}")
    print(f"{_DIM}Polling every {interval}s — press Ctrl+C to stop{_RESET}\n")

    # Initial snapshot
    prev: dict[str, float] = _snapshot(root)

    # Run an initial scan of all files so the user has immediate feedback
    initial_issues: dict[str, list[dict]] = {}
    for fpath in prev:
        result = analyze_file(Path(fpath))
        if result:
            initial_issues[fpath] = result

    if clear:
        os.system("clear")

    print(f"{_BOLD}uidetox watch{_RESET}  {_DIM}{root}{_RESET}  {_DIM}(Ctrl+C to stop){_RESET}\n")
    if initial_issues:
        total = sum(len(v) for v in initial_issues.values())
        print(f"{_YELLOW}Initial scan: {total} issue(s) across {len(initial_issues)} file(s){_RESET}")
        for fpath, issues in initial_issues.items():
            _print_issues(issues, fpath)
    else:
        print(f"{_GREEN}Initial scan: no issues found.{_RESET}")

    try:
        while True:
            time.sleep(interval)
            curr = _snapshot(root)

            changed: list[str] = []

            # Detect modified and new files
            for fpath, mtime in curr.items():
                if fpath not in prev or prev[fpath] != mtime:
                    changed.append(fpath)

            # Detect deleted files
            deleted = [f for f in prev if f not in curr]

            if not changed and not deleted:
                continue

            if clear:
                os.system("clear")

            ts = time.strftime("%H:%M:%S")
            print(f"{_BOLD}uidetox watch{_RESET}  {_DIM}{root}{_RESET}  {_DIM}{ts} — Ctrl+C to stop{_RESET}\n")

            for fpath in sorted(changed):
                issues = analyze_file(Path(fpath))
                _print_issues(issues, fpath)

            for fpath in sorted(deleted):
                rel = os.path.relpath(fpath)
                print(f"  {_DIM}deleted: {rel}{_RESET}")

            prev = curr

    except KeyboardInterrupt:
        print(f"\n{_DIM}Watch stopped.{_RESET}")
