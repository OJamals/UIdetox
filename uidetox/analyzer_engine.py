"""Analyzer execution engine: per-rule, per-file, and project traversal."""

import re
from pathlib import Path

from uidetox.analyzer_ast import _analyze_ast, has_ast_for
from uidetox.analyzer_custom import _CUSTOM_CHECK_HANDLERS, _analyze_component_layout
from uidetox.analyzer_project import reconcile_project_issues
from uidetox.fileset import ProjectFileSet, find_project_root
from uidetox.rule_registry import ANALYZER_RULES as RULES
from uidetox.source_facts import SourceFacts


def _analyze_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    design_variance: int,
    dynamic_colors: dict[str, str] | None,
) -> list[dict]:
    """Analyze one configured rule against loaded source content."""
    issues = []
    # Skip rules conditioned on DESIGN_VARIANCE if below threshold
    variance_threshold = rule.get("_requires_variance_gt")
    if (
        isinstance(variance_threshold, (int, float))
        and design_variance <= variance_threshold
    ):
        return issues

    custom = rule.get("_custom_check")
    handler = _CUSTOM_CHECK_HANDLERS.get(custom)
    if handler is not None:
        custom_issues = handler(rule, filepath, content, ext, dynamic_colors)
        if custom_issues is not None:
            return custom_issues

    # Standard regex match — flag once per file
    pattern = rule.get("pattern")
    if isinstance(pattern, re.Pattern):
        m = pattern.search(content)
        if m:
            line_number = content.count("\n", 0, m.start()) + 1
            col = m.start() - content.rfind("\n", 0, m.start())
            lines_list = content.splitlines()
            snippet = (
                lines_list[line_number - 1].strip()
                if line_number <= len(lines_list)
                else ""
            )
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                    "line": line_number,
                    "column": col,
                    "snippet": snippet,
                }
            )
    return issues


def analyze_file(
    filepath: Path,
    design_variance: int = 8,
    dynamic_colors: dict[str, str] | None = None,
    *,
    facts: SourceFacts | None = None,
) -> list[dict]:
    """Scan a single file against all slop rules.

    Args:
        filepath: File to scan.
        design_variance: Current DESIGN_VARIANCE dial value (affects conditional rules).
        dynamic_colors: Tailwind configuration colors mappings.
    """
    issues = []
    ext = filepath.suffix.lower()

    # Filter rules that apply to this file extension
    applicable_rules = []
    for r in RULES:
        exts = r.get("exts", [])
        if isinstance(exts, (list, set, tuple)) and ext in exts:
            applicable_rules.append(r)
    if not applicable_rules:
        return issues

    try:
        # 1MB size guard to prevent regex engine freezing on massive bundled files
        if filepath.stat().st_size > 1_000_000:
            return issues

        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues  # Skip binary or unreadable files

    if has_ast_for(ext):
        ast_issues = _analyze_ast(filepath, content, ext, facts=facts)
        issues.extend(ast_issues)

    # Component-level layout heuristics (runs regardless of AST)
    layout_issues = _analyze_component_layout(filepath, content, ext)
    issues.extend(layout_issues)

    for rule in applicable_rules:
        issues.extend(
            _analyze_rule(rule, filepath, content, ext, design_variance, dynamic_colors)
        )

    return issues


def analyze_directory(
    root_path: str = ".",
    exclude_paths: list[str] | None = None,
    zone_overrides: dict[str, str] | None = None,
    design_variance: int = 8,
    target_files: list[str | Path] | None = None,
    *,
    _analyze_file=None,
) -> list[dict]:
    """Walk directory and return a flat list of all detected slop issues.

    Args:
        root_path: Directory to scan.
        exclude_paths: Additional directory names/paths to skip (from ``uidetox exclude``).
        zone_overrides: File-to-zone mapping; files in 'vendor' or 'generated' zones are skipped.
        design_variance: DESIGN_VARIANCE dial value passed to per-file analysis.
        target_files: Optional files to analyze. ``None`` walks the full tree; an
            explicit empty list analyzes no files.
    """
    all_issues = []
    root = Path(root_path).resolve()
    file_set = ProjectFileSet(
        find_project_root(root),
        excludes=exclude_paths or (),
        zone_overrides=zone_overrides or {},
        explicit_targets=target_files,
        scope_root=root,
    )
    target_candidates = file_set.explicit_candidates(require_extension=False)
    target_candidate_set = set(target_candidates or ())
    analysis_targets = file_set.discover()

    from concurrent.futures import ThreadPoolExecutor
    from uidetox.color_utils import (
        load_dynamic_colors,
        audit_project_colors,
        find_color_config_sources,
    )

    color_sources = find_color_config_sources(root)
    dynamic_colors = load_dynamic_colors(root)
    should_audit_colors = bool(color_sources) and (
        target_candidates is None
        or any(source.resolve() in target_candidate_set for source in color_sources)
    )
    color_audit_violations = audit_project_colors(root) if should_audit_colors else []
    color_issue_file = str((color_sources[0] if color_sources else root).resolve())
    file_analyzer = _analyze_file or analyze_file

    def _analyze_wrapper(fp: Path) -> list:
        return file_analyzer(
            fp, design_variance=design_variance, dynamic_colors=dynamic_colors
        )  # type: ignore

    futures = []
    with ThreadPoolExecutor() as executor:
        for file_path in analysis_targets:
            futures.append(executor.submit(_analyze_wrapper, file_path))  # type: ignore

        for future in futures:
            all_issues.extend(future.result())

    all_issues = reconcile_project_issues(all_issues, root)

    # Project-level dynamic color audit based on actual Tailwind/theme tokens.
    # Cap output to keep the queue actionable rather than overwhelming.
    for violation in color_audit_violations[:8]:
        all_issues.append(
            {
                "id": "LOW_CONTRAST_SLOP",
                "file": color_issue_file,
                "tier": "T1" if violation.get("severity") == "critical" else "T2",
                "issue": (
                    f"Dynamic color audit: {violation['foreground']} on {violation['background']} "
                    f"fails WCAG AA ({violation['ratio']}:1 < {violation['required']}:1)."
                ),
                "command": "Adjust the theme token pair to meet WCAG AA contrast, then rescan to verify the updated palette.",
            }
        )

    return all_issues
