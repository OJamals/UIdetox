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
from collections import defaultdict
import json
import subprocess
import sys
from pathlib import Path

from uidetox.analyzer import analyze_directory, analyze_file
from uidetox.commands.add_issue import _is_suppressed
from uidetox.fileset import ProjectFileSet, find_project_root
from uidetox.state import get_project_root, load_config, load_state, save_state


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
    """Stable key identifying a unique issue occurrence.

    We intentionally key on normalized file path + issue text instead of the
    mutable ``SCAN-*`` ids or optional rule metadata. Stored baselines and
    fresh analyzer output do not always carry the same rule fields, but they do
    consistently share the issue description. When location metadata is
    available, we include it so repeated identical messages in the same file do
    not collapse into a single occurrence.
    """
    line = issue.get("line")
    column = issue.get("column")
    location = f"{line}:{column}" if line is not None or column is not None else ""
    return f"{issue.get('file', '')}::{issue.get('issue', '')[:120]}::{location}"


def _resolve_issue_file(file_path: str, project_root: Path) -> str:
    if not file_path:
        return ""

    path = Path(file_path)
    if not path.is_absolute():
        path = project_root / path
    return str(path.resolve())


def _normalize_issue_file(issue: dict, project_root: Path) -> dict:
    resolved_file = _resolve_issue_file(issue.get("file", ""), project_root)
    if resolved_file and issue.get("file") != resolved_file:
        return {**issue, "file": resolved_file}
    return issue


def _group_issues_by_fingerprint(issues: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        grouped[_issue_fingerprint(issue)].append(issue)
    return grouped


def _load_diff_baseline(state: dict, project_root: Path) -> list[dict]:
    baseline = state.get("diff_baseline", [])
    if not isinstance(baseline, list):
        return []
    return [
        _normalize_issue_file(issue, project_root)
        for issue in baseline
        if isinstance(issue, dict)
    ]


def _analyze_target(
    path: str,
    config: dict,
    target_files: list[str | Path] | set[str] | None = None,
) -> list[dict]:
    """Run fresh static analysis on `path`, respecting config excludes/zones."""
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    variance = config.get("DESIGN_VARIANCE", 8)
    suppressions = config.get("ignore_patterns", [])

    target = Path(path).resolve()
    if target.is_file():
        file_set = ProjectFileSet(
            find_project_root(target),
            excludes=exclude_paths,
            zone_overrides=zone_overrides,
            explicit_targets=[target],
            scope_root=target.parent,
        )
        raw = (
            analyze_file(target, design_variance=variance)
            if file_set.accepts(target)
            else []
        )
    else:
        kwargs = dict(
            root_path=path,
            exclude_paths=exclude_paths,
            zone_overrides=zone_overrides,
            design_variance=variance,
        )
        if target_files is not None:
            kwargs["target_files"] = list(target_files)
        raw = analyze_directory(**kwargs)

    return [
        i
        for i in raw
        if not _is_suppressed(i.get("file", ""), i.get("issue", ""), suppressions)
    ]


def run(args: argparse.Namespace):
    config = load_config()
    state = load_state()
    project_root = get_project_root()

    path_arg = getattr(args, "path", ".")
    path = str(project_root) if path_arg in (None, "", ".") else path_arg
    since_sha = getattr(args, "since", None)
    output_fmt = getattr(args, "output", "table")

    # ── Determine which files to scope the diff to ──
    scope_files: set[str] | None = None
    if since_sha:
        scan_scope = Path(path).resolve()
        git_cwd = scan_scope if scan_scope.is_dir() else scan_scope.parent
        changed = _get_changed_files(since_sha, cwd=str(git_cwd))
        if changed is None:
            print(
                f"[diff] Warning: could not run `git diff --name-only {since_sha}` — diffing all files.",
                file=sys.stderr,
            )
        else:
            # git diff --name-only always returns paths relative to the git root,
            # regardless of cwd. Find the actual git root to construct correct
            # absolute paths — using `path` directly would double path segments
            # when path is a subdirectory (e.g. "src/components").
            try:
                gr = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    cwd=str(git_cwd),
                    timeout=5,
                )
                root_abs = (
                    gr.stdout.strip()
                    if gr.returncode == 0 and gr.stdout.strip()
                    else str(git_cwd)
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                root_abs = str(git_cwd)
            requested_files = {str((Path(root_abs) / f).resolve()) for f in changed}
            if scan_scope.is_file():
                requested_files.intersection_update({str(scan_scope)})
                scope_root = scan_scope.parent
            else:
                scope_root = scan_scope
            scope_files = {
                str(file_path)
                for file_path in ProjectFileSet(
                    project_root,
                    excludes=config.get("exclude", []),
                    zone_overrides=config.get("zone_overrides", {}),
                    explicit_targets=requested_files,
                    scope_root=scope_root,
                ).discover()
            }
            if not scope_files:
                _emit(output_fmt, [], [], [], since_sha)
                return

    # ── Baseline: issues currently stored in state ──
    stored_baseline = _load_diff_baseline(state, project_root)
    baseline_issues: list[dict] = stored_baseline
    if scope_files is not None:
        baseline_issues = [
            i for i in baseline_issues if i.get("file", "") in scope_files
        ]

    # ── Fresh: re-run static analysis ──
    if scope_files is None:
        analyzed_issues = _analyze_target(path, config)
    else:
        analyzed_issues = _analyze_target(path, config, target_files=scope_files)
    fresh_issues = [
        _normalize_issue_file(issue, project_root) for issue in analyzed_issues
    ]
    if scope_files is not None:
        fresh_issues = [i for i in fresh_issues if i.get("file", "") in scope_files]

    # ── Compute diff sets ──
    baseline_groups = _group_issues_by_fingerprint(baseline_issues)
    fresh_groups = _group_issues_by_fingerprint(fresh_issues)

    new_issues: list[dict] = []
    fixed_issues: list[dict] = []
    unchanged_issues: list[dict] = []

    for key in sorted(set(baseline_groups) | set(fresh_groups)):
        baseline_group = baseline_groups.get(key, [])
        fresh_group = fresh_groups.get(key, [])
        shared_count = min(len(baseline_group), len(fresh_group))

        unchanged_issues.extend(fresh_group[:shared_count])
        new_issues.extend(fresh_group[shared_count:])
        fixed_issues.extend(baseline_group[shared_count:])

    _emit(output_fmt, new_issues, fixed_issues, unchanged_issues, since_sha)

    # ── Persist fresh scan as new baseline if requested ──
    save = getattr(args, "save", False)
    if save:
        if scope_files is not None:
            # Partial diff: merge fresh into the full state (replace scoped files)
            other_issues = [
                i for i in stored_baseline if i.get("file", "") not in scope_files
            ]
            state["diff_baseline"] = other_issues + fresh_issues
        else:
            state["diff_baseline"] = fresh_issues
        save_state(state)
        if output_fmt != "json":
            print(
                f"  [diff] Baseline updated — {len(state['diff_baseline'])} issue(s) saved to diff baseline."
            )


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

    path_obj = Path(file_path)
    if not path_obj.is_absolute():
        rel = path_obj
    else:
        try:
            rel = path_obj.relative_to(get_project_root())
        except ValueError:
            rel = path_obj.name

    print(f"{prefix}[{tier}] {rule_id}")
    print(f"       {rel}")
    print(f"       {description}")
    if command:
        print(f"       → {command}")
    print()
