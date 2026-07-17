"""Compatibility projection from shared source facts to frontend semantics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from uidetox.analyzer_ast import _get_parser
from uidetox.source_facts import SourceFacts, extract_source_facts

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
    """Return the legacy semantic view, reusing precomputed facts when supplied."""
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
        rendered_tags=facts.rendered_modules,
        regions=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.regions
        ),
        actions=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.actions
        ),
        states=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.states
        ),
        endpoints=tuple(
            SemanticOccurrence(
                item.url,
                item.line,
                method=item.method,
                dynamic=item.dynamic,
            )
            for item in facts.endpoints
            if item.url is not None
        ),
        routes=tuple(
            SemanticOccurrence(item.name, item.line) for item in facts.routes
        ),
        extractor=facts.extractor,
        confidence=facts.confidence,
        parse_errors=facts.parse_errors,
    )
