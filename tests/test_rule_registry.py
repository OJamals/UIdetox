"""Canonical rule metadata and prompt routing."""

from collections import Counter

from uidetox.analyzer import RULES
from uidetox.commands.next import _get_relevant_context
from uidetox.commands.scan import _AUTO_CATEGORIES
from uidetox.rule_registry import RULE_REGISTRY, get_rule


def test_registry_covers_analyzer_catalog_with_provenance():
    assert len(RULE_REGISTRY) == len(RULES) == 215
    assert tuple(RULE_REGISTRY) == tuple(rule["id"] for rule in RULES)
    assert all(spec.category for spec in RULE_REGISTRY.values())
    assert all(
        spec.sources and spec.sources[0] == "uidetox" for spec in RULE_REGISTRY.values()
    )
    assert all(spec.extensions for spec in RULE_REGISTRY.values())


def test_registry_replaces_invalid_focus_and_scrollbar_prescriptions():
    assert "FOCUS_VISIBLE_MISSING_SLOP" not in RULE_REGISTRY
    assert "UGLY_SCROLLBAR_SLOP" not in RULE_REGISTRY
    assert "FORCED_COLOR_ADJUST_NONE_SLOP" in RULE_REGISTRY
    assert "HIDDEN_SCROLLBAR_SLOP" in RULE_REGISTRY


def test_registry_consolidates_duplicate_color_and_gradient_rules():
    assert "COLOR_BLACK_SLOP" in RULE_REGISTRY
    assert "COLOR_GRADIENT_SLOP" in RULE_REGISTRY
    assert "TAILWIND_V4_GRADIENT_SLOP" in RULE_REGISTRY
    assert "CSS_PURE_BLACK_SLOP" not in RULE_REGISTRY
    assert "PURE_BLACK_TEXT_SLOP" not in RULE_REGISTRY


def test_registry_replaces_px_font_prescription_with_text_adjust_signal():
    assert "HARDCODED_PX_FONT_SLOP" not in RULE_REGISTRY
    assert "TEXT_SIZE_ADJUST_NONE_SLOP" in RULE_REGISTRY
    assert get_rule("TEXT_SIZE_ADJUST_NONE_SLOP").category == "accessibility"


def test_registry_replaces_supported_class_component_prescription():
    assert "DEPRECATED_CLASS_COMPONENT_SLOP" not in RULE_REGISTRY
    assert "REACT_LEGACY_STRING_REF_SLOP" in RULE_REGISTRY
    assert get_rule("REACT_LEGACY_STRING_REF_SLOP").category == "react"


def test_registry_replaces_universal_hover_prescription():
    assert "MISSING_HOVER_STATES" not in RULE_REGISTRY
    assert "HOVER_ONLY_REVEAL_SLOP" in RULE_REGISTRY
    assert get_rule("HOVER_ONLY_REVEAL_SLOP").category == "interaction"


def test_registry_replaces_smooth_scroll_snap_prescription():
    assert "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP" not in RULE_REGISTRY
    assert "SCROLL_SNAP_MANDATORY_SLOP" in RULE_REGISTRY
    assert get_rule("SCROLL_SNAP_MANDATORY_SLOP").category == "motion"


def test_registry_replaces_flex_centering_preference_with_ime_signal():
    assert "LAZY_FLEX_CENTER_SLOP" not in RULE_REGISTRY
    assert "INPUT_IME_ENTER_UNGUARDED_SLOP" in RULE_REGISTRY
    assert get_rule("INPUT_IME_ENTER_UNGUARDED_SLOP").category == "forms"


def test_registry_replaces_transition_preference_with_paste_signal():
    assert "MISSING_TRANSITION_SLOP" not in RULE_REGISTRY
    assert "INPUT_PASTE_BLOCKED_SLOP" in RULE_REGISTRY
    assert get_rule("INPUT_PASTE_BLOCKED_SLOP").category == "forms"


def test_registry_replaces_duplicate_empty_css_rule_with_bfcache_signal():
    assert "CSS_EMPTY_RULE_SLOP" not in RULE_REGISTRY
    assert "BFCACHE_UNLOAD_LISTENER_SLOP" in RULE_REGISTRY
    assert get_rule("BFCACHE_UNLOAD_LISTENER_SLOP").category == "performance"


def test_scan_categories_exactly_partition_analyzer_catalog():
    catalog = {str(rule["id"]) for rule in RULES}
    counts = Counter(
        rule_id for rule_ids in _AUTO_CATEGORIES.values() for rule_id in rule_ids
    )

    assert set(counts) == catalog
    assert all(count == 1 for count in counts.values())


def test_rule_id_routes_context_without_description_guessing():
    contexts = _get_relevant_context(
        [{"id": "TYPOGRAPHY_SLOP", "issue": "opaque finding", "command": "repair it"}]
    )

    assert contexts
    assert any("TYPOGRAPH" in context or "FONT" in context for context, _ in contexts)
    assert get_rule("TYPOGRAPHY_SLOP").category == "typography"


def test_touch_target_rule_routes_wcag_22_minimum_and_enhanced_guidance():
    contexts = _get_relevant_context(
        [{"id": "TOUCH_TARGET_SLOP", "issue": "opaque finding", "command": "repair it"}]
    )
    guidance = "\n".join(context for context, _ in contexts)

    assert get_rule("TOUCH_TARGET_SLOP").category == "accessibility"
    assert "24" in guidance
    assert "spacing" in guidance.lower()
    assert "44" in guidance
    assert "enhanced" in guidance.lower()


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
