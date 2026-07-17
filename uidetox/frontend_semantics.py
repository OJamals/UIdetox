"""AST-backed source semantics for frontend mapping.

Regex remains a deliberate fallback for languages whose tree-sitter grammar is
unavailable. Consumers get provenance and confidence with every extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from uidetox.analyzer_ast import _get_parser


@dataclass(frozen=True)
class SemanticOccurrence:
    name: str
    line: int


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


def extract_script_semantics(path: Path, content: str) -> ScriptSemantics | None:
    """Extract script semantics from syntax nodes; return ``None`` for fallback."""
    parser = _get_parser(path.suffix.lower())
    if parser is None:
        return None
    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except (TypeError, ValueError, RuntimeError):
        return None

    nodes = list(_walk(tree.root_node))
    imported_aliases: dict[str, str] = {}
    use_state_names = {"useState", "React.useState"}
    imports: list[str] = []

    for node in nodes:
        if node.type not in {"import_statement", "export_statement"}:
            continue
        source = node.child_by_field_name("source")
        if source is not None:
            imports.append(_literal(source))
        if node.type != "import_statement" or _literal(source) != "react":
            react_import = False
        else:
            react_import = True
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
                if not identifiers:
                    continue
                imported = identifiers[0]
                local = identifiers[-1]
                imported_aliases[local] = imported
                if react_import and imported == "useState":
                    use_state_names.add(local)

    components: list[SemanticOccurrence] = []
    rendered_tags: list[str] = []
    regions: list[SemanticOccurrence] = []
    actions: list[SemanticOccurrence] = []
    states: list[SemanticOccurrence] = []
    endpoints: list[SemanticOccurrence] = []
    routes: list[SemanticOccurrence] = []
    config_routes: list[SemanticOccurrence] = []
    has_router_signal = False

    for node in nodes:
        if node.type in {"function_declaration", "class_declaration"}:
            name_node = node.child_by_field_name("name")
            name = _text(name_node)
            if name[:1].isupper():
                components.append(SemanticOccurrence(name, _line(node)))
        elif node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            name = _text(name_node)
            if (
                name[:1].isupper()
                and value_node is not None
                and value_node.type
                in {
                    "arrow_function",
                    "function_expression",
                }
            ):
                components.append(SemanticOccurrence(name, _line(node)))
            if value_node is not None and value_node.type == "call_expression":
                call_name = _text(value_node.child_by_field_name("function"))
                if call_name in use_state_names and name_node is not None:
                    identifiers = [
                        _text(item)
                        for item in _walk(name_node)
                        if item.type == "identifier"
                    ]
                    if identifiers:
                        states.append(SemanticOccurrence(identifiers[0], _line(node)))
        elif node.type in {"jsx_opening_element", "jsx_self_closing_element"}:
            tag = _text(node.child_by_field_name("name"))
            if not tag:
                continue
            rendered = imported_aliases.get(tag, tag)
            if rendered[:1].isupper():
                rendered_tags.append(rendered)
            if tag.lower() in _REGION_TAGS:
                regions.append(SemanticOccurrence(tag.lower(), _line(node)))
            for child in node.named_children:
                if child.type != "jsx_attribute":
                    continue
                attribute = _text(child)
                action_match = _ACTION_ATTRIBUTE_RE.match(attribute)
                if action_match:
                    actions.append(
                        SemanticOccurrence(action_match.group(1), _line(child))
                    )
                if tag.rsplit(".", 1)[-1] == "Route":
                    route_match = _ROUTE_ATTRIBUTE_RE.match(attribute)
                    if route_match:
                        routes.append(
                            SemanticOccurrence(route_match.group(1), _line(child))
                        )
        elif node.type == "call_expression":
            call_name = _text(node.child_by_field_name("function"))
            if call_name == "fetch" or call_name.lower() in {
                "axios.get",
                "axios.post",
                "axios.put",
                "axios.patch",
                "axios.delete",
            }:
                arguments = node.child_by_field_name("arguments")
                literal = _first_literal(arguments)
                if literal:
                    endpoints.append(SemanticOccurrence(literal, _line(node)))
        elif node.type == "pair":
            key = _text(node.child_by_field_name("key")).strip("\"'")
            if key == "path":
                value = node.child_by_field_name("value")
                literal = _literal(value)
                if literal:
                    config_routes.append(SemanticOccurrence(literal, _line(node)))
        elif node.type == "identifier" and _text(node) in _ROUTER_IDENTIFIERS:
            has_router_signal = True

    if has_router_signal:
        routes.extend(config_routes)
    parse_errors = bool(tree.root_node.has_error)
    return ScriptSemantics(
        components=_unique_occurrences(components),
        imports=tuple(dict.fromkeys(item for item in imports if item)),
        rendered_tags=tuple(dict.fromkeys(rendered_tags)),
        regions=tuple(regions),
        actions=tuple(actions),
        states=_unique_occurrences(states),
        endpoints=_unique_occurrences(endpoints),
        routes=_unique_occurrences(routes),
        extractor="tree-sitter",
        confidence=0.85 if parse_errors else 1.0,
        parse_errors=parse_errors,
    )


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _text(node) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="ignore")


def _literal(node) -> str:
    value = _text(node).strip()
    if len(value) >= 2 and value[0] in {'"', "'", "`"} and value[-1] == value[0]:
        return value[1:-1]
    return ""


def _first_literal(node) -> str:
    if node is None:
        return ""
    for candidate in _walk(node):
        if candidate.type in {"string", "template_string"}:
            return _literal(candidate)
    return ""


def _line(node) -> int:
    return int(node.start_point.row) + 1


def _unique_occurrences(
    items: list[SemanticOccurrence],
) -> tuple[SemanticOccurrence, ...]:
    unique: dict[str, SemanticOccurrence] = {}
    for item in items:
        unique.setdefault(item.name, item)
    return tuple(unique.values())
