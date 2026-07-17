"""Static Slop Analyzer: Detects AI anti-patterns via regex/AST rules."""
# ruff: noqa: F401 — compatibility facade intentionally re-exports analyzer seams.

from pathlib import Path

from uidetox.analyzer_ast import (
    AST_CAPABILITIES,
    HAS_AST,
    _analyze_ast,
    _extract_usestate_binding,
    _get_parser,
    _identifier_tokens,
    _is_animation_state_identifier,
    ast_capabilities,
    has_ast_for,
)
from uidetox.analyzer_custom import (
    _CUSTOM_CHECK_HANDLERS,
    _IMPORT_PATTERN,
    _analyze_accessibility_custom_rule,
    _analyze_browser_security_custom_rule,
    _analyze_commented_code_custom_rule,
    _analyze_component_layout,
    _analyze_contrast_custom_rule,
    _analyze_control_custom_rule,
    _analyze_css_custom_rule,
    _analyze_design_pattern_custom_rule,
    _analyze_document_structure_custom_rule,
    _analyze_html_custom_rule,
    _analyze_interaction_custom_rule,
    _analyze_react_custom_rule,
    _analyze_runtime_custom_rule,
    _analyze_tailwind_custom_rule,
    _analyze_unused_import_custom_rule,
    _analyze_unused_state_custom_rule,
    _extract_import_names,
    _find_unused_import_names,
)
from uidetox import analyzer_engine as _engine
from uidetox.analyzer_engine import _analyze_rule, analyze_file
from uidetox.analyzer_rules import _ALL_FE_EXTS, _FE_EXTS, _JSX_EXTS
from uidetox.fileset import IGNORED_DIRECTORY_NAMES
from uidetox.rule_registry import ANALYZER_RULES as RULES

# Compatibility alias retained for callers that imported traversal exclusions.
IGNORE_DIRS = IGNORED_DIRECTORY_NAMES


def analyze_directory(
    root_path: str = ".",
    exclude_paths: list[str] | None = None,
    zone_overrides: dict[str, str] | None = None,
    design_variance: int = 8,
    target_files: list[str | Path] | None = None,
) -> list[dict]:
    """Walk a directory through the execution engine.

    Passing the facade's current analyze_file binding preserves the existing
    monkeypatch seam used by callers and tests.
    """
    return _engine.analyze_directory(
        root_path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        design_variance=design_variance,
        target_files=target_files,
        _analyze_file=analyze_file,
    )
