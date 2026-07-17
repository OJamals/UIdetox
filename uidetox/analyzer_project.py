"""Project-level reconciliation for facts that span source files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_FORM_TAG = re.compile(r"<form\b[^>]*>", re.IGNORECASE)
_HANDLER_ATTRIBUTE = re.compile(r"\b(?:action|onsubmit)\s*=", re.IGNORECASE)
_ID_ATTRIBUTE = re.compile(r"\bid\s*=\s*([\"'])([^\"']+)\1", re.IGNORECASE)
_SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
_SRC_ATTRIBUTE = re.compile(r"\bsrc\s*=\s*([\"'])([^\"']+)\1", re.IGNORECASE)
_SCRIPT_EXTENSIONS = {".cjs", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


def reconcile_project_issues(
    issues: Iterable[dict],
    scope_root: Path,
) -> list[dict]:
    """Remove per-file findings disproved by linked project evidence."""

    issue_list = list(issues)
    form_issue_files = {
        Path(str(issue.get("file", ""))).resolve()
        for issue in issue_list
        if issue.get("id") == "FORM_NO_SUBMIT_SLOP"
        and str(issue.get("file", "")).lower().endswith((".htm", ".html"))
    }
    if not form_issue_files:
        return issue_list

    resolved_form_files = {
        path
        for path in form_issue_files
        if _all_native_forms_have_submit_handlers(
            path,
            scope_root.resolve(),
        )
    }
    return [
        issue
        for issue in issue_list
        if not (
            issue.get("id") == "FORM_NO_SUBMIT_SLOP"
            and Path(str(issue.get("file", ""))).resolve() in resolved_form_files
        )
    ]


def _all_native_forms_have_submit_handlers(
    html_path: Path,
    scope_root: Path,
) -> bool:
    try:
        html = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    unhandled_forms = [
        match.group(0)
        for match in _FORM_TAG.finditer(html)
        if not _HANDLER_ATTRIBUTE.search(match.group(0))
    ]
    if not unhandled_forms:
        return True

    scripts = [html]
    for path in sorted(_linked_scripts(html_path, html, scope_root)):
        try:
            scripts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    script_source = "\n".join(scripts)

    for form in unhandled_forms:
        identifier = _ID_ATTRIBUTE.search(form)
        if identifier is None:
            return False
        if not _has_submit_binding(script_source, identifier.group(2)):
            return False
    return True


def _linked_scripts(
    html_path: Path,
    html: str,
    scope_root: Path,
) -> set[Path]:
    linked: set[Path] = set()
    for tag_match in _SCRIPT_TAG.finditer(html):
        source_match = _SRC_ATTRIBUTE.search(tag_match.group(0))
        if source_match is None:
            continue
        source = source_match.group(2)
        if source.startswith(("http://", "https://", "//")):
            continue
        candidates = (
            (
                scope_root / source.lstrip("/"),
                html_path.parent / source.lstrip("/"),
            )
            if source.startswith("/")
            else (html_path.parent / source,)
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            try:
                resolved.relative_to(scope_root)
            except ValueError:
                continue
            if (
                resolved.is_file()
                and resolved.suffix.lower() in _SCRIPT_EXTENSIONS
            ):
                linked.add(resolved)
                break
    return linked


def _has_submit_binding(script: str, form_id: str) -> bool:
    escaped_id = re.escape(form_id)
    selectors = (
        rf"document\.getElementById\(\s*[\"']{escaped_id}[\"']\s*\)",
        rf"document\.querySelector\(\s*[\"']#{escaped_id}[\"']\s*\)",
    )
    for selector in selectors:
        if re.search(
            selector
            + r"\s*\.\s*addEventListener\(\s*([\"'])submit\1",
            script,
            re.IGNORECASE,
        ):
            return True
        assignment = re.search(
            rf"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*{selector}\s*;?",
            script,
            re.IGNORECASE,
        )
        if assignment is None:
            continue
        variable = re.escape(assignment.group(1))
        if re.search(
            rf"\b{variable}\s*\.\s*addEventListener\(\s*([\"'])submit\1",
            script[assignment.end() :],
            re.IGNORECASE,
        ):
            return True
    return False
