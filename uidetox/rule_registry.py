"""Canonical analyzer rule registry with provenance and prompt routing metadata."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from uidetox.analyzer_rules import RULES as _RAW_RULES


@dataclass(frozen=True)
class RuleSpec:
    id: str
    tier: str
    category: str
    description: str
    command: str
    extensions: tuple[str, ...]
    sources: tuple[str, ...]
    context_keys: tuple[str, ...]
    analyzer_rule: Mapping[str, Any]


_CATEGORY_MATCHERS = (
    (
        "accessibility",
        (
            "A11Y",
            "ACCESSIB",
            "ARIA",
            "TABINDEX",
            "FOCUS",
            "ALT_",
            "LABEL",
            "CAPTION",
            "SEMANTIC",
            "VIEWBOX",
        ),
    ),
    ("typography", ("TYPOGRAPH", "FONT", "LINE_HEIGHT", "TEXT_TRANSFORM")),
    (
        "color",
        ("COLOR", "PALETTE", "GRADIENT", "CONTRAST", "BLACK", "DARK_MODE", "OPACITY"),
    ),
    (
        "motion",
        ("MOTION", "ANIMAT", "TRANSITION", "BOUNCE", "AUTOPLAY", "SCROLL_BEHAVIOR"),
    ),
    (
        "layout",
        (
            "LAYOUT",
            "GRID",
            "FLEX",
            "CENTER",
            "DIV_SOUP",
            "COLUMN",
            "OVERFLOW",
            "STICKY",
            "Z_INDEX",
            "SPACING",
            "PADDING",
            "PX_",
            "RESPONSIVE",
            "MOBILE",
            "VIEWPORT",
        ),
    ),
    (
        "materiality",
        ("MATERIAL", "RADIUS", "SHADOW", "GLASS", "GLOW", "BORDER", "HAIRLINE"),
    ),
    ("iconography", ("ICON", "LUCIDE", "SVG")),
    (
        "forms",
        ("FORM", "INPUT", "SELECT", "BUTTON", "AUTOCOMPLETE", "PLACEHOLDER", "RESIZE"),
    ),
    ("content", ("COPY", "LOREM", "GENERIC", "DASHBOARD", "CARD", "EMPTY")),
    (
        "security",
        (
            "SECURITY",
            "EVAL",
            "INNERHTML",
            "COOKIE",
            "LOCALSTORAGE",
            "POSTMESSAGE",
            "OPEN_REDIRECT",
            "DOCUMENT_WRITE",
            "CROSS_ORIGIN",
        ),
    ),
    (
        "performance",
        (
            "PERF",
            "LAZY",
            "TREE_SHAKING",
            "INLINE_OBJECT",
            "REFERENCE",
            "SETINTERVAL",
            "SETTIMEOUT",
        ),
    ),
    (
        "react",
        (
            "REACT",
            "PROP",
            "STATE",
            "CONTEXT",
            "CLASS_COMPONENT",
            "FINDDOMNODE",
            "FRAGMENT",
            "KEY_",
        ),
    ),
    (
        "browser",
        (
            "BROWSER",
            "USER_AGENT",
            "VENDOR",
            "WEBKIT",
            "PROCESS_BROWSER",
            "TYPEOF_DOCUMENT",
        ),
    ),
    (
        "code-quality",
        (
            "UNUSED",
            "DUPLICATE",
            "COMMENTED",
            "DEBUGGER",
            "CONSOLE",
            "TERNARY",
            "TS_IGNORE",
            "NON_NULL",
            "UNREACHABLE",
            "ESLINT",
            "DEPRECATED",
        ),
    ),
)

_CATEGORY_CONTEXT = {
    "accessibility": ("accessibility", "a11y", "focus", "semantic"),
    "typography": ("typography", "font", "line-height"),
    "color": ("palette", "gradient", "contrast", "dark"),
    "motion": ("animation", "transition", "bounce"),
    "layout": ("responsive", "grid", "spacing", "viewport"),
    "materiality": ("border", "radius", "shadow", "glassmorphism"),
    "iconography": ("icon", "lucide", "viewbox"),
    "forms": ("form", "input", "button type", "autocomplete"),
    "content": ("copy", "generic", "card", "empty"),
    "security": (
        "eval(",
        "document.cookie",
        "open redirect",
        "cross-origin data injection",
    ),
    "performance": ("lazy(", "new reference on every render", "setinterval"),
    "react": (
        "context provider",
        "class component",
        "key prop",
        "usestate initialized with",
    ),
    "browser": ("browser sniffing", "user agent", "vendor prefix"),
    "code-quality": ("unused", "duplicate", "commented", "unreachable"),
    "interaction": ("hover", "loading", "error", "any"),
}

_CATEGORY_SOURCES = {
    "accessibility": ("uidetox", "impeccable"),
    "typography": ("uidetox", "taste", "impeccable", "hallmark"),
    "color": ("uidetox", "taste", "impeccable", "hallmark"),
    "motion": ("uidetox", "taste", "impeccable"),
    "layout": ("uidetox", "taste", "impeccable", "hallmark"),
    "materiality": ("uidetox", "taste", "impeccable", "hallmark"),
    "iconography": ("uidetox", "taste", "impeccable"),
    "forms": ("uidetox", "impeccable"),
    "content": ("uidetox", "taste", "hallmark"),
    "security": ("uidetox",),
    "performance": ("uidetox", "impeccable"),
    "react": ("uidetox",),
    "browser": ("uidetox",),
    "code-quality": ("uidetox",),
    "interaction": ("uidetox", "taste", "impeccable", "hallmark"),
}


def _category(rule_id: str) -> str:
    upper = rule_id.upper()
    for category, tokens in _CATEGORY_MATCHERS:
        if any(token in upper for token in tokens):
            return category
    return "interaction"


def _build_registry() -> dict[str, RuleSpec]:
    registry: dict[str, RuleSpec] = {}
    for rule in _RAW_RULES:
        rule_id = str(rule["id"])
        if rule_id in registry:
            raise ValueError(f"Duplicate analyzer rule id: {rule_id}")
        category = _category(rule_id)
        registry[rule_id] = RuleSpec(
            id=rule_id,
            tier=str(rule["tier"]),
            category=category,
            description=str(rule["description"]),
            command=str(rule["command"]),
            extensions=tuple(sorted(str(ext) for ext in rule["exts"])),
            sources=_CATEGORY_SOURCES[category],
            context_keys=_CATEGORY_CONTEXT[category],
            analyzer_rule=MappingProxyType(rule),
        )
    return registry


RULE_REGISTRY = MappingProxyType(_build_registry())
ANALYZER_RULES = tuple(dict(spec.analyzer_rule) for spec in RULE_REGISTRY.values())


def get_rule(rule_id: str | None) -> RuleSpec | None:
    """Resolve exact rule metadata; unknown/manual issues return ``None``."""
    return RULE_REGISTRY.get(str(rule_id or ""))
