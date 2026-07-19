"""Parse source once into immutable facts shared by analysis consumers.

Tree-sitter nodes stay private to this module. Downstream analyzer and mapping
code consume normalized values with source anchors, provenance, and confidence.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

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


@dataclass(frozen=True)
class SourceOccurrence:
    """One named source fact with a one-based source line."""

    name: str
    line: int


@dataclass(frozen=True)
class ImportAlias:
    """One named import alias resolved to its imported symbol."""

    source: str
    imported: str
    local: str


@dataclass(frozen=True)
class EndpointFact:
    """One HTTP call; ``url=None`` records a dynamic endpoint."""

    url: str | None
    line: int
    method: str | None
    dynamic: bool


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
    imports: tuple[str, ...]
    import_aliases: tuple[ImportAlias, ...]
    react_aliases: tuple[ImportAlias, ...]
    rendered_modules: tuple[str, ...]
    declared_ui_modules: tuple[SourceOccurrence, ...]
    regions: tuple[SourceOccurrence, ...]
    actions: tuple[SourceOccurrence, ...]
    states: tuple[SourceOccurrence, ...]
    endpoints: tuple[EndpointFact, ...]
    routes: tuple[SourceOccurrence, ...]
    analyzer: AnalyzerObservations
    extractor: str
    confidence: float
    parse_errors: bool


ParserFactory = Callable[[str], object | None]


def extract_source_facts(
    path: Path,
    content: str,
    *,
    parser_factory: ParserFactory | None = None,
) -> SourceFacts | None:
    """Parse ``content`` once and return normalized facts.

    ``None`` means no parser exists or parsing failed, allowing existing regex
    fallbacks to run. A recovered syntax tree is returned with ``parse_errors``
    set and reduced confidence.
    """
    extension = path.suffix.lower()
    parser = (parser_factory or get_parser)(extension)
    if parser is None:
        return None
    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except Exception:
        return None

    nodes = tuple(_walk(tree.root_node))
    imports, aliases = _extract_imports(nodes)
    alias_map = {item.local: item.imported for item in aliases}
    react_aliases = tuple(item for item in aliases if item.source == "react")
    use_state_names = {
        "useState",
        "React.useState",
        *(item.local for item in react_aliases if item.imported == "useState"),
    }

    components: list[SourceOccurrence] = []
    rendered_modules: list[str] = []
    regions: list[SourceOccurrence] = []
    actions: list[SourceOccurrence] = []
    states: list[SourceOccurrence] = []
    endpoints: list[EndpointFact] = []
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
            regions=regions,
            actions=actions,
            states=states,
            endpoints=endpoints,
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
        react_aliases=react_aliases,
        rendered_modules=tuple(dict.fromkeys(rendered_modules)),
        declared_ui_modules=_unique_occurrences(components),
        regions=tuple(regions),
        actions=tuple(actions),
        states=_unique_occurrences(states),
        endpoints=_unique_endpoints(endpoints),
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
    nodes: tuple[object, ...],
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
        for child in node.named_children:
            if child.type != "import_clause":
                continue
            for specifier in _walk(child):
                if specifier.type != "import_specifier":
                    continue
                identifiers = [
                    _text(item)
                    for item in specifier.named_children
                    if item.type == "identifier"
                ]
                if identifiers:
                    aliases.append(
                        ImportAlias(
                            source=source,
                            imported=identifiers[0],
                            local=identifiers[-1],
                        )
                    )
    return imports, tuple(aliases)


def _collect_semantic_node(
    node,
    *,
    alias_map: dict[str, str],
    use_state_names: set[str],
    components: list[SourceOccurrence],
    rendered_modules: list[str],
    regions: list[SourceOccurrence],
    actions: list[SourceOccurrence],
    states: list[SourceOccurrence],
    endpoints: list[EndpointFact],
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
                    states.append(SourceOccurrence(identifiers[0], _line(node)))
    elif node.type in {"jsx_opening_element", "jsx_self_closing_element"}:
        tag = _text(node.child_by_field_name("name"))
        if not tag:
            return
        rendered = alias_map.get(tag, tag)
        if rendered[:1].isupper():
            rendered_modules.append(rendered)
        if tag.lower() in _REGION_TAGS:
            regions.append(SourceOccurrence(tag.lower(), _line(node)))
        for child in node.named_children:
            if child.type != "jsx_attribute":
                continue
            attribute = _text(child)
            action_match = _ACTION_ATTRIBUTE_RE.match(attribute)
            if action_match:
                actions.append(SourceOccurrence(action_match.group(1), _line(child)))
            if tag.rsplit(".", 1)[-1] == "Route":
                route_match = _ROUTE_ATTRIBUTE_RE.match(attribute)
                if route_match:
                    routes.append(SourceOccurrence(route_match.group(1), _line(child)))
    elif node.type == "call_expression":
        endpoint = _extract_endpoint(node)
        if endpoint is not None:
            endpoints.append(endpoint)
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


def _extract_endpoint(node) -> EndpointFact | None:
    call_name = _text(node.child_by_field_name("function"))
    lowered = call_name.lower()
    axios_methods = {
        "axios.get": "GET",
        "axios.post": "POST",
        "axios.put": "PUT",
        "axios.patch": "PATCH",
        "axios.delete": "DELETE",
    }
    if call_name != "fetch" and lowered not in axios_methods:
        return None

    arguments = node.child_by_field_name("arguments")
    values = list(arguments.named_children) if arguments is not None else []
    url = _literal(values[0]) if values else ""
    if "${" in url:
        url = ""
    method: str | None = axios_methods.get(lowered)
    if call_name == "fetch":
        method = _fetch_method(values)
    return EndpointFact(
        url=url or None,
        line=_line(node),
        method=method,
        dynamic=not bool(url),
    )


def _fetch_method(arguments: list[object]) -> str | None:
    if len(arguments) < 2:
        return "GET"
    options = arguments[1]
    if options.type != "object":
        return None
    for child in options.named_children:
        if child.type != "pair":
            continue
        key = _text(child.child_by_field_name("key")).strip("\"'")
        if key != "method":
            continue
        method = _literal(child.child_by_field_name("value")).upper()
        return method if method in _HTTP_METHODS else None
    return "GET"


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
    unique: dict[str, SourceOccurrence] = {}
    for item in items:
        unique.setdefault(item.name, item)
    return tuple(unique.values())


def _unique_endpoints(items: list[EndpointFact]) -> tuple[EndpointFact, ...]:
    unique: dict[tuple[str | None, str | None, int], EndpointFact] = {}
    for item in items:
        unique.setdefault(
            (item.url, item.method, item.line if item.dynamic else 0),
            item,
        )
    return tuple(unique.values())
