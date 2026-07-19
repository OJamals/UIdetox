"""Compatibility facade and issue projection for shared source facts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from uidetox import source_facts as _source_facts
from uidetox.source_facts import (
    SourceFacts,
    extract_source_facts,
)

# Compatibility seams retained for callers and monkeypatch-based tests.
importlib = _source_facts.importlib
tree_sitter = _source_facts.tree_sitter
_CORE_AST_ERROR = _source_facts._CORE_AST_ERROR
_AST_LANGUAGES = _source_facts._AST_LANGUAGES
AST_CAPABILITIES = _source_facts.AST_CAPABILITIES
HAS_AST = _source_facts.HAS_AST
_extract_usestate_binding = _source_facts._extract_usestate_binding
_identifier_tokens = _source_facts._identifier_tokens
_is_animation_state_identifier = _source_facts._is_animation_state_identifier


def _load_grammar(
    name: str,
    module_name: str,
    factory_name: str,
    extensions: tuple[str, ...],
) -> None:
    """Register one grammar through the shared parser registry."""
    _source_facts._load_grammar(name, module_name, factory_name, extensions)


def ast_capabilities() -> dict[str, dict[str, object]]:
    """Return serializable per-language AST availability and failure details."""
    return _source_facts.ast_capabilities()


def has_ast_for(ext: str) -> bool:
    """Report whether an AST parser is available for one file extension."""
    return _source_facts.has_ast_for(ext)


def _get_parser(ext: str):
    """Compatibility wrapper around shared parser selection."""
    return _source_facts.get_parser(ext)


def _analyze_ast(
    filepath: Path,
    content: str,
    ext: str,
    facts: SourceFacts | None = None,
) -> list[dict]:
    """Project shared AST facts into legacy analyzer issue dictionaries."""
    if facts is None:
        facts = extract_source_facts(filepath, content, parser_factory=_get_parser)
    if facts is None or ext not in {".tsx", ".jsx", ".js", ".ts"}:
        return []

    state = facts.analyzer
    issues: list[dict] = []
    fpath = str(filepath.resolve())

    if state.div_count > 20 and state.semantic_count == 0:
        issues.append(
            {
                "id": "DIV_SOUP_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state.div_count} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>.",
            }
        )

    if state.nested_ternaries >= 2:
        issues.append(
            {
                "id": "NESTED_TERNARY_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state.nested_ternaries} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity.",
            }
        )

    if state.cards >= 3 and state.charts >= 1:
        issues.append(
            {
                "id": "HERO_DASHBOARD_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Hero metric dashboard pattern detected via AST ({state.cards} cards, {state.charts} charts) — cliché AI layout.",
                "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow.",
            }
        )

    drilled_props = [
        name
        for name, components in state.prop_components
        if len(components) >= 4
        and name
        not in {
            "className",
            "children",
            "key",
            "id",
            "style",
            "ref",
            "onClick",
            "onChange",
        }
    ]
    if drilled_props:
        sample = ", ".join(sorted(drilled_props)[:5])
        issues.append(
            {
                "id": "PROP_DRILLING_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
                "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling.",
            }
        )

    if state.animation_state:
        issues.append(
            {
                "id": "ANIMATE_STATE_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": "React useState used for animation values — causes re-renders on every frame.",
                "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state.",
            }
        )

    for children in state.sibling_component_groups:
        if len(children) < 4:
            continue
        counts = Counter(children)
        for component_name, count in counts.items():
            if count < 4:
                continue
            issues.append(
                {
                    "id": "IDENTICAL_SIBLINGS_SLOP",
                    "file": fpath,
                    "tier": "T3",
                    "issue": f"Generic layout pattern detected via AST: {count} identical <{component_name}/> siblings — dashboard/feature-grid slop.",
                    "command": f"Vary the {component_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint.",
                }
            )
            break

    if state.styled_nesting_depth >= 5:
        issues.append(
            {
                "id": "STYLED_NESTING_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Deeply nested styled-component selectors detected ({state.styled_nesting_depth} levels) — specificity war.",
                "command": "Flatten CSS nesting. Use component composition instead of deeply nested selectors.",
            }
        )

    return issues
