"""Parse source once into immutable facts shared by analysis consumers.

Tree-sitter nodes stay private to this module. Downstream analyzer and mapping
code consume normalized values with source anchors, provenance, and confidence.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

tree_sitter = None
_CORE_AST_ERROR: str | None = None
try:
    import tree_sitter
except ImportError as exc:
    _CORE_AST_ERROR = f"{type(exc).__name__}: {exc}"

_AST_LANGUAGES: dict[str, object] = {}
AST_CAPABILITIES: dict[str, dict[str, object]] = {}


def _load_grammar(
    name: str,
    module_name: str,
    factory_name: str,
    extensions: tuple[str, ...],
) -> None:
    """Register one grammar without disabling unrelated AST languages."""
    error = _CORE_AST_ERROR
    language = None
    if tree_sitter is not None:
        try:
            module = importlib.import_module(module_name)
            language = tree_sitter.Language(getattr(module, factory_name)())
        except (ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
    if language is not None:
        for extension in extensions:
            _AST_LANGUAGES[extension] = language
    AST_CAPABILITIES[name] = {
        "available": language is not None,
        "extensions": extensions,
        "error": error,
    }


_load_grammar(
    "javascript", "tree_sitter_javascript", "language", (".js", ".jsx", ".mjs", ".cjs")
)
_load_grammar("typescript", "tree_sitter_typescript", "language_typescript", (".ts",))
_load_grammar("tsx", "tree_sitter_typescript", "language_tsx", (".tsx",))
_load_grammar("css", "tree_sitter_css", "language", (".css", ".scss", ".less"))

HAS_AST = any(capability["available"] for capability in AST_CAPABILITIES.values())


def ast_capabilities() -> dict[str, dict[str, object]]:
    """Return serializable per-language AST availability and failure details."""
    return {
        name: {
            **capability,
            "extensions": list(capability["extensions"]),
        }
        for name, capability in AST_CAPABILITIES.items()
    }


def has_ast_for(ext: str) -> bool:
    """Report whether an AST parser is available for one file extension."""
    return ext.lower() in _AST_LANGUAGES


def get_parser(ext: str):
    """Create a parser for one source extension, when its grammar is available."""
    language = _AST_LANGUAGES.get(ext.lower())
    if tree_sitter is None or language is None:
        return None
    return tree_sitter.Parser(language)


_USESTATE_BINDING_RE = re.compile(
    r"\b(?:const|let|var)\s+\[\s*(?P<state>[A-Za-z_$][\w$]*)\s*,"
    r"\s*[A-Za-z_$][\w$]*\s*\]\s*=\s*(?:React\.)?useState\b"
)
_IDENTIFIER_TOKEN_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)
_ANIMATION_STATE_TOKENS = frozenset(
    {
        "x",
        "y",
        "top",
        "left",
        "right",
        "bottom",
        "opacity",
        "scale",
        "rotate",
        "position",
        "transform",
    }
)
_ANIMATION_STATE_PREFIXES = ("animat", "transit", "translate")
_ROUTE_ATTRIBUTE_RE = re.compile(r"^path\s*=\s*[\"']([^\"']+)[\"']$")
_ACTION_ATTRIBUTE_RE = re.compile(r"^on([A-Z][A-Za-z0-9_]*)\b")
_ROUTER_IDENTIFIERS = frozenset(
    {"createBrowserRouter", "createRoutesFromElements", "router", "routes"}
)
_REGION_TAGS = frozenset(
    {
        "header",
        "nav",
        "main",
        "aside",
        "section",
        "article",
        "footer",
        "form",
        "table",
        "dialog",
    }
)
_SCRIPT_EXTENSIONS = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_TYPE_CONTAINERS = frozenset(
    {
        "Array",
        "AxiosPromise",
        "AxiosResponse",
        "Partial",
        "Pick",
        "Promise",
        "Readonly",
        "ReadonlyArray",
        "Record",
        "Response",
    }
)


@dataclass(frozen=True)
class SourceOccurrence:
    """One named source fact with a one-based source line."""

    name: str
    line: int
    owner: str = field(default="", compare=False)
    target: str = field(default="", compare=False)


@dataclass(frozen=True)
class ImportAlias:
    """One import binding resolved to its module symbol."""

    source: str
    imported: str
    local: str
    kind: str = "named"


@dataclass(frozen=True)
class ExportFact:
    """One module export, including re-exports."""

    exported: str
    local: str
    source: str | None = None


@dataclass(frozen=True)
class BindingFact:
    """One local symbol bound to another symbol or call target."""

    local: str
    target: str
    line: int


@dataclass(frozen=True)
class CallableFact:
    """One named callable with normalized parameter names."""

    name: str
    parameters: tuple[str, ...]
    line: int
    type_parameters: tuple[str, ...] = ()


@dataclass(frozen=True)
class CallFact:
    """One call site without parser-node leakage."""

    target: str
    arguments: tuple[str, ...]
    line: int
    owner: str
    method_hint: str | None = None
    type_arguments: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class RenderFact:
    """One rendered UI binding before module resolution."""

    binding: str
    line: int


@dataclass(frozen=True)
class SelectorFact:
    """One static selector/source signature."""

    selector: str
    line: int
    strength: str


@dataclass(frozen=True)
class EndpointFact:
    """One HTTP call; ``url=None`` records a dynamic endpoint."""

    url: str | None
    line: int
    method: str | None
    dynamic: bool


@dataclass(frozen=True)
class NetworkCallFact:
    """One locally classified network/query call."""

    target: str
    client_family: str
    method: str | None
    url: str | None
    url_expression: str | None
    line: int
    dynamic: bool
    owner: str
    resolution: str
    unresolved_evidence: str | None = None
    request_type_refs: tuple[str, ...] = ()
    response_type_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalyzerObservations:
    """AST-derived values needed by deterministic analyzer checks."""

    div_count: int = 0
    semantic_count: int = 0
    nested_ternaries: int = 0
    cards: int = 0
    charts: int = 0
    prop_components: tuple[tuple[str, tuple[str, ...]], ...] = ()
    animation_state: bool = False
    sibling_component_groups: tuple[tuple[str, ...], ...] = ()
    styled_nesting_depth: int = 0


@dataclass(frozen=True)
class SourceFacts:
    """Normalized parse result shared across analyzer and frontend mapping."""

    path: Path
    extension: str
    imports: tuple[str, ...] = ()
    import_aliases: tuple[ImportAlias, ...] = ()
    exports: tuple[ExportFact, ...] = ()
    bindings: tuple[BindingFact, ...] = ()
    callables: tuple[CallableFact, ...] = ()
    calls: tuple[CallFact, ...] = ()
    react_aliases: tuple[ImportAlias, ...] = ()
    rendered_modules: tuple[str, ...] = ()
    rendered_bindings: tuple[RenderFact, ...] = ()
    selectors: tuple[SelectorFact, ...] = ()
    declared_ui_modules: tuple[SourceOccurrence, ...] = ()
    regions: tuple[SourceOccurrence, ...] = ()
    actions: tuple[SourceOccurrence, ...] = ()
    states: tuple[SourceOccurrence, ...] = ()
    network_calls: tuple[NetworkCallFact, ...] = ()
    network_symbols: tuple[NetworkCallFact, ...] = ()
    endpoints: tuple[EndpointFact, ...] = ()
    routes: tuple[SourceOccurrence, ...] = ()
    analyzer: AnalyzerObservations = field(default_factory=AnalyzerObservations)
    extractor: str = "none"
    confidence: float = 0.0
    parse_errors: bool = False


ParserFactory = Callable[[str], object | None]


def extract_source_facts(
    path: Path,
    content: str,
    *,
    parser_factory: ParserFactory | None = None,
) -> SourceFacts | None:
    """Parse ``content`` once and return normalized facts.

    ``None`` means no qualified parser exists or parsing failed. A recovered
    syntax tree returns facts with ``parse_errors`` set and reduced confidence.
    """
    extension = path.suffix.lower()
    parser = (parser_factory or get_parser)(extension)
    if parser is None:
        return None
    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except Exception:
        return None

    root_node = tree.root_node
    nodes = tuple(_walk(root_node))
    imports, aliases = _extract_imports(nodes)
    exports, default_component = _extract_exports(nodes, path)
    bindings = _extract_bindings(nodes)
    callables = _extract_callables(nodes)
    calls = _extract_calls(nodes)
    network_calls, network_symbols = _classify_network_calls(
        aliases=aliases,
        bindings=bindings,
        callables=callables,
        calls=calls,
    )
    alias_map = {item.local: item.imported for item in aliases}
    react_aliases = tuple(item for item in aliases if item.source == "react")
    use_state_names = {
        "useState",
        "React.useState",
        *(item.local for item in react_aliases if item.imported == "useState"),
    }

    components = [default_component] if default_component is not None else []
    rendered_modules: list[str] = []
    rendered_bindings: list[RenderFact] = []
    selectors: list[SelectorFact] = []
    regions: list[SourceOccurrence] = []
    actions: list[SourceOccurrence] = []
    states: list[SourceOccurrence] = []
    routes: list[SourceOccurrence] = []
    config_routes: list[SourceOccurrence] = []
    has_router_signal = False

    analyzer_state = _MutableAnalyzerState()
    for node in nodes:
        _collect_semantic_node(
            node,
            alias_map=alias_map,
            use_state_names=use_state_names,
            components=components,
            rendered_modules=rendered_modules,
            rendered_bindings=rendered_bindings,
            selectors=selectors,
            regions=regions,
            actions=actions,
            states=states,
            routes=routes,
            config_routes=config_routes,
        )
        if node.type == "identifier" and _text(node) in _ROUTER_IDENTIFIERS:
            has_router_signal = True
        if extension in _SCRIPT_EXTENSIONS:
            _collect_analyzer_node(node, analyzer_state)

    if has_router_signal:
        routes.extend(config_routes)
    parse_errors = bool(tree.root_node.has_error)
    return SourceFacts(
        path=path,
        extension=extension,
        imports=tuple(dict.fromkeys(item for item in imports if item)),
        import_aliases=aliases,
        exports=exports,
        bindings=bindings,
        callables=callables,
        calls=calls,
        react_aliases=react_aliases,
        rendered_modules=tuple(dict.fromkeys(rendered_modules)),
        rendered_bindings=_unique_rendered_bindings(rendered_bindings),
        selectors=_unique_selectors(selectors),
        declared_ui_modules=_unique_occurrences(components),
        regions=tuple(regions),
        actions=tuple(actions),
        states=_unique_occurrences(states),
        network_calls=network_calls,
        network_symbols=network_symbols,
        endpoints=_unique_endpoints(
            [
                EndpointFact(
                    item.url,
                    item.line,
                    item.method,
                    item.dynamic,
                )
                for item in network_calls
                if item.client_family in {"fetch", "axios", "ky", "http-wrapper"}
            ]
        ),
        routes=_unique_occurrences(routes),
        analyzer=analyzer_state.freeze(),
        extractor="tree-sitter",
        confidence=0.85 if parse_errors else 1.0,
        parse_errors=parse_errors,
    )


def _extract_usestate_binding(declaration_text: str) -> str | None:
    match = _USESTATE_BINDING_RE.search(declaration_text)
    return match.group("state") if match else None


def _identifier_tokens(identifier: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _IDENTIFIER_TOKEN_RE.findall(identifier))


def _is_animation_state_identifier(identifier: str) -> bool:
    return any(
        token in _ANIMATION_STATE_TOKENS or token.startswith(_ANIMATION_STATE_PREFIXES)
        for token in _identifier_tokens(identifier)
    )


@dataclass
class _MutableAnalyzerState:
    div_count: int = 0
    semantic_count: int = 0
    nested_ternaries: int = 0
    cards: int = 0
    charts: int = 0
    prop_components: dict[str, set[str]] = field(default_factory=dict)
    animation_state: bool = False
    sibling_components: dict[tuple[int, int, str], list[str]] = field(
        default_factory=dict
    )
    styled_nesting_depth: int = 0

    def freeze(self) -> AnalyzerObservations:
        return AnalyzerObservations(
            div_count=self.div_count,
            semantic_count=self.semantic_count,
            nested_ternaries=self.nested_ternaries,
            cards=self.cards,
            charts=self.charts,
            prop_components=tuple(
                (name, tuple(sorted(components)))
                for name, components in self.prop_components.items()
            ),
            animation_state=self.animation_state,
            sibling_component_groups=tuple(
                tuple(children) for children in self.sibling_components.values()
            ),
            styled_nesting_depth=self.styled_nesting_depth,
        )


def _extract_imports(
    nodes: Iterable[object],
) -> tuple[list[str], tuple[ImportAlias, ...]]:
    imports: list[str] = []
    aliases: list[ImportAlias] = []
    for node in nodes:
        if node.type not in {"import_statement", "export_statement"}:
            continue
        source_node = node.child_by_field_name("source")
        source = _literal(source_node)
        if source:
            imports.append(source)
        if node.type != "import_statement":
            continue
        clause = next(
            (child for child in node.named_children if child.type == "import_clause"),
            None,
        )
        if clause is None:
            continue
        for child in clause.named_children:
            if child.type == "identifier":
                aliases.append(ImportAlias(source, "default", _text(child), "default"))
            elif child.type == "namespace_import":
                local = next(
                    (
                        _text(item)
                        for item in child.named_children
                        if item.type == "identifier"
                    ),
                    "",
                )
                if local:
                    aliases.append(ImportAlias(source, "*", local, "namespace"))
            elif child.type == "named_imports":
                for specifier in child.named_children:
                    if specifier.type != "import_specifier":
                        continue
                    imported = _text(specifier.child_by_field_name("name"))
                    local = _text(specifier.child_by_field_name("alias")) or imported
                    if imported and local:
                        aliases.append(ImportAlias(source, imported, local))
    return imports, tuple(aliases)


def _extract_exports(
    nodes: Iterable[object],
    path: Path,
) -> tuple[tuple[ExportFact, ...], SourceOccurrence | None]:
    exports: list[ExportFact] = []
    default_component = None
    for node in nodes:
        if node.type != "export_statement":
            continue
        source = _literal(node.child_by_field_name("source")) or None
        is_default = any(child.type == "default" for child in node.children)
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            if declaration.type in {"function_declaration", "class_declaration"}:
                name = _text(declaration.child_by_field_name("name"))
                if name:
                    exports.append(ExportFact("default" if is_default else name, name))
            else:
                for descendant in _walk(declaration):
                    if descendant.type != "variable_declarator":
                        continue
                    local = _text(descendant.child_by_field_name("name"))
                    if local and _is_identifier(local):
                        exports.append(ExportFact(local, local))
        value = node.child_by_field_name("value")
        if value is not None:
            local = _text(value.child_by_field_name("name"))
            if not local and _is_anonymous_ui_value(value):
                local = _module_display_name(path)
                default_component = SourceOccurrence(local, _line(value))
            local = local or _text(value)
            if local:
                exports.append(ExportFact("default", local))
        for child in node.named_children:
            if child.type != "export_clause":
                continue
            for specifier in child.named_children:
                if specifier.type != "export_specifier":
                    continue
                local = _text(specifier.child_by_field_name("name"))
                exported = _text(specifier.child_by_field_name("alias")) or local
                if local and exported:
                    exports.append(ExportFact(exported, local, source))
        if (
            source
            and declaration is None
            and value is None
            and not any(child.type == "export_clause" for child in node.named_children)
            and any(child.type == "*" for child in node.children)
        ):
            exports.append(ExportFact("*", "*", source))
    return tuple(dict.fromkeys(exports)), default_component


def _is_anonymous_ui_value(node) -> bool:
    return bool(
        node.type in {"arrow_function", "class", "function_expression"}
        and not _text(node.child_by_field_name("name"))
        and any(
            child.type in {"jsx_element", "jsx_self_closing_element"}
            for child in _walk(node)
        )
    )


def _module_display_name(path: Path) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", path.stem)
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    return name if name and _is_identifier(name) else "DefaultComponent"


def _extract_bindings(nodes: Iterable[object]) -> tuple[BindingFact, ...]:
    bindings: list[BindingFact] = []
    for node in nodes:
        if node.type != "variable_declarator":
            continue
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        target = (
            _text(value_node.child_by_field_name("function"))
            if value_node.type == "call_expression"
            else _text(value_node)
        )
        if not target:
            continue
        if name_node.type == "identifier" and value_node.type in {
            "call_expression",
            "identifier",
            "member_expression",
        }:
            bindings.append(BindingFact(_text(name_node), target, _line(node)))
        elif name_node.type == "object_pattern":
            for child in name_node.named_children:
                if child.type == "pair_pattern":
                    key = _text(child.child_by_field_name("key"))
                    local = _text(child.child_by_field_name("value"))
                elif child.type == "shorthand_property_identifier_pattern":
                    key = local = _text(child)
                else:
                    continue
                if key and local:
                    bindings.append(BindingFact(local, f"{target}.{key}", _line(child)))
    return tuple(dict.fromkeys(bindings))


def _extract_callables(nodes: Iterable[object]) -> tuple[CallableFact, ...]:
    callables: list[CallableFact] = []
    for node in nodes:
        name = _callable_name(node)
        if not name:
            continue
        callables.append(
            CallableFact(
                name,
                _parameter_names(node.child_by_field_name("parameters")),
                _line(node),
                _type_parameter_names(node.child_by_field_name("type_parameters")),
            )
        )
    return tuple(dict.fromkeys(callables))


def _extract_calls(nodes: Iterable[object]) -> tuple[CallFact, ...]:
    calls: list[CallFact] = []
    for node in nodes:
        if node.type != "call_expression":
            continue
        function = node.child_by_field_name("function")
        if function is not None and function.type == "await_expression":
            function = next(iter(function.named_children), function)
        target = _text(function)
        if not target:
            continue
        arguments = node.child_by_field_name("arguments")
        values = (
            tuple(_text(child) for child in arguments.named_children)
            if arguments is not None
            else ()
        )
        calls.append(
            CallFact(
                target=target,
                arguments=values,
                line=_line(node),
                owner=_containing_callable(node),
                method_hint=_call_method_hint(arguments),
                type_arguments=_type_argument_references(
                    node.child_by_field_name("type_arguments")
                ),
            )
        )
    return tuple(calls)


def _classify_network_calls(
    *,
    aliases: tuple[ImportAlias, ...],
    bindings: tuple[BindingFact, ...],
    callables: tuple[CallableFact, ...],
    calls: tuple[CallFact, ...],
) -> tuple[tuple[NetworkCallFact, ...], tuple[NetworkCallFact, ...]]:
    families: dict[str, str] = {"fetch": "fetch", "axios": "axios", "ky": "ky"}
    binding_targets = {binding.local: binding.target for binding in bindings}
    for alias in aliases:
        family = _client_family_for_source(alias.source)
        if family:
            families[alias.local] = family

    changed = True
    while changed:
        changed = False
        for binding in bindings:
            base = binding.target.split(".", 1)[0]
            family = families.get(base)
            if family and families.get(binding.local) != family:
                families[binding.local] = family
                changed = True

    parameters_by_callable: dict[str, set[str]] = {}
    for callable_fact in callables:
        parameters_by_callable.setdefault(callable_fact.name, set()).update(
            callable_fact.parameters
        )
    wrapper_methods: dict[str, str | None] = {}
    wrapper_families: dict[str, str] = {}
    wrapper_type_refs: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for call in calls:
        if not call.owner or not call.arguments:
            continue
        base, method = _call_family_and_method(call.target, families, binding_targets)
        if base not in {"fetch", "axios", "ky"}:
            continue
        if call.arguments[0] not in parameters_by_callable.get(call.owner, set()):
            continue
        wrapper_families[call.owner] = base
        wrapper_methods[call.owner] = method or call.method_hint or "GET"
        request_refs, response_refs = classify_network_type_references(
            base,
            call.target,
            call.type_arguments,
        )
        previous_request, previous_response = wrapper_type_refs.get(
            call.owner, ((), ())
        )
        wrapper_type_refs[call.owner] = (
            tuple(dict.fromkeys((*previous_request, *request_refs))),
            tuple(dict.fromkeys((*previous_response, *response_refs))),
        )

    classified: list[NetworkCallFact] = []
    for call in calls:
        family, method = _call_family_and_method(
            call.target,
            {**families, **wrapper_families},
            binding_targets,
        )
        if family is None:
            continue
        if family in {"axios", "ky"} and call.target.rsplit(".", 1)[-1] in {
            "create",
            "extend",
        }:
            continue
        if call.owner in wrapper_families and family in {"fetch", "axios", "ky"}:
            continue
        if call.target in wrapper_families:
            family = "http-wrapper"
            method = call.method_hint or wrapper_methods.get(call.target)
        elif family == "fetch":
            method = call.method_hint or "GET"
        elif family in {"axios", "ky"}:
            method = method or call.method_hint

        expression = call.arguments[0] if call.arguments else None
        url = literal_text(expression) if expression is not None else None
        dynamic = expression is None or url is None or "${" in url
        unresolved = None
        if family in {"tanstack-query", "apollo", "rtk-query"} and url is None:
            unresolved = "client family resolved; endpoint URL not statically available"
        request_refs, response_refs = classify_network_type_references(
            family,
            call.target,
            call.type_arguments,
        )
        classified.append(
            NetworkCallFact(
                target=call.target,
                client_family=family,
                method=method,
                url=url,
                url_expression=expression,
                line=call.line,
                dynamic=dynamic,
                owner=call.owner,
                resolution="resolved",
                unresolved_evidence=unresolved,
                request_type_refs=request_refs,
                response_type_refs=response_refs,
            )
        )
    symbols: dict[str, NetworkCallFact] = {}

    def remember(name: str, candidate: NetworkCallFact) -> None:
        existing = symbols.get(name)
        if existing is None or (existing.url is None and candidate.url is not None):
            symbols[name] = candidate
        elif candidate.url is not None and candidate != existing:
            symbols[name] = replace(
                candidate,
                client_family=(
                    existing.client_family
                    if existing.client_family == candidate.client_family
                    else "mixed-client"
                ),
                method=existing.method if existing.method == candidate.method else None,
                url=None,
                url_expression=None,
                dynamic=True,
            )

    for local, family in families.items():
        remember(
            local,
            NetworkCallFact(
                local, family, None, None, None, 0, True, local, "definition"
            ),
        )
    for owner, family in wrapper_families.items():
        request_refs, response_refs = wrapper_type_refs.get(owner, ((), ()))
        remember(
            owner,
            NetworkCallFact(
                owner,
                family,
                wrapper_methods[owner],
                None,
                None,
                0,
                True,
                owner,
                "definition",
                request_type_refs=request_refs,
                response_type_refs=response_refs,
            ),
        )
    for call in classified:
        if call.owner:
            remember(call.owner, replace(call, resolution="definition"))
    return tuple(classified), tuple(symbols.values())


def _collect_semantic_node(
    node,
    *,
    alias_map: dict[str, str],
    use_state_names: set[str],
    components: list[SourceOccurrence],
    rendered_modules: list[str],
    rendered_bindings: list[RenderFact],
    selectors: list[SelectorFact],
    regions: list[SourceOccurrence],
    actions: list[SourceOccurrence],
    states: list[SourceOccurrence],
    routes: list[SourceOccurrence],
    config_routes: list[SourceOccurrence],
) -> None:
    if node.type in {"function_declaration", "class_declaration"}:
        name = _text(node.child_by_field_name("name"))
        if name[:1].isupper():
            components.append(SourceOccurrence(name, _line(node)))
    elif node.type == "variable_declarator":
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        name = _text(name_node)
        if (
            name[:1].isupper()
            and value_node is not None
            and value_node.type in {"arrow_function", "function_expression"}
        ):
            components.append(SourceOccurrence(name, _line(node)))
        if value_node is not None and value_node.type == "call_expression":
            call_name = _text(value_node.child_by_field_name("function"))
            if call_name in use_state_names and name_node is not None:
                identifiers = [
                    _text(item)
                    for item in _walk(name_node)
                    if item.type == "identifier"
                ]
                if identifiers:
                    states.append(
                        SourceOccurrence(
                            identifiers[0],
                            _line(node),
                            _containing_callable(node),
                        )
                    )
    elif node.type in {"jsx_opening_element", "jsx_self_closing_element"}:
        tag = _text(node.child_by_field_name("name"))
        if not tag:
            return
        rendered = alias_map.get(tag, tag)
        if tag[:1].isupper():
            rendered_modules.append(rendered if rendered[:1].isupper() else tag)
            rendered_bindings.append(RenderFact(tag, _line(node)))
        selectors.append(SelectorFact(tag.lower(), _line(node), "heuristic"))
        if tag.lower() in _REGION_TAGS:
            regions.append(SourceOccurrence(tag.lower(), _line(node)))
        for child in node.named_children:
            if child.type != "jsx_attribute":
                continue
            attribute = _text(child)
            named_children = list(child.named_children)
            name_node = child.child_by_field_name("name") or (
                named_children[0] if named_children else None
            )
            value_node = child.child_by_field_name("value") or (
                named_children[1] if len(named_children) > 1 else None
            )
            attribute_name = _text(name_node)
            attribute_value = _literal(value_node)
            selectors.extend(
                selector_facts(attribute_name, attribute_value, _line(child))
            )
            action_match = _ACTION_ATTRIBUTE_RE.match(attribute)
            if action_match:
                action_target = _text(value_node).strip("{}")
                actions.append(
                    SourceOccurrence(
                        action_match.group(1),
                        _line(child),
                        _containing_callable(child),
                        action_target if _is_identifier(action_target) else "",
                    )
                )
            if tag.rsplit(".", 1)[-1] == "Route":
                route_match = _ROUTE_ATTRIBUTE_RE.match(attribute)
                if route_match:
                    routes.append(SourceOccurrence(route_match.group(1), _line(child)))
    elif node.type == "pair":
        key = _text(node.child_by_field_name("key")).strip("\"'")
        if key == "path":
            literal = _literal(node.child_by_field_name("value"))
            if literal:
                config_routes.append(SourceOccurrence(literal, _line(node)))


def _collect_analyzer_node(node, state: _MutableAnalyzerState) -> None:
    if node.type in {"jsx_element", "jsx_self_closing_element"}:
        open_tag = (
            node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
        )
        if open_tag is None:
            return
        tag_name = _text(open_tag.child_by_field_name("name"))
        if not tag_name:
            return
        if tag_name == "div":
            state.div_count += 1
        elif tag_name in {
            "nav",
            "main",
            "article",
            "section",
            "aside",
            "header",
            "footer",
        }:
            state.semantic_count += 1
        if "Card" in tag_name or "Stat" in tag_name or "Metric" in tag_name:
            state.cards += 1
        elif "Chart" in tag_name or "Graph" in tag_name or "Activity" in tag_name:
            state.charts += 1

        parent = node.parent
        parent_key = (
            (int(parent.start_byte), int(parent.end_byte), parent.type)
            if parent is not None
            else (0, 0, "")
        )
        if tag_name[:1].isupper():
            state.sibling_components.setdefault(parent_key, []).append(tag_name)
        for attribute in open_tag.children or []:
            if attribute.type != "jsx_attribute":
                continue
            attribute_name = _text(attribute.child_by_field_name("name"))
            if attribute_name:
                state.prop_components.setdefault(attribute_name, set()).add(tag_name)
    elif node.type == "ternary_expression":
        state.nested_ternaries += sum(
            child.type == "ternary_expression" for child in node.children
        )
    elif node.type == "lexical_declaration":
        binding = _extract_usestate_binding(_text(node))
        if binding and _is_animation_state_identifier(binding):
            state.animation_state = True
    elif node.type == "tagged_template_expression":
        tag = node.child_by_field_name("function")
        if tag is not None and ("styled" in _text(tag) or "css" in _text(tag)):
            template = node.child_by_field_name("arguments") or node
            state.styled_nesting_depth = max(
                state.styled_nesting_depth,
                _text(template).count("{"),
            )


def _containing_callable(node) -> str:
    parent = node.parent
    while parent is not None:
        name = _callable_name(parent)
        if name:
            return name
        parent = parent.parent
    return ""


def _callable_name(node) -> str:
    if node.type == "function_declaration":
        return _text(node.child_by_field_name("name"))
    if node.type not in {"arrow_function", "function_expression"}:
        return ""
    container = node.parent
    if container is None:
        return ""
    if container.type == "variable_declarator":
        name = _text(container.child_by_field_name("name"))
        return name if _is_identifier(name) else ""
    if container.type == "pair":
        return _object_member_name(container)
    return ""


def _object_member_name(pair) -> str:
    members: list[str] = []
    current = pair
    while current is not None and current.type == "pair":
        member = _text(current.child_by_field_name("key")).strip("\"'")
        if not _is_identifier(member):
            return ""
        members.append(member)
        object_node = current.parent
        if object_node is None or object_node.type != "object":
            return ""
        container = object_node.parent
        if container is not None and container.type == "variable_declarator":
            root = _text(container.child_by_field_name("name"))
            if not _is_identifier(root):
                return ""
            return ".".join((root, *reversed(members)))
        current = container
    return ""


def _call_method_hint(arguments) -> str | None:
    if arguments is None:
        return None
    for options in arguments.named_children:
        if options.type != "object":
            continue
        for child in options.named_children:
            if child.type != "pair":
                continue
            key = _text(child.child_by_field_name("key")).strip("\"'")
            if key != "method":
                continue
            method = _literal(child.child_by_field_name("value")).upper()
            return method if method in _HTTP_METHODS else None
    return None


def _parameter_names(parameters) -> tuple[str, ...]:
    if parameters is None:
        return ()
    names: list[str] = []
    for child in parameters.named_children:
        pattern = child.child_by_field_name("pattern") or child
        if pattern.type == "identifier":
            names.append(_text(pattern))
            continue
        names.extend(
            _text(item) for item in _walk(pattern) if item.type == "identifier"
        )
    return tuple(dict.fromkeys(name for name in names if name))


def _type_parameter_names(type_parameters) -> tuple[str, ...]:
    if type_parameters is None:
        return ()
    return tuple(
        name
        for parameter in type_parameters.named_children[:8]
        if parameter.type == "type_parameter"
        and (name := _text(parameter.child_by_field_name("name")))
    )


def _type_argument_references(
    type_arguments,
) -> tuple[tuple[str, ...], ...]:
    if type_arguments is None:
        return ()
    return tuple(
        _bounded_type_references(argument)
        for argument in type_arguments.named_children[:8]
    )


def _bounded_type_references(node) -> tuple[str, ...]:
    references: list[str] = []
    pending = [node]
    visited = 0
    while pending and visited < 64 and len(references) < 16:
        current = pending.pop()
        visited += 1
        if current.type == "nested_type_identifier":
            references.append(_text(current))
            continue
        if current.type == "type_identifier":
            name = _text(current)
            if name not in _TYPE_CONTAINERS:
                references.append(name)
            continue
        pending.extend(reversed(current.named_children))
    return tuple(dict.fromkeys(reference for reference in references if reference))


def classify_network_type_references(
    family: str,
    target: str,
    type_arguments: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Classify bounded generic-call evidence without inferring DTO lineage."""

    if not type_arguments:
        return (), ()
    method = target.rsplit(".", 1)[-1].lower()

    def refs(*indexes: int) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                reference
                for index in indexes
                if index < len(type_arguments)
                for reference in type_arguments[index]
            )
        )

    if family == "axios":
        return refs(2), refs(0, 1)
    if family == "tanstack-query":
        return (
            refs(2) if "mutation" in method else (),
            refs(0, 2) if "query" in method else refs(0),
        )
    if family in {"apollo", "rtk-query"}:
        return refs(1), refs(0)
    if family == "ky":
        return (), refs(0)
    if method.startswith("use") and method.endswith(("query", "mutation")):
        return refs(1), refs(0)
    if len(type_arguments) == 1:
        return (), refs(0)
    return refs(0), refs(1)


def _client_family_for_source(source: str) -> str | None:
    lowered = source.lower()
    if lowered == "axios" or lowered.startswith("axios/"):
        return "axios"
    if lowered == "ky" or lowered.startswith("ky/"):
        return "ky"
    if "@tanstack/react-query" in lowered:
        return "tanstack-query"
    if "@apollo/client" in lowered:
        return "apollo"
    if "@reduxjs/toolkit/query" in lowered:
        return "rtk-query"
    return None


def _call_family_and_method(
    target: str,
    families: dict[str, str],
    binding_targets: dict[str, str],
) -> tuple[str | None, str | None]:
    resolved = binding_targets.get(target, target)
    parts = resolved.split(".")
    family = families.get(parts[0]) or families.get(target)
    method = parts[-1].upper() if parts[-1].upper() in _HTTP_METHODS else None
    if family in {"tanstack-query", "apollo", "rtk-query"}:
        return family, method
    if family in {"fetch", "axios", "ky"}:
        return family, method
    if target in families:
        return families[target], method
    return None, None


def selector_facts(
    name: str,
    value: str,
    line: int,
) -> tuple[SelectorFact, ...]:
    if not name or not value:
        return ()
    if name == "id":
        return (SelectorFact(f"#{value}", line, "exact"),)
    if name in {"data-testid", "data-test"}:
        escaped = value.replace('"', '\\"')
        return (SelectorFact(f'[{name}="{escaped}"]', line, "exact"),)
    if name in {"class", "className", ":class"}:
        return tuple(
            SelectorFact(f".{class_name}", line, "heuristic")
            for class_name in value.split()
            if re.fullmatch(r"[-_A-Za-z][-\w]*", class_name)
        )
    return ()


def literal_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] in {'"', "'", "`"}
        and stripped[-1] == stripped[0]
    ):
        return stripped[1:-1]
    return None


def _is_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_$][\w$]*", value))


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _text(node) -> str:
    if node is None:
        return ""
    try:
        return node.text.decode("utf-8", errors="ignore")
    except AttributeError:
        return str(node.text)


def _literal(node) -> str:
    value = _text(node).strip()
    if len(value) >= 2 and value[0] in {'"', "'", "`"} and value[-1] == value[0]:
        return value[1:-1]
    return ""


def _line(node) -> int:
    return int(node.start_point.row) + 1


def _unique_occurrences(
    items: list[SourceOccurrence],
) -> tuple[SourceOccurrence, ...]:
    unique: dict[tuple[str, str], SourceOccurrence] = {}
    for item in items:
        unique.setdefault((item.owner, item.name), item)
    return tuple(unique.values())


def _unique_rendered_bindings(items: list[RenderFact]) -> tuple[RenderFact, ...]:
    return tuple(dict.fromkeys(items))


def _unique_selectors(items: list[SelectorFact]) -> tuple[SelectorFact, ...]:
    return tuple(dict.fromkeys(items))


def _unique_endpoints(items: list[EndpointFact]) -> tuple[EndpointFact, ...]:
    unique: dict[tuple[str | None, str | None, int], EndpointFact] = {}
    for item in items:
        unique.setdefault(
            (item.url, item.method, item.line if item.dynamic else 0),
            item,
        )
    return tuple(unique.values())
