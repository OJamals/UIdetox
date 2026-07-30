"""Cross-file interaction and development-server evidence for analyzer rules."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

_IGNORED_STYLE_DIRS = {
    ".git",
    ".next",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}
_UTILITY_CLASS = re.compile(
    r"^(?:[a-z-]+:)*(?:"
    r"bg-|text-|p[trblxy]?-|m[trblxy]?-|gap-|space-[xy]-|"
    r"border(?:-|$)|rounded(?:-|$)|shadow(?:-|$)|ring(?:-|$)|"
    r"w-|h-|min-[wh]-|max-[wh]-|grid(?:-|$)|flex(?:-|$)|"
    r"items-|justify-|font-|leading-|tracking-|opacity-|"
    r"cursor-|transition(?:-|$)|duration-|ease-|outline(?:-|$)"
    r")"
)
_DEV_SERVER_CONFIG_NAMES = {
    "playwright.config.js",
    "playwright.config.ts",
    "vite.config.js",
    "vite.config.ts",
    "vitest.config.js",
    "vitest.config.ts",
    "webpack.config.js",
    "webpack.config.ts",
}
_INTERACTION_STATE_GROUPS = (
    ("hover",),
    ("focus", "focus-visible"),
)


@dataclass(frozen=True)
class _StylesheetFacts:
    sources: tuple[tuple[str, str], ...]
    selectors_by_states: tuple[
        tuple[tuple[str, ...], tuple[str, ...]],
        ...,
    ]
    class_states: frozenset[tuple[str, tuple[str, ...]]]


_STYLESHEET_CONTEXT: ContextVar[Mapping[Path, _StylesheetFacts] | None] = ContextVar(
    "uidetox_stylesheet_context", default=None
)


def _uses_utility_classes(classes: str) -> bool:
    return any(_UTILITY_CLASS.match(token) for token in classes.split())


def _project_root(filepath: Path) -> Path:
    for candidate in (filepath.parent, *filepath.parents):
        if (candidate / "package.json").is_file():
            return candidate
    return filepath.parent


def _build_stylesheet_facts(root: Path) -> _StylesheetFacts:
    identities: list[tuple[str, str]] = []
    sources: list[str] = []
    for stylesheet in sorted(root.rglob("*.css")):
        if not _IGNORED_STYLE_DIRS.isdisjoint(stylesheet.relative_to(root).parts):
            continue
        try:
            source = stylesheet.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = stylesheet.relative_to(root).as_posix()
        identities.append(
            (relative, hashlib.sha256(source.encode("utf-8")).hexdigest())
        )
        sources.append(source)
    stylesheet = "\n".join(sources)
    selector_lists = tuple(re.findall(r"([^{}]+)\{", stylesheet))
    selectors_by_states: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    class_states: set[tuple[str, tuple[str, ...]]] = set()
    class_names = tuple(dict.fromkeys(re.findall(r"\.([A-Za-z_][\w-]*)", stylesheet)))
    for states in _INTERACTION_STATE_GROUPS:
        state_pattern = "|".join(re.escape(state) for state in states)
        state = rf":(?:{state_pattern})\b"
        selectors_by_states.append(
            (
                states,
                tuple(
                    selector
                    for selector_list in selector_lists
                    for selector in _split_selector_list(selector_list)
                    if re.search(state, selector)
                ),
            )
        )
        for class_name in class_names:
            escaped = re.escape(class_name)
            direct = rf"\.{escaped}(?:\[[^\]]+\]|:[\w-]+(?:\([^)]*\))?)*{state}"
            nested = rf"\.{escaped}\s*\{{[^{{}}]*&{state}"
            if re.search(rf"(?:{direct}|{nested})", stylesheet, re.DOTALL):
                class_states.add((class_name, states))
    return _StylesheetFacts(
        sources=tuple(identities),
        selectors_by_states=tuple(selectors_by_states),
        class_states=frozenset(class_states),
    )


def _stylesheet_context_for_files(
    files: Iterable[Path],
) -> Mapping[Path, _StylesheetFacts]:
    roots = sorted({_project_root(path) for path in files}, key=str)
    return MappingProxyType({root: _build_stylesheet_facts(root) for root in roots})


@contextmanager
def _activate_stylesheet_context(
    context: Mapping[Path, _StylesheetFacts],
) -> Iterator[None]:
    token = _STYLESHEET_CONTEXT.set(context)
    try:
        yield
    finally:
        _STYLESHEET_CONTEXT.reset(token)


@contextmanager
def _stylesheet_scope(filepath: Path) -> Iterator[None]:
    root = _project_root(filepath)
    context = _STYLESHEET_CONTEXT.get()
    if context is not None and root in context:
        yield
        return
    with _activate_stylesheet_context(
        MappingProxyType({root: _build_stylesheet_facts(root)})
    ):
        yield


def _stylesheet_facts(filepath: Path) -> _StylesheetFacts:
    root = _project_root(filepath)
    context = _STYLESHEET_CONTEXT.get()
    if context is not None and root in context:
        return context[root]
    return _build_stylesheet_facts(root)


def _split_selector_list(selector_list: str) -> tuple[str, ...]:
    selectors: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(selector_list):
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(depth - 1, 0)
        elif character == "," and depth == 0:
            selectors.append(selector_list[start:index])
            start = index + 1
    selectors.append(selector_list[start:])
    return tuple(selectors)


def _tag_has_state(
    facts: _StylesheetFacts,
    tag: str,
    states: tuple[str, ...],
) -> bool:
    tag_pattern = re.compile(rf"(?<![\w-]){re.escape(tag)}(?![\w-])")
    selectors = dict(facts.selectors_by_states).get(states, ())
    return any(tag_pattern.search(selector) for selector in selectors)


def _semantic_class_has_state(
    classes: str,
    filepath: Path,
    states: tuple[str, ...],
    tag: str,
) -> bool:
    facts = _stylesheet_facts(filepath)
    if not facts.sources:
        return False
    if _tag_has_state(facts, tag, states):
        return True
    return any(
        re.fullmatch(r"[A-Za-z_][\w-]*", token)
        and (token, states) in facts.class_states
        for token in classes.split()
    )


def class_list_has_interaction_state(
    classes: str,
    filepath: Path,
    state: str,
    tag: str,
) -> bool:
    """Verify interaction state from utility tokens or project CSS selectors."""
    utility_variants = {
        "hover": ("hover:",),
        "focus": ("focus:", "focus-visible:"),
    }[state]
    if _uses_utility_classes(classes):
        return any(variant in classes for variant in utility_variants)
    css_states = ("focus", "focus-visible") if state == "focus" else ("hover",)
    return _semantic_class_has_state(classes, filepath, css_states, tag)


def is_development_proxy_url(
    filepath: Path,
    content: str,
    match: re.Match[str],
) -> bool:
    """Return true only for a URL owned by known development-tool configuration."""
    if filepath.name not in _DEV_SERVER_CONFIG_NAMES:
        return False
    if filepath.name.startswith("playwright.config."):
        return True
    prefix = content[: match.start()]
    proxy_matches = tuple(re.finditer(r"\bproxy\s*:\s*\{", prefix))
    if not proxy_matches:
        return False
    proxy_block = prefix[proxy_matches[-1].end() - 1 :]
    return proxy_block.count("{") > proxy_block.count("}")
