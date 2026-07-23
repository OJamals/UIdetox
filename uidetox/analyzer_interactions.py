"""Cross-file interaction and development-server evidence for analyzer rules."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


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


def _uses_utility_classes(classes: str) -> bool:
    return any(_UTILITY_CLASS.match(token) for token in classes.split())


def _project_root(filepath: Path) -> Path:
    for candidate in (filepath.parent, *filepath.parents):
        if (candidate / "package.json").is_file():
            return candidate
    return filepath.parent


def _stylesheet_signature(root: Path) -> tuple[tuple[str, int, int], ...]:
    entries: list[tuple[str, int, int]] = []
    for stylesheet in root.rglob("*.css"):
        if any(part in _IGNORED_STYLE_DIRS for part in stylesheet.relative_to(root).parts):
            continue
        try:
            stat = stylesheet.stat()
        except OSError:
            continue
        entries.append((str(stylesheet), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


@lru_cache(maxsize=64)
def _stylesheet_text(signature: tuple[tuple[str, int, int], ...]) -> str:
    sources: list[str] = []
    for path, _, _ in signature:
        try:
            sources.append(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    return "\n".join(sources)


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
    stylesheet: str,
    tag: str,
    states: tuple[str, ...],
) -> bool:
    state_pattern = "|".join(re.escape(state) for state in states)
    tag_pattern = re.compile(rf"(?<![\w-]){re.escape(tag)}(?![\w-])")
    for selector_list in re.findall(r"([^{}]+)\{", stylesheet):
        for selector in _split_selector_list(selector_list):
            if re.search(rf":(?:{state_pattern})\b", selector) and tag_pattern.search(
                selector
            ):
                return True
    return False


def _semantic_class_has_state(
    classes: str,
    filepath: Path,
    states: tuple[str, ...],
    tag: str,
) -> bool:
    stylesheet = _stylesheet_text(_stylesheet_signature(_project_root(filepath)))
    if not stylesheet:
        return False
    if _tag_has_state(stylesheet, tag, states):
        return True

    state_pattern = "|".join(re.escape(state) for state in states)
    for token in classes.split():
        if not re.fullmatch(r"[A-Za-z_][\w-]*", token):
            continue
        escaped = re.escape(token)
        direct = rf"\.{escaped}(?:\[[^\]]+\]|:[\w-]+(?:\([^)]*\))?)*:(?:{state_pattern})\b"
        nested = rf"\.{escaped}\s*\{{[^{{}}]*&:(?:{state_pattern})\b"
        if re.search(direct, stylesheet) or re.search(
            nested, stylesheet, re.DOTALL
        ):
            return True
    return False


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
