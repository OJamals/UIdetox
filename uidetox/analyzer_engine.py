"""Analyzer execution engine: per-rule, per-file, and project traversal."""

import hashlib
import re
from pathlib import Path

from uidetox.analyzer_ast import _analyze_ast, has_ast_for
from uidetox.analyzer_custom import _CUSTOM_CHECK_HANDLERS, _analyze_component_layout
from uidetox.analyzer_project import reconcile_project_issues
from uidetox.fileset import ProjectFileSet, find_project_root
from uidetox.findings import Finding
from uidetox.prompt_safety import sanitize_untrusted_data
from uidetox.rule_registry import ANALYZER_RULES as RULES
from uidetox.source_facts import SourceFacts


def _analyze_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    design_variance: int,
) -> list[Finding]:
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
        custom_issues = handler(rule, filepath, content, ext)
        if custom_issues is not None:
            return [
                _static_finding(item, filepath, content, rule=rule)
                for item in custom_issues
            ]

    # Emit every ordered occurrence. ``finditer`` advances safely for zero-width regexes.
    pattern = rule.get("pattern")
    if isinstance(pattern, re.Pattern):
        for match in pattern.finditer(content):
            issues.append(
                _static_finding(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    },
                    filepath,
                    content,
                    rule=rule,
                    start=match.start(),
                    end=match.end(),
                    matched_evidence=match.group(0),
                )
            )
    return issues


def _static_finding(
    issue: dict,
    filepath: Path,
    content: str,
    *,
    rule: dict | None = None,
    start: int | None = None,
    end: int | None = None,
    matched_evidence: str | None = None,
) -> Finding:
    """Convert one static candidate at the analyzer engine seam."""
    sanitized = sanitize_untrusted_data(issue, matched_evidence=matched_evidence)
    candidate = dict(sanitized) if isinstance(sanitized, dict) else {}
    line = int(candidate.get("line", 0) or 0)
    column = int(candidate.get("column", 0) or 0)
    if start is None:
        preceding = content.splitlines(keepends=True)[: max(0, line - 1)]
        start = sum(len(item) for item in preceding) + max(0, column - 1)
    if end is None:
        end = start
    if line <= 0:
        line = content.count("\n", 0, start) + 1
    if column <= 0:
        column = start - content.rfind("\n", 0, start)
    lines = content.splitlines()
    excerpt = str(candidate.get("snippet", ""))
    if not excerpt and line <= len(lines):
        excerpt = lines[line - 1].strip()
    detector_id = str(
        candidate.get("detector_id", candidate.get("id", "static-finding"))
    )
    tier = str(candidate.get("tier", (rule or {}).get("tier", "T2")))
    severity = {"T1": "info", "T2": "warning", "T3": "error", "T4": "critical"}.get(
        tier, "warning"
    )
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return Finding.create(
        detector_id=detector_id,
        category=str(candidate.get("category", "quality")),
        severity=severity,
        confidence=float(candidate.get("confidence", 1.0)),
        message=str(
            candidate.get("issue", candidate.get("message", "Static finding."))
        ),
        provenance="static",
        evidence={"matched_text": matched_evidence or "", "source_hash": source_hash},
        source_anchor={
            "path": str(filepath.resolve()),
            "line": line,
            "column": column,
            "start": start,
            "end": end,
        },
        suppression_key=detector_id,
        verifier={
            "kind": "static",
            "detector_id": detector_id,
            "source_path": str(filepath.resolve()),
            "source_hash": source_hash,
            "start": start,
            "end": end,
        },
        display_excerpt=excerpt,
        legacy={"command": str(candidate.get("command", ""))},
        extensions={
            key: candidate[key]
            for key in ("credential_class", "evidence_fingerprint")
            if key in candidate
        },
    )


def analyze_file(
    filepath: Path,
    design_variance: int = 8,
    *,
    facts: SourceFacts | None = None,
) -> list[Finding]:
    """Scan a single file against all slop rules.

    Args:
        filepath: File to scan.
        design_variance: Current DESIGN_VARIANCE dial value (affects conditional rules).
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
        issues.extend(_analyze_rule(rule, filepath, content, ext, design_variance))

    return [
        item if isinstance(item, Finding) else _static_finding(item, filepath, content)
        for item in issues
    ]


def analyze_directory(
    root_path: str = ".",
    exclude_paths: list[str] | None = None,
    zone_overrides: dict[str, str] | None = None,
    design_variance: int = 8,
    target_files: list[str | Path] | None = None,
    *,
    _analyze_file=None,
) -> list[Finding]:
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
    analysis_targets = file_set.discover()

    from concurrent.futures import ThreadPoolExecutor

    file_analyzer = _analyze_file or analyze_file

    def _analyze_wrapper(fp: Path) -> list:
        return file_analyzer(fp, design_variance=design_variance)  # type: ignore

    futures = []
    with ThreadPoolExecutor() as executor:
        for file_path in analysis_targets:
            futures.append(executor.submit(_analyze_wrapper, file_path))  # type: ignore

        for future in futures:
            all_issues.extend(future.result())

    all_issues = reconcile_project_issues(all_issues, root)

    canonical: list[Finding] = []
    for item in all_issues:
        if isinstance(item, Finding):
            canonical.append(item)
            continue
        path = Path(str(item.get("file", root)))
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
        canonical.append(_static_finding(item, path, content))
    return canonical
