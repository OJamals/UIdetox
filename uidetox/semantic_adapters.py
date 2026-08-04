"""Adapter-driven application semantics over the shared parser lifecycle.

Adapters normalize framework evidence. ``ApplicationSemantics`` then resolves
module/export identity once for mapping, network analysis, and runtime source
ownership. Tree-sitter remains owned by :mod:`uidetox.source_facts`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from uidetox.source_facts import (
    CallFact,
    ImportAlias,
    NetworkCallFact,
    RenderFact,
    SelectorFact,
    SourceFacts,
    SourceOccurrence,
    classify_network_type_references,
    extract_source_facts,
    has_ast_for,
    literal_text,
    selector_facts,
)

CapabilityStatus = Literal["native", "degraded", "unsupported"]
_SCRIPT_EXTENSIONS = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
_STYLE_EXTENSIONS = frozenset({".css", ".less", ".sass", ".scss"})
_EMBEDDED_EXTENSIONS = frozenset({".astro", ".html", ".htm", ".svelte", ".vue"})
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_ROUTE_SPECIFICITY_VECTOR_BUDGET = 64
_NETWORK_METHODS = frozenset(
    {
        "create",
        "delete",
        "execute",
        "get",
        "list",
        "load",
        "mutate",
        "patch",
        "post",
        "put",
        "query",
        "remove",
        "request",
        "update",
    }
)
_REGION_TAGS = frozenset(
    {
        "article",
        "aside",
        "dialog",
        "footer",
        "form",
        "header",
        "main",
        "nav",
        "section",
        "table",
    }
)
_TAG_RE = re.compile(r"<(?P<tag>[A-Za-z][A-Za-z0-9_.:-]*)\b(?P<attrs>[^>]*)>")
_SCRIPT_RE = re.compile(
    r"<script(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</script\s*>",
    re.IGNORECASE,
)
_ASTRO_SCRIPT_RE = re.compile(r"\A---[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n---")
_ATTRIBUTE_RE = re.compile(
    r"""(?P<name>[:@A-Za-z_][:\w.-]*)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)"""
)
_ACTION_RE = re.compile(
    r"(?:@|v-on:|on:|on)(?P<name>click|submit|change|focus|blur|keydown|keyup)",
    re.IGNORECASE,
)
_QUERY_HOOK_RE = re.compile(r"^use[A-Z][A-Za-z0-9]*(?:Query|Mutation)$")
_TYPE_BLOCK_RE = re.compile(
    r"\b(?:export\s+)?(?:interface\s+(?P<interface>[A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+[^{]+)?|type\s+(?P<alias>[A-Za-z_$][\w$]*)\s*=)"
    r"\s*\{(?P<body>[^{}]*)\}",
    re.DOTALL,
)
_TYPE_FIELD_RE = re.compile(
    r"(?:^|[;,\n])\s*(?:readonly\s+)?"
    r"(?P<name>[A-Za-z_$][\w$]*|[\"'][^\"']+[\"'])"
    r"(?P<optional>\?)?\s*:\s*(?P<type>[^;,\n]+)"
)


@dataclass(frozen=True)
class AdapterCapability:
    status: CapabilityStatus
    reason: str
    confidence: float
    adapter: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SourceDocument:
    path: Path
    relative_path: str
    content: str


@dataclass(frozen=True)
class ModuleSemantics:
    relative_path: str
    framework: str
    capability: AdapterCapability
    facts: SourceFacts
    contracts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedSymbol:
    status: str
    module_path: str | None
    local_name: str | None
    export_name: str | None
    package: str | None
    provenance: str
    confidence: float


@dataclass(frozen=True)
class SourceOwnership:
    status: str
    confidence: float
    provenance: str
    candidates: tuple[str, ...]

    @property
    def source_targets(self) -> tuple[str, ...]:
        return self.candidates if self.status == "resolved" else ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "candidates": list(self.candidates),
        }


class SemanticAdapter(Protocol):
    name: str

    def supports(self, document: SourceDocument) -> bool: ...

    def extract(self, document: SourceDocument) -> ModuleSemantics: ...


@dataclass(frozen=True)
class SemanticAdapterRegistry:
    adapters: tuple[SemanticAdapter, ...]

    def select(self, document: SourceDocument) -> SemanticAdapter:
        for adapter in self.adapters:
            if adapter.supports(document):
                return adapter
        return _UnsupportedAdapter()

    def extract(self, document: SourceDocument) -> ModuleSemantics:
        return self.select(document).extract(document)


@dataclass(frozen=True)
class _ApplicationIndex:
    modules: Mapping[str, ModuleSemantics]
    extensions: tuple[str, ...]
    exact_selectors: Mapping[str, tuple[str, ...]]
    heuristic_selectors: Mapping[str, tuple[str, ...]]
    routes: Mapping[str, tuple[str, ...]]
    network_symbols: Mapping[str, Mapping[str, NetworkCallFact]]


@dataclass(frozen=True)
class ApplicationSemantics:
    root: Path
    scope: Path
    modules: tuple[ModuleSemantics, ...]
    resolution_issues: tuple[str, ...] = ()
    _index: _ApplicationIndex = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_index", _build_application_index(self.modules))

    def module(self, relative_path: str) -> ModuleSemantics | None:
        return self._index.modules.get(relative_path)

    def resolve_import(self, module_path: str, specifier: str) -> str | None:
        return self._resolve_specifier(module_path, specifier)

    def resolve_render(self, module_path: str, binding: str) -> ResolvedSymbol:
        module = self.module(module_path)
        if module is None:
            return _unresolved_symbol("rendering module absent")
        facts = module.facts
        local_component = next(
            (item for item in facts.declared_ui_modules if item.name == binding),
            None,
        )
        if local_component is not None:
            exported = next(
                (item.exported for item in facts.exports if item.local == binding),
                binding,
            )
            return ResolvedSymbol(
                "resolved",
                module_path,
                binding,
                exported,
                None,
                "component:local-binding",
                1.0,
            )

        root_binding, _, member = binding.partition(".")
        imported = next(
            (item for item in facts.import_aliases if item.local == root_binding),
            None,
        )
        if imported is None:
            return _unresolved_symbol("render binding has no lexical import")
        export_name = (
            member if imported.kind == "namespace" and member else imported.imported
        )
        target_module = self._resolve_specifier(module_path, imported.source)
        if target_module is None:
            if imported.source.startswith((".", "/")):
                return _unresolved_symbol("local render import target absent")
            return ResolvedSymbol(
                "external",
                None,
                None,
                export_name,
                imported.source,
                "component:package-import",
                1.0,
            )
        return self._resolve_export(
            target_module, export_name, ()
        ) or _unresolved_symbol("render export unresolved through module graph")

    def source_ownership(
        self,
        *,
        selector: str,
        tag: str,
        source_hint: str = "",
        source_selectors: Iterable[str] = (),
        runtime_url: str = "",
        route_sources: tuple[str, ...] | None = None,
    ) -> SourceOwnership:
        if source_hint in self._index.modules:
            return SourceOwnership(
                "resolved", 1.0, "runtime:source-hook", (source_hint,)
            )
        candidates = tuple(dict.fromkeys((selector, *source_selectors)))
        route_sources = (
            self.route_sources(runtime_url) if route_sources is None else route_sources
        )
        exact = _matching_sources(self._index.exact_selectors, candidates)
        if len(exact) == 1:
            return SourceOwnership(
                "resolved",
                1.0,
                "selector:exact",
                exact,
            )
        if exact:
            narrowed = _narrow_sources(exact, route_sources)
            if len(narrowed) == 1:
                return SourceOwnership(
                    "resolved", 0.9, "selector:exact+route", narrowed
                )
            return SourceOwnership("ambiguous", 0.0, "selector:ambiguous", narrowed)
        tag_selector = tag.lower()
        specific_candidates = tuple(
            candidate for candidate in candidates if candidate.lower() != tag_selector
        )
        for heuristic_candidates in (specific_candidates, (tag_selector,)):
            heuristic = _matching_sources(
                self._index.heuristic_selectors,
                heuristic_candidates,
            )
            if len(heuristic) == 1:
                return SourceOwnership(
                    "resolved", 0.65, "selector:unique-heuristic", heuristic
                )
            if heuristic:
                narrowed = _narrow_sources(heuristic, route_sources)
                if len(narrowed) == 1:
                    return SourceOwnership(
                        "resolved", 0.6, "selector:heuristic+route", narrowed
                    )
                return SourceOwnership(
                    "ambiguous", 0.0, "selector:ambiguous-heuristic", narrowed
                )
        if len(route_sources) == 1:
            return SourceOwnership(
                "resolved", 0.4, "route:unique-context", route_sources
            )
        if route_sources:
            return SourceOwnership(
                "ambiguous", 0.0, "route:ambiguous-context", route_sources
            )
        return SourceOwnership("unresolved", 0.0, "source-signature:absent", ())

    def route_sources(self, runtime_url: str) -> tuple[str, ...]:
        runtime_route = _normalize_route_path(runtime_url)
        if not runtime_route:
            return ()
        exact = self._index.routes.get(runtime_route, ())
        route_sources = set(exact)
        matched_routes = {runtime_route} if exact else set()
        if not route_sources:
            matching_routes: dict[str, tuple[str, ...]] = {}
            for route, sources in self._index.routes.items():
                if _route_matches(route, runtime_route):
                    matching_routes[route] = sources
            matched_routes.update(_most_specific_routes(matching_routes))
            for route in matched_routes:
                route_sources.update(matching_routes[route])

        route_roots: set[str] = set()
        for source in sorted(route_sources):
            module = self.module(source)
            if module is None:
                continue
            matched_route_facts = tuple(
                route
                for route in module.facts.routes
                if _normalize_route_pattern(route.name) in matched_routes
            )
            route_line_counts: dict[int, int] = {}
            for route in module.facts.routes:
                route_line_counts[route.line] = route_line_counts.get(route.line, 0) + 1
            route_lines = {
                route.line
                for route in matched_route_facts
                if not route.target or route_line_counts[route.line] == 1
            }
            for route in matched_route_facts:
                if not route.target:
                    continue
                if route.target.startswith((".", "/")):
                    target_module = self._resolve_specifier(source, route.target)
                    if target_module is not None:
                        route_roots.add(target_module)
                    continue
                resolved = self.resolve_render(source, route.target)
                if resolved.status == "resolved" and resolved.module_path is not None:
                    route_roots.add(resolved.module_path)
            for rendered in module.facts.rendered_bindings:
                if rendered.line not in route_lines:
                    continue
                resolved = self.resolve_render(source, rendered.binding)
                if resolved.status == "resolved" and resolved.module_path is not None:
                    route_roots.add(resolved.module_path)

        pending = sorted(route_roots, reverse=True)
        route_sources.update(route_roots)
        while pending:
            source = pending.pop()
            module = self.module(source)
            if module is None:
                continue
            for rendered in module.facts.rendered_bindings:
                resolved = self.resolve_render(source, rendered.binding)
                target = resolved.module_path
                if resolved.status != "resolved" or target is None:
                    continue
                if target not in route_sources:
                    route_sources.add(target)
                    pending.append(target)
        return tuple(sorted(route_sources))

    def _resolve_specifier(self, source_path: str, specifier: str) -> str | None:
        if not specifier.startswith((".", "/")):
            return None
        source = PurePosixPath(source_path)
        if specifier.startswith("/"):
            web_path = PurePosixPath(specifier.lstrip("/"))
            bases = (
                [source.parent / web_path]
                if source.suffix.lower() in {".html", ".htm"}
                else []
            )
            scope_root = self.scope if self.scope.is_dir() else self.scope.parent
            try:
                scope_relative = PurePosixPath(
                    scope_root.relative_to(self.root).as_posix()
                )
            except ValueError:
                scope_relative = PurePosixPath()
            bases = list(dict.fromkeys((*bases, scope_relative / web_path, web_path)))
        else:
            bases = [source.parent / specifier]
        for base in bases:
            normalized = _normalize_module_path(base)
            candidates = [normalized]
            if not PurePosixPath(normalized).suffix:
                candidates.extend(
                    f"{normalized}{extension}" for extension in self._index.extensions
                )
                candidates.extend(
                    f"{normalized}/index{extension}"
                    for extension in self._index.extensions
                )
            for candidate in candidates:
                if candidate in self._index.modules:
                    return candidate
        return None

    def _resolve_export(
        self,
        module_path: str,
        export_name: str,
        visited: tuple[tuple[str, str], ...],
    ) -> ResolvedSymbol | None:
        marker = (module_path, export_name)
        if marker in visited:
            return None
        module = self.module(module_path)
        if module is None:
            return None
        facts = module.facts
        trail = (*visited, marker)
        export = next(
            (item for item in facts.exports if item.exported == export_name),
            None,
        )
        if export is None:
            for wildcard in (
                item for item in facts.exports if item.exported == "*" and item.source
            ):
                target = self._resolve_specifier(module_path, wildcard.source or "")
                resolved = (
                    self._resolve_export(target, export_name, trail)
                    if target is not None
                    else None
                )
                if resolved is not None:
                    return resolved
        if export is not None and export.source:
            target = self._resolve_specifier(module_path, export.source)
            return (
                self._resolve_export(target, export.local, trail)
                if target is not None
                else None
            )
        local = export.local if export is not None else export_name
        imported = next(
            (item for item in facts.import_aliases if item.local == local),
            None,
        )
        if imported is not None:
            target = self._resolve_specifier(module_path, imported.source)
            if target is None:
                return None
            imported_name = local if imported.kind == "namespace" else imported.imported
            return self._resolve_export(target, imported_name, trail)
        if any(item.name == local for item in facts.declared_ui_modules):
            provenance = "component:module-export"
        elif local in self._index.network_symbols.get(module_path, {}):
            provenance = "network:module-export"
        elif any(item.name == local for item in facts.callables):
            provenance = "callable:module-export"
        else:
            return None
        return ResolvedSymbol(
            "resolved", module_path, local, export_name, None, provenance, 1.0
        )


class _ScriptAdapter:
    name = "javascript-typescript"

    def supports(self, document: SourceDocument) -> bool:
        return document.path.suffix.lower() in _SCRIPT_EXTENSIONS

    def extract(self, document: SourceDocument) -> ModuleSemantics:
        facts = extract_source_facts(document.path, document.content)
        if facts is None:
            capability = AdapterCapability(
                "unsupported",
                f"no qualified AST grammar for {document.path.suffix.lower()}",
                0.0,
                self.name,
            )
            return _module(document, _framework_for_script(document, ()), capability)
        framework = _framework_for_script(document, facts.imports)
        return _module(
            document,
            framework,
            AdapterCapability(
                "native",
                "qualified Tree-sitter grammar",
                facts.confidence,
                self.name,
            ),
            facts,
        )


class _EmbeddedMarkupAdapter:
    name = "embedded-markup"

    def supports(self, document: SourceDocument) -> bool:
        return document.path.suffix.lower() in _EMBEDDED_EXTENSIONS

    def extract(self, document: SourceDocument) -> ModuleSemantics:
        extension = document.path.suffix.lower()
        framework = {
            ".astro": "astro",
            ".svelte": "svelte",
            ".vue": "vue",
        }.get(extension, "html")
        capability = _degraded_capability(framework, self.name)
        script = _embedded_script(document.content, framework)
        if script is None:
            module = _module(document, framework, capability)
        else:
            body, line_offset, script_extension = script
            facts = extract_source_facts(
                document.path.with_suffix(script_extension),
                "\n" * line_offset + body,
            )
            module = _module(
                document,
                framework,
                capability,
                facts,
                extractor="tree-sitter+degraded-markup" if facts else None,
            )
        return replace(
            module, facts=_merge_markup_facts(module.facts, document, framework)
        )


class _StyleAdapter:
    name = "styles"

    def supports(self, document: SourceDocument) -> bool:
        return document.path.suffix.lower() in _STYLE_EXTENSIONS

    def extract(self, document: SourceDocument) -> ModuleSemantics:
        extension = document.path.suffix.lower()
        status: CapabilityStatus = "native" if has_ast_for(extension) else "unsupported"
        return _module(
            document,
            "styles",
            AdapterCapability(
                status,
                (
                    "qualified Tree-sitter grammar"
                    if status == "native"
                    else f"no qualified AST grammar for {extension}"
                ),
                1.0 if status == "native" else 0.0,
                self.name,
            ),
        )


class _UnsupportedAdapter:
    name = "unsupported"

    def supports(self, document: SourceDocument) -> bool:
        return True

    def extract(self, document: SourceDocument) -> ModuleSemantics:
        return _module(
            document,
            "unknown",
            AdapterCapability(
                "unsupported",
                f"no semantic adapter for {document.path.suffix.lower() or '<none>'}",
                0.0,
                self.name,
            ),
        )


DEFAULT_ADAPTER_REGISTRY = SemanticAdapterRegistry(
    (_ScriptAdapter(), _EmbeddedMarkupAdapter(), _StyleAdapter())
)


def build_application_semantics(
    root: str | Path,
    scope: str | Path,
    documents: Iterable[SourceDocument],
    *,
    registry: SemanticAdapterRegistry = DEFAULT_ADAPTER_REGISTRY,
) -> ApplicationSemantics:
    """Extract once, then resolve imported network behavior across modules."""

    extracted: list[ModuleSemantics] = []
    for document in documents:
        extracted.append(registry.extract(document))
    modules = tuple(sorted(extracted, key=lambda module: module.relative_path))
    application = ApplicationSemantics(
        Path(root).resolve(),
        Path(scope).resolve(),
        modules,
    )
    resolved_modules, issues = _resolve_network_calls(application)
    return replace(application, modules=resolved_modules, resolution_issues=issues)


def _module(
    document: SourceDocument,
    framework: str,
    capability: AdapterCapability,
    facts: SourceFacts | None = None,
    *,
    extractor: str | None = None,
) -> ModuleSemantics:
    source_facts = facts or SourceFacts(document.path, document.path.suffix.lower())
    source_facts = replace(
        source_facts,
        path=document.path,
        extension=document.path.suffix.lower(),
        routes=tuple(dict.fromkeys((*source_facts.routes, *_file_routes(document)))),
        extractor=extractor
        or (
            source_facts.extractor
            if facts is not None
            else f"adapter:{capability.adapter}"
        ),
        confidence=min(source_facts.confidence, capability.confidence)
        if facts is not None
        else capability.confidence,
    )
    return ModuleSemantics(
        document.relative_path,
        framework,
        capability,
        source_facts,
        extract_type_contracts(document.content),
    )


def _framework_for_script(
    document: SourceDocument,
    imports: tuple[str, ...],
) -> str:
    extension = document.path.suffix.lower()
    normalized = f"/{document.relative_path.lower()}"
    if re.search(r"/(?:app|pages)/", normalized) and document.path.stem in {
        "page",
        "layout",
        "index",
    }:
        return "next"
    if "@angular/core" in imports:
        return "angular"
    if "react" in imports or extension in {".jsx", ".tsx"}:
        return "react"
    return "typescript" if extension == ".ts" else "javascript"


def _degraded_capability(framework: str, adapter: str) -> AdapterCapability:
    return AdapterCapability(
        "degraded",
        (
            f"{framework} framework grammar unavailable; embedded script uses "
            "shared JS/TS parser and template evidence is conservative"
        ),
        0.65,
        adapter,
    )


def _embedded_script(
    content: str,
    framework: str,
) -> tuple[str, int, str] | None:
    match = (
        _ASTRO_SCRIPT_RE.search(content)
        if framework == "astro"
        else _SCRIPT_RE.search(content)
    )
    if match is None:
        return None
    body = match.group("body")
    line_offset = content.count("\n", 0, match.start("body"))
    attrs = match.groupdict().get("attrs") or ""
    extension = ".ts" if re.search(r"\blang\s*=\s*[\"']ts[\"']", attrs) else ".js"
    return body, line_offset, extension


def _merge_markup_facts(
    facts: SourceFacts,
    document: SourceDocument,
    framework: str,
) -> SourceFacts:
    components = list(facts.declared_ui_modules)
    if document.path.suffix.lower() in {".astro", ".svelte", ".vue"}:
        name = document.path.stem
        if not any(item.name == name for item in components):
            components.append(SourceOccurrence(name, 1))

    renders = list(facts.rendered_bindings)
    regions = list(facts.regions)
    actions = list(facts.actions)
    states = list(facts.states)
    selectors = list(facts.selectors)
    for match in _TAG_RE.finditer(document.content):
        tag = match.group("tag")
        lowered = tag.lower()
        line = _line_number(document.content, match.start())
        if tag[:1].isupper():
            renders.append(RenderFact(tag, line))
        if lowered in _REGION_TAGS:
            regions.append(SourceOccurrence(lowered, line))
        attrs = match.group("attrs")
        for action in _ACTION_RE.finditer(attrs):
            actions.append(SourceOccurrence(action.group("name").title(), line))
        selectors.append(SelectorFact(lowered, line, "heuristic"))
        for attribute in _ATTRIBUTE_RE.finditer(attrs):
            name = attribute.group("name")
            value = attribute.group("value")
            selectors.extend(selector_facts(name, value, line))

    if framework == "vue":
        state_pattern = re.compile(
            r"\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:ref|reactive)\s*\("
        )
    elif framework == "svelte":
        state_pattern = re.compile(r"\blet\s+([A-Za-z_$][\w$]*)\s*=")
    else:
        state_pattern = None
    if state_pattern is not None:
        states.extend(
            SourceOccurrence(
                match.group(1),
                _line_number(document.content, match.start()),
            )
            for match in state_pattern.finditer(document.content)
        )

    routes = list(facts.routes)
    normalized = PurePosixPath(document.relative_path)
    if framework == "astro" and "pages" in normalized.parts:
        page_index = normalized.parts.index("pages")
        parts = list(normalized.parts[page_index + 1 :])
        if parts:
            parts[-1] = PurePosixPath(parts[-1]).stem
            if parts[-1] == "index":
                parts.pop()
            routes.append(SourceOccurrence("/" + "/".join(parts), 1))
    return replace(
        facts,
        imports=tuple(
            dict.fromkeys((*facts.imports, *_markup_imports(document.content)))
        ),
        declared_ui_modules=tuple(dict.fromkeys(components)),
        rendered_bindings=tuple(dict.fromkeys(renders)),
        regions=tuple(dict.fromkeys(regions)),
        actions=tuple(actions),
        states=tuple(dict.fromkeys(states)),
        routes=tuple(dict.fromkeys(routes)),
        selectors=tuple(dict.fromkeys(selectors)),
    )


def _build_application_index(
    modules: tuple[ModuleSemantics, ...],
) -> _ApplicationIndex:
    by_path = {module.relative_path: module for module in modules}
    exact_selectors: dict[str, set[str]] = {}
    heuristic_selectors: dict[str, set[str]] = {}
    routes: dict[str, set[str]] = {}
    network_symbols: dict[str, Mapping[str, NetworkCallFact]] = {}
    for module in modules:
        for selector in module.facts.selectors:
            index = (
                exact_selectors if selector.strength == "exact" else heuristic_selectors
            )
            index.setdefault(selector.selector, set()).add(module.relative_path)
        for route in module.facts.routes:
            normalized_route = _normalize_route_pattern(route.name)
            if normalized_route:
                routes.setdefault(normalized_route, set()).add(module.relative_path)
        symbols = {item.owner: item for item in module.facts.network_symbols}
        for name, symbol in tuple(symbols.items()):
            symbols.setdefault(name.partition(".")[0], symbol)
        network_symbols[module.relative_path] = MappingProxyType(symbols)
    return _ApplicationIndex(
        modules=MappingProxyType(by_path),
        extensions=tuple(
            sorted(
                {
                    PurePosixPath(path).suffix
                    for path in by_path
                    if PurePosixPath(path).suffix
                }
            )
        ),
        exact_selectors=_freeze_source_index(exact_selectors),
        heuristic_selectors=_freeze_source_index(heuristic_selectors),
        routes=_freeze_source_index(routes),
        network_symbols=MappingProxyType(network_symbols),
    )


def _freeze_source_index(
    index: Mapping[str, set[str]],
) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType(
        {selector: tuple(sorted(paths)) for selector, paths in index.items()}
    )


def _matching_sources(
    index: Mapping[str, tuple[str, ...]],
    selectors: Iterable[str],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                source
                for selector in selectors
                for source in index.get(selector, ())
                if selector
            }
        )
    )


def _narrow_sources(
    sources: tuple[str, ...],
    route_sources: tuple[str, ...],
) -> tuple[str, ...]:
    if not route_sources:
        return sources
    narrowed = tuple(sorted(set(sources) & set(route_sources)))
    return narrowed or sources


def _normalize_route_path(value: str) -> str:
    if not value:
        return ""
    path = urlsplit(value).path or "/"
    normalized = "/" + "/".join(part for part in path.split("/") if part)
    return "/" if normalized == "/" else normalized.rstrip("/")


def _normalize_route_pattern(value: str) -> str:
    if not value:
        return ""
    normalized = "/" + "/".join(part for part in value.split("/") if part)
    return "/" if normalized == "/" else normalized.rstrip("/")


def _route_matches(pattern: str, runtime_route: str) -> bool:
    pattern_parts = pattern.strip("/").split("/") if pattern != "/" else []
    runtime_parts = runtime_route.strip("/").split("/") if runtime_route != "/" else []
    runtime_indexes = {0}
    for index, pattern_part in enumerate(pattern_parts):
        if (
            pattern_part == "*"
            or pattern_part.startswith(":")
            and pattern_part.endswith("*")
        ):
            return index == len(pattern_parts) - 1 and any(
                runtime_index <= len(runtime_parts) for runtime_index in runtime_indexes
            )
        optional = pattern_part.endswith("?")
        expected_part = pattern_part[:-1] if optional else pattern_part
        next_runtime_indexes: set[int] = set()
        for runtime_index in runtime_indexes:
            if optional:
                next_runtime_indexes.add(runtime_index)
            if runtime_index >= len(runtime_parts):
                continue
            if (
                expected_part.startswith(":")
                or expected_part == runtime_parts[runtime_index]
            ):
                next_runtime_indexes.add(runtime_index + 1)
        if not next_runtime_indexes:
            return False
        runtime_indexes = next_runtime_indexes
    return len(runtime_parts) in runtime_indexes


def _most_specific_routes(routes: Iterable[str]) -> tuple[str, ...]:
    candidates = tuple(sorted(set(routes)))
    specificity: dict[str, tuple[int, ...]] = {}
    for route in candidates:
        parts = route.strip("/").split("/") if route != "/" else []
        splat_count = sum(
            part == "*" or part.startswith(":") and part.endswith("*") for part in parts
        )
        optional_count = sum(part.endswith("?") for part in parts)
        static_count = sum(not part.startswith(":") and part != "*" for part in parts)
        specificity[route] = (
            static_count,
            len(parts) - optional_count - splat_count,
            len(parts) - splat_count,
            -optional_count,
            -splat_count,
        )

    specificity_values = tuple(sorted(set(specificity.values())))
    if len(specificity_values) > _ROUTE_SPECIFICITY_VECTOR_BUDGET:
        return candidates
    nondominated = {
        route_specificity
        for route_specificity in specificity_values
        if not any(
            other != route_specificity
            and all(
                other_value >= route_value
                for other_value, route_value in zip(
                    other, route_specificity, strict=True
                )
            )
            for other in specificity_values
        )
    }
    return tuple(route for route in candidates if specificity[route] in nondominated)


def _resolve_network_calls(
    application: ApplicationSemantics,
) -> tuple[tuple[ModuleSemantics, ...], tuple[str, ...]]:
    modules: list[ModuleSemantics] = []
    issues: list[str] = []
    for module in application.modules:
        facts = module.facts
        resolved_calls = list(facts.network_calls)
        known_calls = {(call.target, call.line) for call in resolved_calls}
        imports = {item.local: item for item in facts.import_aliases}
        bindings = {item.local: item.target for item in facts.bindings}
        for call in facts.calls:
            if (call.target, call.line) in known_calls:
                continue
            imported_binding = _import_binding(call.target, imports, bindings)
            if imported_binding is None:
                continue
            imported, members = imported_binding
            target_module = application._resolve_specifier(
                module.relative_path,
                imported.source,
            )
            if target_module is None:
                if _looks_network_shaped(
                    call.target,
                    call.arguments,
                    allow_url_argument=False,
                ):
                    resolved_calls.append(
                        _unresolved_network_call(
                            call,
                            f"external import {imported.source!r} has no local symbol graph",
                        )
                    )
                continue
            if imported.kind == "namespace":
                if not members:
                    continue
                export_name, *member_parts = members
            else:
                export_name = imported.imported
                member_parts = list(members)
            symbol = application._resolve_export(target_module, export_name, ())
            if (
                symbol is None
                or symbol.module_path is None
                or symbol.local_name is None
            ):
                issue = (
                    f"{module.relative_path}:{call.line}: unresolved import chain "
                    f"for {call.target}"
                )
                if _looks_network_shaped(call.target, call.arguments):
                    issues.append(issue)
                    resolved_calls.append(_unresolved_network_call(call, issue))
                continue
            capability_name = ".".join((symbol.local_name, *member_parts)).rstrip(".")
            capability = application._index.network_symbols.get(
                symbol.module_path, {}
            ).get(capability_name)
            if capability is None:
                if _looks_network_shaped(call.target, call.arguments):
                    resolved_calls.append(
                        _unresolved_network_call(
                            call,
                            (
                                f"resolved local symbol {capability_name!r}; "
                                "network behavior is unavailable"
                            ),
                        )
                    )
                continue
            request_refs, response_refs = _resolved_type_references(
                application,
                symbol.module_path,
                symbol.local_name,
                capability,
                call,
            )
            expression = call.arguments[0] if call.arguments else None
            literal_url = literal_text(expression)
            url = literal_url or capability.url
            url_expression = (
                expression if literal_url is not None else capability.url_expression
            )
            resolved_calls.append(
                NetworkCallFact(
                    target=call.target,
                    client_family=capability.client_family,
                    method=call.method_hint
                    or capability.method
                    or _method_from_target(call.target),
                    url=url,
                    url_expression=url_expression,
                    line=call.line,
                    dynamic=(
                        capability.dynamic
                        if literal_url is None
                        else "${" in literal_url
                    ),
                    owner=call.owner,
                    resolution="resolved",
                    unresolved_evidence=None,
                    request_type_refs=request_refs,
                    response_type_refs=response_refs,
                )
            )
        modules.append(
            replace(module, facts=replace(facts, network_calls=tuple(resolved_calls)))
        )
    return tuple(modules), tuple(dict.fromkeys(issues))


def _looks_network_shaped(
    target: str,
    arguments: tuple[str, ...],
    *,
    allow_url_argument: bool = True,
) -> bool:
    method = target.rsplit(".", 1)[-1]
    if method in {"create", "extend"}:
        return False
    return bool(
        method.lower() in _NETWORK_METHODS
        or _QUERY_HOOK_RE.fullmatch(method)
        or (allow_url_argument and arguments and _looks_like_url(arguments[0]))
    )


def _import_binding(
    target: str,
    imports: dict[str, ImportAlias],
    bindings: dict[str, str],
) -> tuple[ImportAlias, tuple[str, ...]] | None:
    visited: set[str] = set()
    root, *members = target.split(".")
    current = root
    while current not in visited:
        visited.add(current)
        imported = imports.get(current)
        if imported is not None:
            return imported, tuple(members)
        binding = bindings.get(current)
        if binding is None:
            return None
        current, *bound_members = binding.split(".")
        members = [*bound_members, *members]
    return None


def _resolved_type_references(
    application: ApplicationSemantics,
    module_path: str,
    local_name: str,
    capability: NetworkCallFact,
    call: CallFact,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    module = application.module(module_path)
    definition = (
        next(
            (
                item
                for item in module.facts.callables
                if item.name in {local_name, capability.owner}
            ),
            None,
        )
        if module is not None
        else None
    )
    substitutions = (
        dict(zip(definition.type_parameters, call.type_arguments, strict=False))
        if definition is not None
        else {}
    )

    def substitute(references: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                resolved
                for reference in references
                for resolved in substitutions.get(reference, (reference,))
            )
        )

    request_refs = substitute(capability.request_type_refs)
    response_refs = substitute(capability.response_type_refs)
    direct_request, direct_response = classify_network_type_references(
        capability.client_family,
        call.target,
        call.type_arguments,
    )
    return request_refs or direct_request, response_refs or direct_response


def _unresolved_network_call(call: CallFact, evidence: str) -> NetworkCallFact:
    expression = call.arguments[0] if call.arguments else None
    url = literal_text(expression)
    request_refs, response_refs = classify_network_type_references(
        "imported-client",
        call.target,
        call.type_arguments,
    )
    return NetworkCallFact(
        target=call.target,
        client_family="imported-client",
        method=call.method_hint or _method_from_target(call.target),
        url=url,
        url_expression=expression,
        line=call.line,
        dynamic=url is None or "${" in url,
        owner=call.owner,
        resolution="unresolved",
        unresolved_evidence=evidence,
        request_type_refs=request_refs,
        response_type_refs=response_refs,
    )


def _looks_like_url(value: str) -> bool:
    literal = literal_text(value)
    return bool(
        literal
        and (literal.startswith(("/", "http://", "https://")) or "${" in literal)
    )


def _method_from_target(target: str) -> str | None:
    method = target.rsplit(".", 1)[-1].upper()
    if method in _HTTP_METHODS:
        return method
    aliases = {"CREATE": "POST", "UPDATE": "PUT", "REMOVE": "DELETE", "LIST": "GET"}
    return aliases.get(method)


def _normalize_module_path(path: PurePosixPath) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _file_routes(document: SourceDocument) -> tuple[SourceOccurrence, ...]:
    path = PurePosixPath(document.relative_path)
    parts = list(path.parts)
    if parts[:2] == ["src", "routes"] and path.name == "+page.svelte":
        route_parts = [
            _normalize_route_segment(part)
            for part in parts[2:-1]
            if not part.startswith("(")
        ]
        return (SourceOccurrence("/" + "/".join(filter(None, route_parts)), 1),)
    if "app" in parts and path.stem == "page":
        index = parts.index("app")
        route_parts = [
            _normalize_route_segment(part)
            for part in parts[index + 1 : -1]
            if not part.startswith(("(", "@"))
        ]
        return (SourceOccurrence("/" + "/".join(filter(None, route_parts)), 1),)
    if "pages" in parts:
        index = parts.index("pages")
        route_parts = parts[index + 1 :]
        if route_parts:
            route_parts[-1] = path.stem
            if route_parts[-1] == "index":
                route_parts.pop()
            return (
                SourceOccurrence(
                    "/"
                    + "/".join(_normalize_route_segment(part) for part in route_parts),
                    1,
                ),
            )
    return ()


def _normalize_route_segment(segment: str) -> str:
    if segment.startswith("[[...") and segment.endswith("]]"):
        return f":{segment[5:-2]}*"
    if segment.startswith("[...") and segment.endswith("]"):
        return f":{segment[4:-1]}*"
    if segment.startswith("[") and segment.endswith("]"):
        return f":{segment[1:-1]}"
    return segment


def _markup_imports(content: str) -> tuple[str, ...]:
    imports: list[str] = []
    for match in re.finditer(r"<(script|link)\b[^>]*>", content, re.IGNORECASE):
        tag_name = match.group(1).lower()
        tag = match.group(0)
        attribute_name = "src" if tag_name == "script" else "href"
        if tag_name == "link" and not re.search(
            r"""\brel\s*=\s*["'][^"']*(?:stylesheet|modulepreload|preload)""",
            tag,
            re.IGNORECASE,
        ):
            continue
        attribute = re.search(
            rf"""\b{attribute_name}\s*=\s*["'](?P<source>[^"']+)["']""",
            tag,
            re.IGNORECASE,
        )
        if attribute is None:
            continue
        source = attribute.group("source").split("?", 1)[0].split("#", 1)[0]
        if not source or source.startswith(("data:", "http://", "https://", "//")):
            continue
        imports.append(source if source.startswith((".", "/")) else f"./{source}")
    return tuple(dict.fromkeys(imports))


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _unresolved_symbol(reason: str) -> ResolvedSymbol:
    return ResolvedSymbol("unresolved", None, None, None, None, reason, 0.0)


def extract_type_contracts(content: str) -> dict[str, dict[str, Any]]:
    """Extract conservative object contracts inside the selected JS/TS adapter."""

    contracts: dict[str, dict[str, Any]] = {}
    for match in _TYPE_BLOCK_RE.finditer(content):
        name = match.group("interface") or match.group("alias")
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for field_match in _TYPE_FIELD_RE.finditer(match.group("body")):
            field_name = field_match.group("name").strip("\"'")
            properties[field_name] = _typescript_type_shape(
                field_match.group("type").strip()
            )
            if field_match.group("optional") is None:
                required.append(field_name)
        contracts[name] = {
            "type": "object",
            "properties": dict(sorted(properties.items())),
            "required": sorted(required),
        }
    return contracts


def _typescript_type_shape(value: str) -> dict[str, Any]:
    union = [item.strip() for item in value.split("|")]
    nullable = any(item in {"null", "undefined"} for item in union)
    concrete = [item for item in union if item not in {"null", "undefined"}]
    literals = [
        item[1:-1]
        for item in concrete
        if len(item) >= 2 and item[0] == item[-1] and item[0] in {"'", '"'}
    ]
    if literals and len(literals) == len(concrete):
        result: dict[str, Any] = {"type": "string", "enum": sorted(literals)}
    else:
        candidate = concrete[0] if len(concrete) == 1 else value
        array_match = re.fullmatch(r"(?:Array|ReadonlyArray)<(.+)>", candidate)
        if candidate.endswith("[]"):
            result = {
                "type": "array",
                "items": _typescript_type_shape(candidate[:-2].strip()),
            }
        elif array_match:
            result = {
                "type": "array",
                "items": _typescript_type_shape(array_match.group(1).strip()),
            }
        else:
            scalar = {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "object": "object",
                "unknown": "unknown",
                "any": "unknown",
            }
            result = {"type": scalar.get(candidate, "object")}
            if candidate not in scalar:
                result["reference"] = candidate
    if nullable:
        result["nullable"] = True
    return result
