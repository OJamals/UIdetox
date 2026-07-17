"""Canonical rule metadata and prompt routing."""

from uidetox.analyzer import RULES
from uidetox.commands.next import _get_relevant_context
from uidetox.rule_registry import RULE_REGISTRY, get_rule


def test_registry_covers_analyzer_catalog_with_provenance():
    assert len(RULE_REGISTRY) == len(RULES) == 218
    assert tuple(RULE_REGISTRY) == tuple(rule["id"] for rule in RULES)
    assert all(spec.category for spec in RULE_REGISTRY.values())
    assert all(
        spec.sources and spec.sources[0] == "uidetox" for spec in RULE_REGISTRY.values()
    )
    assert all(spec.extensions for spec in RULE_REGISTRY.values())


def test_rule_id_routes_context_without_description_guessing():
    contexts = _get_relevant_context(
        [{"id": "TYPOGRAPHY_SLOP", "issue": "opaque finding", "command": "repair it"}]
    )

    assert contexts
    assert any("TYPOGRAPH" in context or "FONT" in context for context, _ in contexts)
    assert get_rule("TYPOGRAPHY_SLOP").category == "typography"


def test_fallback_matching_uses_token_boundaries():
    assert (
        _get_relevant_context(
            [
                {
                    "id": "MANUAL-1",
                    "issue": "Company profile",
                    "command": "Preserve brand",
                }
            ]
        )
        == []
    )
