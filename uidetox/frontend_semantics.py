"""Compatibility projection from shared source facts to frontend semantics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uidetox.source_facts import (
    SourceFacts,
    extract_source_facts,
)
from uidetox.source_facts import (
    get_parser as _get_parser,
)

_UNSET_FACTS = object()


@dataclass(frozen=True)
class SemanticOccurrence:
    name: str
    line: int
    method: str | None = None
    dynamic: bool = False


@dataclass(frozen=True)
class ScriptSemantics:
    components: tuple[SemanticOccurrence, ...]
    imports: tuple[str, ...]
    rendered_tags: tuple[str, ...]
    regions: tuple[SemanticOccurrence, ...]
    actions: tuple[SemanticOccurrence, ...]
    states: tuple[SemanticOccurrence, ...]
    endpoints: tuple[SemanticOccurrence, ...]
    routes: tuple[SemanticOccurrence, ...]
    extractor: str
    confidence: float
    parse_errors: bool


def extract_script_semantics(
    path: Path,
    content: str,
    facts: SourceFacts | None | object = _UNSET_FACTS,
) -> ScriptSemantics | None:
    """Return compatibility values projected from the canonical adapter."""
    if facts is _UNSET_FACTS:
        facts = extract_source_facts(path, content, parser_factory=_get_parser)
    if facts is None:
        return None
    assert isinstance(facts, SourceFacts)
    return ScriptSemantics(
        components=tuple(
            SemanticOccurrence(item.name, item.line)
            for item in facts.declared_ui_modules
        ),
        imports=facts.imports,
        rendered_tags=tuple(item.binding for item in facts.rendered_bindings),
        regions=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.regions
        ),
        actions=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.actions
        ),
        states=tuple(SemanticOccurrence(item.name, item.line) for item in facts.states),
        endpoints=tuple(
            SemanticOccurrence(
                item.url or item.url_expression or item.target,
                item.line,
                method=item.method,
                dynamic=item.dynamic,
            )
            for item in facts.network_calls
        ),
        routes=tuple(SemanticOccurrence(item.name, item.line) for item in facts.routes),
        extractor=facts.extractor,
        confidence=facts.confidence,
        parse_errors=facts.parse_errors,
    )
