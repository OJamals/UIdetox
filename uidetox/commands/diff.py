"""Diff command — compare fresh static analysis against the stored issue baseline.

Shows which issues are:
  NEW      — detected now but not in the stored baseline (regressions introduced)
  FIXED    — in the stored baseline but no longer detected (improvements made)
  UNCHANGED — present in both (unresolved carryover)

Usage:
    uidetox diff                     Diff all files against stored baseline
    uidetox diff src/components/     Diff a specific directory
    uidetox diff --since <sha>       Only diff files changed since a git SHA
    uidetox diff --output json       Machine-readable JSON output
    uidetox diff --output github     GitHub Actions annotation format
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from uidetox.analyzer import analyze_directory, analyze_file
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import load_config, load_state, save_state


def _get_changed_files(since_sha: str, cwd: str) -> list[str] | None:
    """Return list of file paths changed since `since_sha`, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", since_sha],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _issue_fingerprint(issue: dict) -> str:
    """Stable key identifying a unique issue occurrence: file + rule/category + first-line context.

    Deliberately excludes the ``id`` field because fresh analysis generates
    new UUIDs on every run — including it would make every issue appear as
    NEW and the carry count would always be zero.
    """
    # Prefer rule_id/rule over the mutable UUID ``id``
    rule = issue.get("rule_id") or issue.get("rule") or issue.get("category", "")
    return f"{issue.get('file', '')}::{rule}::{issue.get('issue', '')[:60]}"


def _analyze_target(path: str, config: dict) -> list[dict]:
    """Run fresh static analysis on `path`, respecting config excludes/zones."""
    exclude_paths = config.get("ignore_patterns", [])
    zone_overrides = config.get("zone_overrides", {})
    variance = config.get("DESIGN_VARIANCE", 8)
    suppressions = config.get("ignore_patterns", [])

    target = Path(path).resolve()
    if target.is_file():
        raw = analyze_file(target, design_variance=variance)
    else:
        raw = analyze_directory(
            root_path=path,
            exclude_paths=exclude_paths,
            zone_overrides=zone_overrides,
            design_variance=variance,
        )

    return [i for i in raw if not _is_suppressed(i.get("file", ""), i.get("issue", ""), suppressions)]


def run(args: argparse.Namespace):
    config = load_config()
    state = load_state()

    path = getattr(args, "path", ".") or "."
    since_sha = getattr(args, "since", None)
    output_fmt = getattr(args, "output", "table")

    # ── Determine which files to scope the diff to ──
    scope_files: set[str] | None = None
    if since_sha:
        changed = _get_changed_files(since_sha, cwd=path)
        if changed is None:
            print(
                f"[diff] Warning: could not run `git diff --name-only {since_sha}` — diffing all files.",
                file=sys.stderr,
            )
        else:
            root_abs = str(Path(path).resolve())
            scope_files = {str(Path(root_abs) / f) for f in changed}
            if not scope_files:
                _emit(output_fmt, [], [], [], since_sha)
                return

    # ── Baseline: issues currently stored in state ──
    baseline_issues: list[dict] = state.get("issues", [])
    if scope_files is not None:
        baseline_issues = [
            i for i in baseline_issues
            if str(Path(i.get("file", "")).resolve()) in scope_files
        ]

    # ── Fresh: re-run static analysis ──
    fresh_issues = _analyze_target(path, config)
    if scope_files is not None:
        fresh_issues = [
            i for i in fresh_issues
            if str(Path(i.get("file", "")).resolve()) in scope_files
        ]

    # ── Compute diff sets ──
    baseline_fps = {_issue_fingerprint(i): i for i in baseline_issues}
    fresh_fps = {_issue_fingerprint(i): i for i in fresh_issues}

    baseline_keys = set(baseline_fps)
    fresh_keys = set(fresh_fps)

    new_issues = [fresh_fps[k] for k in sorted(fresh_keys - baseline_keys)]
    fixed_issues = [baseline_fps[k] for k in sorted(baseline_keys - fresh_keys)]
    unchanged_issues = [fresh_fps[k] for k in sorted(fresh_keys & baseline_keys)]

    _emit(output_fmt, new_issues, fixed_issues, unchanged_issues, since_sha)

    # ── Persist fresh scan as new baseline if requested ──
    save = getattr(args, "save", False)
    if save:
        if scope_files is not None:
            # Partial diff: merge fresh into the full state (replace scoped files)
            other_issues = [
                i for i in state.get("issues", [])
                if str(Path(i.get("file", "")).resolve()) not in scope_files
            ]
            state["issues"] = other_issues + fresh_issues
        else:
            state["issues"] = fresh_issues
        save_state(state)
        if output_fmt != "json":
            print(f"  [diff] Baseline updated — {len(state['issues'])} issue(s) saved to state.")


def _emit(
    fmt: str,
    new_issues: list[dict],
    fixed_issues: list[dict],
    unchanged_issues: list[dict],
    since_sha: str | None,
):
    if fmt == "json":
        payload = {
            "since": since_sha,
            "summary": {
                "new": len(new_issues),
                "fixed": len(fixed_issues),
                "unchanged": len(unchanged_issues),
            },
            "new": new_issues,
            "fixed": fixed_issues,
            "unchanged": unchanged_issues,
        }
        print(json.dumps(payload, indent=2))
        return

    if fmt == "github":
        for issue in new_issues:
            fpath = issue.get("file", "unknown")
            msg = issue.get("issue", "")
            tier = issue.get("tier", "T2")
            level = "error" if tier in ("T3", "T4") else "warning"
            print(f"::{level} file={fpath}::[NEW] {msg}")
        for issue in fixed_issues:
            fpath = issue.get("file", "unknown")
            msg = issue.get("issue", "")
            print(f"::notice file={fpath}::[FIXED] {msg}")
        return

    # ── Table format (default) ──
    width = 60
    print()
    print("+" + "=" * width + "+")
    print(f"| {'DIFF — Static Analysis Delta':^{width}} |")
    print("+" + "=" * width + "+")
    if since_sha:
        print(f"  Since : {since_sha}")
    print(f"  New   : {len(new_issues)} issue(s) introduced")
    print(f"  Fixed : {len(fixed_issues)} issue(s) resolved")
    print(f"  Carry : {len(unchanged_issues)} issue(s) unchanged")
    print()

    if new_issues:
        print(f"  {'─' * (width - 2)}")
        print(f"  NEW ISSUES  ({len(new_issues)} introduced)")
        print(f"  {'─' * (width - 2)}")
        for issue in new_issues:
            _print_issue(issue, prefix="  + ")

    if fixed_issues:
        print()
        print(f"  {'─' * (width - 2)}")
        print(f"  FIXED ISSUES  ({len(fixed_issues)} resolved)")
        print(f"  {'─' * (width - 2)}")
        for issue in fixed_issues:
            _print_issue(issue, prefix="  - ")

    if not new_issues and not fixed_issues:
        print("  No changes detected against the stored baseline.")
    print()


def _print_issue(issue: dict, prefix: str = "  "):
    tier = issue.get("tier", "??")
    rule_id = issue.get("id", "")
    file_path = issue.get("file", "")
    description = issue.get("issue", "")
    command = issue.get("command", "")

    try:
        rel = Path(file_path).relative_to(Path.cwd())
    except ValueError:
        rel = Path(file_path).name

    print(f"{prefix}[{tier}] {rule_id}")
    print(f"       {rel}")
    print(f"       {description}")
    if command:
        print(f"       → {command}")
    print()
