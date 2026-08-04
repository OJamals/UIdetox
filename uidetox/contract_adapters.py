"""Qualified static backend contract observation adapters."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import tokenize
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from uidetox.contract_graph import (
    ContractObservation,
    SourceAnchor,
    _json_value,
    _schema_observation_state,
    _unknown_anchor,
    contract_schema_observations,
    normalize_http_method,
    normalize_route_path,
)


@dataclass(frozen=True)
class _PythonProvenance:
    model_classes: frozenset[str]
    entity_classes: frozenset[str]
    dependency_injectors: frozenset[str]
    mapped_annotations: frozenset[str]
    security_injectors: frozenset[str]
    security_bindings: frozenset[str]


@dataclass(frozen=True)
class _BackendSource:
    path: Path
    relative: str
    suffix: str
    content: str
    digest: str
    openapi: bool


_CODE_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py"}

_OPENAPI_SCHEMA_DEPTH_LIMIT = 16
_OPENAPI_SCHEMA_PROPERTY_LIMIT = 128
_OPENAPI_SCHEMA_VARIANT_LIMIT = 32
_OPENAPI_TEXT_LIMIT = 256
_OPENAPI_SCHEMA_NODE_LIMIT = 512
_OPENAPI_SCHEMA_BYTE_LIMIT = 262_144
_OPENAPI_LINEAGE_ITEM_LIMIT = 512
_OPENAPI_LINEAGE_BYTE_LIMIT = 262_144
_OPERATION_OBLIGATIONS = (
    "affected-reads",
    "auth-required",
    "cancellation",
    "conflict",
    "duplicate-submit",
    "forbidden",
    "idempotency",
    "optimistic-rollback",
    "partial-success",
    "rate-limit",
    "retry",
    "stale-refresh",
    "timeout",
    "validation",
)
_OPERATION_OBLIGATION_REQUIRED_DETAILS = {
    "affected-reads": ("operations",),
    "duplicate-submit": ("mechanism",),
    "idempotency": ("scope", "retention", "replay"),
    "retry": ("condition",),
}


_IGNORED_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".uidetox",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "vendor",
}


_INTERNAL_PATHS = re.compile(
    r"^/(?:health|healthz|ready|readiness|live|liveness|metrics|internal)(?:/|$)",
    re.IGNORECASE,
)


_PY_METHOD_DECORATOR = re.compile(
    r"@(?P<receiver>[A-Za-z_$][\w$]*)\."
    r"(?P<method>get|post|put|patch|delete|head|options)"
    r"\(\s*(?P<quote>[\"'])(?P<path>.*?)(?P=quote)",
    re.DOTALL | re.IGNORECASE,
)


_PY_ROUTE_DECORATOR = re.compile(
    r"@(?P<receiver>[A-Za-z_$][\w$]*)\.route"
    r"\(\s*(?P<quote>[\"'])(?P<path>.*?)(?P=quote)(?P<args>[^)]*)\)",
    re.DOTALL | re.IGNORECASE,
)


_JS_METHOD_ROUTE = re.compile(
    r"\b(?P<receiver>[A-Za-z_$][\w$]*)\."
    r"(?P<method>get|post|put|patch|delete|head|options)"
    r"\(\s*(?P<quote>[\"'`])(?P<path>.*?)(?P=quote)",
    re.DOTALL | re.IGNORECASE,
)


_FASTIFY_ROUTE = re.compile(
    r"\b(?P<receiver>[A-Za-z_$][\w$]*)\.route\s*\(\s*\{(?P<body>.*?)\}\s*\)",
    re.DOTALL,
)


_NEST_CONTROLLER = re.compile(
    r"@Controller\s*\(\s*(?:(?P<quote>[\"'])(?P<path>.*?)(?P=quote))?\s*\)",
    re.DOTALL,
)


_NEST_METHOD = re.compile(
    r"@(?P<method>Get|Post|Put|Patch|Delete|Head|Options)"
    r"\s*\(\s*(?:(?P<quote>[\"'])(?P<path>.*?)(?P=quote))?\s*\)",
    re.DOTALL,
)


_QUALIFIED_BACKEND_MARKERS = (
    "@controller",
    "@app.",
    "@router.",
    "@bp.",
    "fastapi(",
    "apirouter(",
    "flask(",
    "blueprint(",
    "express(",
    "fastify",
    ".route(",
    "app.get(",
    "app.post(",
    "app.put(",
    "app.patch(",
    "app.delete(",
    "router.get(",
    "router.post(",
    "router.put(",
    "router.patch(",
    "router.delete(",
)


_FACTORY_IMPORT_MARKERS = ("fastapi", "flask", "express")
_CONSERVATIVE_BACKEND_MARKERS = (
    *_QUALIFIED_BACKEND_MARKERS,
    *_FACTORY_IMPORT_MARKERS,
)


def _discover_backend_sources(root: Path) -> tuple[_BackendSource, ...]:
    sources: list[_BackendSource] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _IGNORED_DIRS for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if _is_test_source(relative):
            continue
        suffix = path.suffix.lower()
        openapi = suffix in {".json", ".yaml", ".yml"} and path.name.lower().startswith(
            ("openapi", "swagger")
        )
        if not openapi and suffix not in _CODE_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not openapi and (
            not _could_be_backend_source(content)
            or not _looks_like_backend_source(content, suffix)
        ):
            continue
        sources.append(
            _BackendSource(
                path=path,
                relative=relative,
                suffix=suffix,
                content=content,
                digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                openapi=openapi,
            )
        )
    return tuple(sources)


def backend_source_manifest(root: Path) -> dict[str, str]:
    """Hash every source qualified to contribute backend/API evidence."""
    return {
        source.relative: source.digest for source in _discover_backend_sources(root)
    }


def extract_backend_observations(
    root: Path,
) -> tuple[list[ContractObservation], dict[str, Any]]:
    operations: list[ContractObservation] = []
    adapters: set[str] = set()
    unknown = 0
    sources = _discover_backend_sources(root)
    for source in sources:
        if source.openapi:
            extracted = _extract_openapi(
                source.path,
                source.relative,
                source.content,
            )
            if extracted:
                adapters.add("openapi")
                operations.extend(extracted)
            else:
                operations.append(
                    _unknown_backend(source.relative, "openapi", "openapi")
                )
                unknown += 1
            continue
        extracted: list[ContractObservation] = []
        if source.suffix == ".py":
            extracted, found_adapters = _extract_python_routes(
                source.relative,
                source.content,
            )
        else:
            extracted, found_adapters = _extract_javascript_routes(
                source.relative,
                source.content,
            )
        if extracted:
            operations.extend(extracted)
            adapters.update(found_adapters)
            unknown += sum(item.classification == "unknown" for item in extracted)
        elif _contains_route_syntax(source.content, source.suffix):
            operations.append(
                _unknown_backend(source.relative, "unknown", "route-syntax")
            )
            unknown += 1
    return operations, {
        "adapters": adapters,
        "files_scanned": len(sources),
        "unknown": unknown,
        "source_manifest": {source.relative: source.digest for source in sources},
    }


def _is_test_source(relative: str) -> bool:
    path = Path(relative)
    lowered_parts = {part.lower() for part in path.parts[:-1]}
    lowered_name = path.name.lower()
    return bool(
        lowered_parts & {"__tests__", "e2e", "test", "tests"}
        or lowered_name.startswith("test_")
        or lowered_name.endswith("_test.py")
        or ".spec." in lowered_name
        or ".test." in lowered_name
    )


def _openapi_parameters(
    path_item: Mapping[str, Any],
    operation: Mapping[str, Any],
    document: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    """Resolve inherited parameters with operation-level override semantics."""

    parameters: dict[tuple[str, str], Mapping[str, Any]] = {}
    for values in (path_item.get("parameters"), operation.get("parameters")):
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            parameter = _resolve_openapi_mapping(value, document)
            name = parameter.get("name")
            location = parameter.get("in")
            if isinstance(name, str) and name and isinstance(location, str):
                parameters[(location, name)] = parameter
    return parameters


def _swagger_media_types(
    operation: Mapping[str, Any],
    document: Mapping[str, Any],
    key: str,
) -> tuple[str, ...]:
    """Return exact Swagger 2 operation/root media declarations."""

    values = operation.get(key, document.get(key))
    if not isinstance(values, list):
        return ()
    return tuple(sorted({str(value) for value in values if isinstance(value, str)}))


def _openapi_read_operation_counts(document: Mapping[str, Any]) -> dict[str, int]:
    """Count exact canonical backend read operations for reference validation."""

    counts: dict[str, int] = {}
    paths = document.get("paths")
    if not isinstance(paths, Mapping):
        return counts
    for route, path_item in paths.items():
        if not isinstance(path_item, Mapping):
            continue
        normalized, _parameters, unresolved = normalize_route_path(str(route))
        if unresolved:
            continue
        for method, operation in path_item.items():
            normalized_method = normalize_http_method(method)
            if normalized_method not in {"GET", "HEAD"} or not isinstance(
                operation, Mapping
            ):
                continue
            reference = f"{normalized_method} {normalized}"
            counts[reference] = counts.get(reference, 0) + 1
    return counts


def _validation_schema_has_field_association(value: Any) -> bool:
    """Accept only bounded schemas linking a field location to an error message."""

    remaining = _OPENAPI_SCHEMA_NODE_LIMIT

    def visit(node: Any) -> bool:
        nonlocal remaining
        if not isinstance(node, (Mapping, list, tuple)):
            return False
        remaining -= 1
        if remaining < 0:
            return False
        if isinstance(node, Mapping):
            properties = node.get("properties")
            if isinstance(properties, Mapping):
                names = {str(name).lower() for name in properties}
                locations = {"field", "fieldname", "loc", "location", "path"}
                messages = {"code", "error", "message", "msg", "type"}
                if names & locations and names & messages:
                    return True
            return any(visit(node[key]) for key in sorted(node, key=str))
        if isinstance(node, (list, tuple)):
            return any(visit(child) for child in node)
        return False

    return visit(value)


def _extract_openapi(
    path: Path,
    relative: str,
    content: str,
) -> list[ContractObservation]:
    try:
        if path.suffix.lower() == ".json":
            document = json.loads(content)
        else:
            document = yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError):
        return []
    if not isinstance(document, Mapping) or not isinstance(
        document.get("paths"), Mapping
    ):
        return []
    available_reads = _openapi_read_operation_counts(document)
    operations: list[ContractObservation] = []
    for route, path_item in sorted(
        document["paths"].items(), key=lambda item: str(item[0])
    ):
        if not isinstance(path_item, Mapping):
            continue
        for method, operation in sorted(
            path_item.items(), key=lambda item: str(item[0])
        ):
            normalized_method = normalize_http_method(method)
            if normalized_method is None or not isinstance(operation, Mapping):
                continue
            normalized, parameters, unresolved = normalize_route_path(str(route))
            transport_parameters = _openapi_parameters(path_item, operation, document)
            request_source = operation.get("requestBody")
            if request_source is None:
                request_source = next(
                    (
                        parameter
                        for (location, _name), parameter in transport_parameters.items()
                        if location == "body"
                    ),
                    None,
                )
            request_schema = _openapi_content_schema(request_source, document)
            request_schemas = contract_schema_observations(
                request_schema,
                fallback="request",
            )
            responses = operation.get("responses", {})
            response_map = (
                {str(key): value for key, value in responses.items()}
                if isinstance(responses, Mapping)
                else {}
            )
            success_statuses = sorted(
                str(status) for status in response_map if str(status).startswith("2")
            )
            error_statuses = sorted(
                str(status)
                for status in response_map
                if str(status).startswith(("4", "5")) or str(status) == "default"
            )
            response_schemas = tuple(
                schema_observation
                for status in success_statuses
                if (
                    schema := _openapi_content_schema(
                        response_map.get(status), document
                    )
                )
                for schema_observation in contract_schema_observations(
                    schema,
                    fallback=f"response:{status}",
                    status=status,
                )
            )
            error_schemas = tuple(
                (status, schema)
                for status in error_statuses
                if (
                    schema := _openapi_content_schema(
                        response_map.get(status), document
                    )
                )
            )
            security = operation.get("security", document.get("security"))
            if security is None or security == []:
                auth = "absent"
                security_names: tuple[str, ...] = ()
            elif isinstance(security, list):
                requirements = tuple(
                    requirement
                    for requirement in security
                    if isinstance(requirement, Mapping)
                )
                security_names = tuple(
                    sorted(
                        {
                            str(name)
                            for requirement in requirements
                            for name in requirement
                        }
                    )
                )
                allows_anonymous = any(not requirement for requirement in requirements)
                if security_names and allows_anonymous:
                    auth = "unknown"
                elif security_names:
                    auth = "present"
                elif allows_anonymous:
                    auth = "absent"
                else:
                    auth = "unknown"
            else:
                auth = "unknown"
                security_names = ()
            lineage = tuple(
                {
                    "kind": "auth_requirement",
                    "name": name,
                    "provenance": "openapi:security",
                }
                for name in security_names
            ) + _openapi_transport_lineage(
                path_item,
                operation,
                response_map,
                security,
                document,
                method=normalized_method,
                available_reads=available_reads,
            )
            operations.append(
                ContractObservation(
                    identity=f"openapi:{relative}:{normalized_method}:{normalized}",
                    side="backend",
                    method=normalized_method,
                    path=str(route),
                    normalized_path=normalized,
                    parameters=parameters,
                    dynamic=unresolved,
                    classification=_classify_path(normalized),
                    request_schemas=request_schemas,
                    response_schemas=response_schemas,
                    error_schemas=error_schemas,
                    status_codes=tuple(sorted(response_map)),
                    auth=auth,
                    authorization=str(
                        operation.get(
                            "x-uidetox-authorization",
                            "absent" if auth == "absent" else "unknown",
                        )
                    ),
                    tenant=str(
                        operation.get(
                            "x-uidetox-tenant",
                            "absent" if auth == "absent" else "unknown",
                        )
                    ),
                    evidence={
                        "request": ("present" if request_schemas else "absent"),
                        "response": (
                            _schema_observation_state(
                                response_schemas,
                                statuses_distinguish=True,
                            )
                            if response_schemas
                            else "absent"
                            if success_statuses
                            else "unknown"
                        ),
                        "error": "present" if error_schemas else "absent",
                        "status": "present" if response_map else "unknown",
                        "ui_lifecycle": "absent",
                        "cache": "absent",
                    },
                    lineage=lineage,
                    sources=(
                        SourceAnchor(
                            file=relative,
                            line=1,
                            framework="openapi",
                            extractor="openapi",
                            confidence=1.0,
                        ),
                    ),
                )
            )
    return operations


def _extract_python_routes(
    relative: str,
    content: str,
) -> tuple[list[ContractObservation], set[str]]:
    operations: list[ContractObservation] = []
    adapters: set[str] = set()
    code_positions = _python_code_positions(content)
    receiver_frameworks = _python_receiver_frameworks(content)
    prefixes = _python_receiver_prefixes(content)
    for match in _PY_METHOD_DECORATOR.finditer(content):
        if not code_positions[match.start()]:
            continue
        receiver = match.group("receiver")
        framework = receiver_frameworks.get(receiver)
        if framework is None:
            operations.append(
                _unsupported_operation(
                    method=match.group("method"),
                    path=match.group("path"),
                    file=relative,
                    line=_line_number(content, match.start()),
                    extractor="unknown-python-decorator",
                )
            )
            continue
        adapters.add(framework)
        operations.append(
            _operation(
                side="backend",
                method=match.group("method"),
                path=_join_routes(
                    prefixes.get(match.group("receiver"), ""),
                    match.group("path"),
                ),
                file=relative,
                line=_line_number(content, match.start()),
                framework=framework,
                extractor=f"{framework}-decorator",
                confidence=0.92,
            )
        )
    for match in _PY_ROUTE_DECORATOR.finditer(content):
        if not code_positions[match.start()]:
            continue
        receiver = match.group("receiver")
        if receiver_frameworks.get(receiver) != "flask":
            operations.append(
                _unsupported_operation(
                    method=None,
                    path=match.group("path"),
                    file=relative,
                    line=_line_number(content, match.start()),
                    extractor="unknown-python-route",
                )
            )
            continue
        adapters.add("flask")
        methods = _methods_from_text(match.group("args")) or ("GET",)
        for method in methods:
            operations.append(
                _operation(
                    side="backend",
                    method=method,
                    path=_join_routes(
                        prefixes.get(match.group("receiver"), ""),
                        match.group("path"),
                    ),
                    file=relative,
                    line=_line_number(content, match.start()),
                    framework="flask",
                    extractor="flask-route",
                    confidence=0.95,
                )
            )
    return _enrich_python_operations(operations, content), adapters


def _extract_javascript_routes(
    relative: str,
    content: str,
) -> tuple[list[ContractObservation], set[str]]:
    operations: list[ContractObservation] = []
    adapters: set[str] = set()
    code_positions = _javascript_code_positions(content)
    receiver_frameworks = _javascript_receiver_frameworks(content)
    prefixes = _javascript_receiver_prefixes(content)
    fastify_prefix = _fastify_registration_prefix(content)
    for match in _JS_METHOD_ROUTE.finditer(content):
        if not code_positions[match.start()]:
            continue
        receiver = match.group("receiver")
        framework = receiver_frameworks.get(receiver)
        if framework is None and receiver.lower() in {
            "axios",
            "fetch",
            "client",
            "api",
        }:
            continue
        if framework is None:
            operations.append(
                _unsupported_operation(
                    method=match.group("method"),
                    path=match.group("path"),
                    file=relative,
                    line=_line_number(content, match.start()),
                    extractor="unknown-javascript-route",
                )
            )
            continue
        adapters.add(framework)
        prefix = prefixes.get(match.group("receiver"), "")
        if framework == "fastify" and not prefix:
            prefix = fastify_prefix
        operations.append(
            _operation(
                side="backend",
                method=match.group("method"),
                path=_join_routes(prefix, match.group("path")),
                file=relative,
                line=_line_number(content, match.start()),
                framework=framework,
                extractor=f"{framework}-route",
                confidence=0.9,
            )
        )
    for match in _FASTIFY_ROUTE.finditer(content):
        if not code_positions[match.start()]:
            continue
        body = match.group("body")
        method_match = re.search(
            r"\bmethod\s*:\s*[\"'`](?P<method>[A-Za-z]+)[\"'`]", body
        )
        path_match = re.search(
            r"\b(?:url|path)\s*:\s*[\"'`](?P<path>.*?)[\"'`]", body, re.DOTALL
        )
        if method_match and path_match:
            receiver = match.group("receiver")
            if receiver_frameworks.get(receiver) != "fastify":
                operations.append(
                    _unsupported_operation(
                        method=method_match.group("method"),
                        path=path_match.group("path"),
                        file=relative,
                        line=_line_number(content, match.start()),
                        extractor="unknown-route-object",
                    )
                )
                continue
            adapters.add("fastify")
            prefix = prefixes.get(match.group("receiver"), "") or fastify_prefix
            operations.append(
                _operation(
                    side="backend",
                    method=method_match.group("method"),
                    path=_join_routes(prefix, path_match.group("path")),
                    file=relative,
                    line=_line_number(content, match.start()),
                    framework="fastify",
                    extractor="fastify-route-object",
                    confidence=0.95,
                )
            )
    controller = next(
        (
            match
            for match in _NEST_CONTROLLER.finditer(content)
            if code_positions[match.start()]
        ),
        None,
    )
    if controller:
        adapters.add("nest")
        prefix = controller.group("path") or ""
        for match in _NEST_METHOD.finditer(content):
            if not code_positions[match.start()]:
                continue
            route = _join_routes(prefix, match.group("path") or "")
            operations.append(
                _operation(
                    side="backend",
                    method=match.group("method"),
                    path=route,
                    file=relative,
                    line=_line_number(content, match.start()),
                    framework="nest",
                    extractor="nest-decorator",
                    confidence=0.92,
                )
            )
    return [
        _enrich_javascript_operation(item, content) for item in operations
    ], adapters


def _operation(
    *,
    side: str,
    method: str | None,
    path: str | None,
    file: str,
    line: int,
    framework: str,
    extractor: str,
    confidence: float,
) -> ContractObservation:
    normalized, parameters, unresolved = normalize_route_path(path)
    return ContractObservation(
        identity=f"{extractor}:{file}:{line}:{normalize_http_method(method) or '?'}:{normalized or '?'}",
        side=side,
        method=normalize_http_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=unresolved,
        classification=_classify_path(normalized),
        evidence={
            "request": (
                "absent"
                if normalize_http_method(method) in {"GET", "HEAD", "OPTIONS"}
                else "unknown"
            ),
            "response": "unknown",
            "error": "unknown",
            "status": "unknown",
            "ui_lifecycle": "absent",
            "cache": "absent",
        },
        sources=(SourceAnchor(file, line, framework, extractor, confidence),),
    )


def _unknown_backend(file: str, framework: str, extractor: str) -> ContractObservation:
    return ContractObservation(
        identity=f"{extractor}:{file}:1:unknown",
        side="backend",
        method=None,
        path=None,
        normalized_path=None,
        dynamic=True,
        classification="unknown",
        sources=(SourceAnchor(file, 1, framework, extractor, 0.2),),
    )


def _unsupported_operation(
    *,
    method: str | None,
    path: str | None,
    file: str,
    line: int,
    extractor: str,
) -> ContractObservation:
    normalized, parameters, _unresolved = normalize_route_path(path)
    return ContractObservation(
        identity=f"{extractor}:{file}:{line}:{normalize_http_method(method) or '?'}:{normalized or '?'}",
        side="backend",
        method=normalize_http_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=True,
        classification="unknown",
        sources=(SourceAnchor(file, line, "unknown", extractor, 0.2),),
    )


def _methods_from_text(value: str) -> tuple[str, ...]:
    methods = {
        method
        for token in re.findall(r"[\"']([A-Za-z]+)[\"']", value)
        if (method := normalize_http_method(token)) is not None
    }
    return tuple(sorted(methods))


def _python_framework_factories(
    content: str,
) -> dict[str, tuple[str, str]]:
    factories: dict[str, tuple[str, str]] = {}
    constructors = {
        "fastapi": {"FastAPI", "APIRouter"},
        "flask": {"Flask", "Blueprint"},
    }
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return factories
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            framework = node.module.split(".", 1)[0]
            if framework not in constructors:
                continue
            for imported in node.names:
                if imported.name == "*":
                    for constructor in constructors[framework]:
                        factories[constructor] = (framework, constructor)
                    continue
                if imported.name not in constructors[framework]:
                    continue
                factories[imported.asname or imported.name] = (
                    framework,
                    imported.name,
                )
        elif isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name not in constructors:
                    continue
                namespace = imported.asname or imported.name
                for constructor in constructors[imported.name]:
                    factories[f"{namespace}.{constructor}"] = (
                        imported.name,
                        constructor,
                    )
    return factories


def _python_receiver_prefixes(content: str) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    factories = _python_framework_factories(content)
    code_positions = _python_code_positions(content)
    prefix_argument = r"\b(?:prefix|url_prefix)\s*=\s*[\"'](?P<prefix>[^)]*?)[\"']"
    prefix_args = rf"(?:[^)]*?{prefix_argument}[^)]*|[^)]*)"
    assignment = re.compile(
        r"\b(?P<receiver>[A-Za-z_$][\w$]*)\s*=\s*"
        r"(?P<factory>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)"
        rf"\s*\({prefix_args}\)",
        re.DOTALL,
    )
    for match in assignment.finditer(content):
        if not code_positions[match.start()]:
            continue
        factory = factories.get(match.group("factory"))
        prefix = match.group("prefix")
        if (
            factory is None
            or factory[1] not in {"APIRouter", "Blueprint"}
            or prefix is None
        ):
            continue
        prefixes[match.group("receiver")] = prefix

    mount = re.compile(
        r"\b[A-Za-z_$][\w$]*\.(?:include_router|register_blueprint)"
        rf"\(\s*(?P<receiver>[A-Za-z_$][\w$]*){prefix_args}\)",
        re.DOTALL,
    )
    for match in mount.finditer(content):
        prefix = match.group("prefix")
        if not code_positions[match.start()] or prefix is None:
            continue
        receiver = match.group("receiver")
        prefixes[receiver] = _join_routes(
            prefix,
            prefixes.get(receiver, ""),
        )
    return prefixes


def _python_receiver_frameworks(content: str) -> dict[str, str]:
    frameworks: dict[str, str] = {}
    factories = _python_framework_factories(content)
    code_positions = _python_code_positions(content)
    assignment = re.compile(
        r"\b(?P<receiver>[A-Za-z_$][\w$]*)\s*=\s*"
        r"(?P<factory>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\(",
    )
    for match in assignment.finditer(content):
        if not code_positions[match.start()]:
            continue
        factory = factories.get(match.group("factory"))
        if factory is not None:
            frameworks[match.group("receiver")] = factory[0]
    return frameworks


def _javascript_receiver_prefixes(content: str) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    code_positions = _javascript_code_positions(content)
    mount = re.compile(
        r"\b(?P<parent>[A-Za-z_$][\w$]*)\.use"
        r"\(\s*(?P<quote>[\"'`])(?P<prefix>.*?)(?P=quote)"
        r"\s*,\s*(?P<receiver>[A-Za-z_$][\w$]*)",
        re.DOTALL,
    )
    for match in mount.finditer(content):
        if not code_positions[match.start()]:
            continue
        receiver = match.group("receiver")
        prefixes[receiver] = _join_routes(
            prefixes.get(match.group("parent"), ""),
            match.group("prefix"),
        )
    return prefixes


def _javascript_framework_factories(content: str) -> dict[str, str]:
    factories: dict[str, str] = {}
    code_positions = _javascript_code_positions(content)
    import_statement = re.compile(
        r"^[ \t]*import\s+(?P<clause>[^;]+?)\s+from\s*"
        r"(?P<quote>[\"'])(?P<module>express|fastify)(?P=quote)",
        re.DOTALL | re.MULTILINE,
    )
    for match in import_statement.finditer(content):
        if not code_positions[match.start()]:
            continue
        framework = match.group("module")
        clause = match.group("clause").strip()
        if clause.startswith("type "):
            continue
        default_match = re.match(r"(?P<binding>[A-Za-z_$][\w$]*)", clause)
        if default_match:
            binding = default_match.group("binding")
            factories[binding] = framework
            if framework == "express":
                factories[f"{binding}.Router"] = framework
        namespace_match = re.search(r"\*\s+as\s+(?P<binding>[A-Za-z_$][\w$]*)", clause)
        if namespace_match:
            binding = namespace_match.group("binding")
            factories[binding] = framework
            if framework == "express":
                factories[f"{binding}.Router"] = framework
        named_match = re.search(r"\{(?P<names>.*?)\}", clause, re.DOTALL)
        if named_match:
            allowed = (
                {"Router", "express", "default"}
                if framework == "express"
                else {"fastify", "Fastify", "default"}
            )
            for imported in named_match.group("names").split(","):
                parts = re.split(r"\s+as\s+", imported.strip())
                original = parts[0].strip()
                if original not in allowed:
                    continue
                alias = parts[1].strip() if len(parts) == 2 else original
                factories[alias] = framework

    require_binding = re.compile(
        r"^[ \t]*(?:const|let|var)\s+"
        r"(?P<binding>[A-Za-z_$][\w$]*)\s*=\s*"
        r"require\s*\(\s*(?P<quote>[\"'])(?P<module>express|fastify)(?P=quote)"
        r"\s*\)",
        re.MULTILINE,
    )
    for match in require_binding.finditer(content):
        if not code_positions[match.start()]:
            continue
        binding = match.group("binding")
        framework = match.group("module")
        factories[binding] = framework
        if framework == "express":
            factories[f"{binding}.Router"] = framework

    require_destructure = re.compile(
        r"^[ \t]*(?:const|let|var)\s*\{(?P<names>.*?)\}\s*=\s*"
        r"require\s*\(\s*(?P<quote>[\"'])"
        r"(?P<module>express|fastify)(?P=quote)\s*\)",
        re.DOTALL | re.MULTILINE,
    )
    for match in require_destructure.finditer(content):
        if not code_positions[match.start()]:
            continue
        framework = match.group("module")
        allowed = (
            {"Router", "express", "default"}
            if framework == "express"
            else {"fastify", "Fastify", "default"}
        )
        for imported in match.group("names").split(","):
            parts = re.split(r"\s*:\s*", imported.strip())
            original = parts[0].strip()
            if original not in allowed:
                continue
            alias = parts[1].strip() if len(parts) == 2 else original
            factories[alias] = framework
    return factories


def _javascript_receiver_frameworks(content: str) -> dict[str, str]:
    frameworks: dict[str, str] = {}
    factories = _javascript_framework_factories(content)
    code_positions = _javascript_code_positions(content)
    assignment = re.compile(
        r"^[ \t]*(?:const|let|var)\s+"
        r"(?P<receiver>[A-Za-z_$][\w$]*)\s*=\s*"
        r"(?P<factory>[A-Za-z_$][\w$]*(?:\.Router)?)\s*\(",
        re.MULTILINE,
    )
    for match in assignment.finditer(content):
        if not code_positions[match.start()]:
            continue
        framework = factories.get(match.group("factory"))
        if framework is not None:
            frameworks[match.group("receiver")] = framework

    direct_require = re.compile(
        r"^[ \t]*(?:const|let|var)\s+"
        r"(?P<receiver>[A-Za-z_$][\w$]*)\s*=\s*"
        r"require\s*\(\s*(?P<quote>[\"'])(?P<module>express|fastify)"
        r"(?P=quote)\s*\)(?:\.Router)?\s*\(",
        re.MULTILINE,
    )
    for match in direct_require.finditer(content):
        if not code_positions[match.start()]:
            continue
        frameworks[match.group("receiver")] = match.group("module")
    return frameworks


def _fastify_registration_prefix(content: str) -> str:
    code_positions = _javascript_code_positions(content)
    pattern = re.compile(
        r"\.register\s*\([\s\S]{0,1000}?"
        r"\bprefix\s*:\s*[\"'`](?P<prefix>[^\"'`]+)[\"'`]"
    )
    prefixes = {
        match.group("prefix")
        for match in pattern.finditer(content)
        if code_positions[match.start()]
    }
    return next(iter(prefixes)) if len(prefixes) == 1 else ""


def _classify_path(path: str | None) -> str:
    if path is None:
        return "unknown"
    return "internal" if _INTERNAL_PATHS.match(path) else "application"


def _join_routes(prefix: str, suffix: str) -> str:
    joined = "/".join(part.strip("/") for part in (prefix, suffix) if part.strip("/"))
    return f"/{joined}" if joined else "/"


def _could_be_backend_source(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in _CONSERVATIVE_BACKEND_MARKERS)


def _looks_like_backend_source(content: str, suffix: str) -> bool:
    code_positions = (
        _python_code_positions(content)
        if suffix == ".py"
        else _javascript_code_positions(content)
    )
    if suffix == ".py" and _python_framework_factories(content):
        return True
    if suffix != ".py" and _javascript_framework_factories(content):
        return True
    lowered = "".join(
        character if code_positions[index] else " "
        for index, character in enumerate(content)
    ).lower()
    return any(marker in lowered for marker in _QUALIFIED_BACKEND_MARKERS)


def _contains_route_syntax(content: str, suffix: str) -> bool:
    code_positions = (
        _python_code_positions(content)
        if suffix == ".py"
        else _javascript_code_positions(content)
    )
    pattern = re.compile(
        r"(?:@\w+\s*\(|\.\s*(?:route|get|post|put|patch|delete)\s*\()",
        re.IGNORECASE,
    )
    return any(code_positions[match.start()] for match in pattern.finditer(content))


def _python_code_positions(content: str) -> tuple[bool, ...]:
    positions = [True] * len(content)
    line_offsets = [0]
    for line in content.splitlines(keepends=True):
        line_offsets.append(line_offsets[-1] + len(line))

    def absolute(row: int, column: int) -> int:
        line_index = max(0, min(row - 1, len(line_offsets) - 1))
        return min(len(content), line_offsets[line_index] + column)

    try:
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        for token in tokens:
            if token.type not in {tokenize.COMMENT, tokenize.STRING}:
                continue
            start = absolute(*token.start)
            end = absolute(*token.end)
            positions[start:end] = [False] * max(0, end - start)
    except (IndentationError, tokenize.TokenError):
        pass
    return tuple(positions)


def _javascript_code_positions(content: str) -> tuple[bool, ...]:
    positions = [True] * len(content)
    index = 0
    while index < len(content):
        character = content[index]
        following = content[index + 1] if index + 1 < len(content) else ""
        if character == "/" and following in ("/", "*"):
            line_comment = following == "/"
            end = content.find("\n" if line_comment else "*/", index + 2)
            end = len(content) if end == -1 else end + (0 if line_comment else 2)
            positions[index:end] = [False] * (end - index)
            index = end
            continue
        if character in {'"', "'", "`"}:
            quote = character
            end = index + 1
            while end < len(content):
                if content[end] == "\\":
                    end += 2
                    continue
                if content[end] == quote:
                    end += 1
                    break
                end += 1
            positions[index:end] = [False] * (end - index)
            index = end
            continue
        index += 1
    return tuple(positions)


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _bounded_openapi_text(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > _OPENAPI_TEXT_LIMIT:
        return ""
    if any(ord(character) < 32 for character in value) or "<" in value or ">" in value:
        return ""
    return value


def _bounded_openapi_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= _OPENAPI_SCHEMA_DEPTH_LIMIT:
        return {"capability_status": "unknown", "truncated": True}
    if isinstance(value, Mapping):
        rows = sorted(value.items(), key=lambda item: str(item[0]))
        bounded = {
            key: _bounded_openapi_value(raw_value, depth=depth + 1)
            for raw_key, raw_value in rows[:_OPENAPI_SCHEMA_PROPERTY_LIMIT]
            if (key := _bounded_openapi_text(raw_key))
        }
        if len(rows) > _OPENAPI_SCHEMA_PROPERTY_LIMIT:
            bounded.update({"capability_status": "unknown", "truncated": True})
        return bounded
    if isinstance(value, (list, tuple)):
        bounded = [
            _bounded_openapi_value(item, depth=depth + 1)
            for item in value[:_OPENAPI_SCHEMA_VARIANT_LIMIT]
        ]
        if len(value) > _OPENAPI_SCHEMA_VARIANT_LIMIT:
            bounded.append({"capability_status": "unknown", "truncated": True})
        return bounded
    if isinstance(value, str):
        return _bounded_openapi_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None


def _bounded_openapi_names(values: list[Any]) -> tuple[list[str], bool]:
    truncated = len(values) > _OPENAPI_SCHEMA_PROPERTY_LIMIT
    names: list[str] = []
    for raw_name in values[:_OPENAPI_SCHEMA_PROPERTY_LIMIT]:
        name = _bounded_openapi_text(raw_name)
        if not isinstance(raw_name, str) or not name or name != raw_name:
            truncated = True
            continue
        names.append(name)
    return sorted(set(names)), truncated


def _openapi_operation_obligations(
    operation: Mapping[str, Any],
    *,
    method: str = "",
    parameters: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    responses: Mapping[str, Any] | None = None,
    security: Any = None,
    document: Mapping[str, Any] | None = None,
    available_reads: Mapping[str, int] | None = None,
) -> tuple[dict[str, Any], ...]:
    raw = operation.get("x-uidetox-operation")
    raw = raw if isinstance(raw, Mapping) else {}
    obligations: list[dict[str, Any]] = []
    for name in _OPERATION_OBLIGATIONS:
        value = raw.get(name)
        if isinstance(value, bool):
            applicable: bool | None = value
            details: dict[str, Any] = {}
        elif isinstance(value, Mapping):
            raw_applicable = value.get("applicable")
            applicable = raw_applicable if isinstance(raw_applicable, bool) else None
            details = {}
            constraint_unknown = False
            for raw_key, raw_value in sorted(
                value.items(), key=lambda item: str(item[0])
            ):
                if raw_key == "applicable":
                    continue
                key = _bounded_openapi_text(raw_key)
                bounded = _bounded_openapi_value(raw_value)
                if not key or bounded is None or bounded != raw_value:
                    constraint_unknown = True
                    continue
                details[key] = bounded
            if constraint_unknown:
                applicable = None
                details["constraint_status"] = "unknown"
                details["truncated"] = True
        elif value is not None:
            applicable = None
            details = {}
        else:
            continue
        required_details = _OPERATION_OBLIGATION_REQUIRED_DETAILS.get(name, ())
        missing_details = [
            key
            for key in required_details
            if not details.get(key)
            or (key == "operations" and not isinstance(details.get(key), list))
        ]
        if applicable is True and missing_details:
            applicable = None
            details["constraint_status"] = "unknown"
            details["missing_constraints"] = missing_details
        if name == "affected-reads" and applicable is True:
            operations = details.get("operations")
            if isinstance(operations, list):
                invalid_operations = [
                    reference
                    for reference in operations
                    if not isinstance(reference, str)
                    or (available_reads or {}).get(reference) != 1
                ]
                if len(set(map(str, operations))) != len(operations):
                    invalid_operations = list(operations)
            if invalid_operations:
                applicable = None
                details["constraint_status"] = "unknown"
                details["invalid_operations"] = invalid_operations
        obligations.append(
            {
                "kind": "operation_obligation",
                "name": name,
                "ref": f"operation_obligation:{name}",
                "applicable": applicable,
                "capability_status": (
                    "present"
                    if applicable is True
                    else "absent"
                    if applicable is False
                    else "unknown"
                ),
                "provenance": "openapi:x-uidetox-operation",
                "edge": "requires_behavior",
                **details,
            }
        )
    explicit_names = {item["name"] for item in obligations}
    status_codes = {str(status) for status in (responses or {})}
    parameter_names = {
        (location.lower(), name.lower()) for location, name in (parameters or {})
    }
    response_headers: set[str] = set()
    for response_value in (responses or {}).values():
        if not isinstance(response_value, Mapping):
            continue
        response = _resolve_openapi_mapping(response_value, document or {})
        headers = response.get("headers")
        if isinstance(headers, Mapping):
            response_headers.update(str(name).lower() for name in headers)

    native: dict[str, dict[str, Any]] = {}
    native_unknown: dict[str, dict[str, Any]] = {}

    def prove(name: str, **details: Any) -> None:
        if name not in explicit_names:
            native[name] = details

    def investigate(name: str, **details: Any) -> None:
        if name not in explicit_names and name not in native:
            native_unknown[name] = details

    safe_method = method.upper() in {"GET", "HEAD", "OPTIONS"}
    idempotency_header = ("header", "idempotency-key") in parameter_names
    precondition_header = bool(
        parameter_names & {("header", "if-match"), ("header", "if-none-match")}
    )
    retry_signaled = bool(
        status_codes & {"408", "429", "502", "503", "504"}
        or "retry-after" in response_headers
    )
    if safe_method and retry_signaled:
        prove("retry", condition="safe-method")
    elif idempotency_header:
        investigate(
            "retry",
            evidence="request-header:Idempotency-Key",
            missing_constraints=["condition"],
        )
    if idempotency_header:
        investigate(
            "idempotency",
            evidence="request-header:Idempotency-Key",
            missing_constraints=["scope", "retention", "replay"],
        )
        investigate(
            "duplicate-submit",
            evidence="request-header:Idempotency-Key",
            missing_constraints=["mechanism"],
        )
    if status_codes & {"409", "412"} or precondition_header:
        prove(
            "conflict",
            statuses=sorted(status_codes & {"409", "412"}),
            precondition=precondition_header,
        )
    if "207" in status_codes:
        prove("partial-success", statuses=["207"])
    if "429" in status_codes:
        prove("rate-limit", statuses=["429"])
    if status_codes & {"408", "504"}:
        prove("timeout", statuses=sorted(status_codes & {"408", "504"}))
    validation_statuses = sorted(status_codes & {"400", "422"})
    proven_validation_statuses = [
        status
        for status in validation_statuses
        if _validation_schema_has_field_association(
            _openapi_content_schema((responses or {}).get(status), document or {})
        )
    ]
    if proven_validation_statuses:
        prove("validation", statuses=proven_validation_statuses)
    elif validation_statuses:
        investigate(
            "validation",
            statuses=validation_statuses,
            missing_constraints=["field-error-schema"],
        )
    if "403" in status_codes:
        prove("forbidden", statuses=["403"])
    if safe_method and response_headers & {"etag", "last-modified"}:
        prove(
            "stale-refresh",
            validators=sorted(response_headers & {"etag", "last-modified"}),
        )
    if isinstance(security, list):
        requirements = [item for item in security if isinstance(item, Mapping)]
        schemes = {str(name) for item in requirements for name in item}
        if schemes and not any(not item for item in requirements):
            prove("auth-required", schemes=sorted(schemes))

    for name, details in sorted(native.items()):
        obligations.append(
            {
                "kind": "operation_obligation",
                "name": name,
                "ref": f"operation_obligation:{name}",
                "applicable": True,
                "capability_status": "present",
                "provenance": "openapi:native-operation",
                "edge": "requires_behavior",
                **details,
            }
        )
    for name, details in sorted(native_unknown.items()):
        obligations.append(
            {
                "kind": "operation_obligation",
                "name": name,
                "ref": f"operation_obligation:{name}",
                "applicable": None,
                "capability_status": "unknown",
                "provenance": "openapi:native-operation",
                "edge": "requires_behavior",
                "constraint_status": "unknown",
                **details,
            }
        )
    return tuple(obligations)


def _openapi_operation_contract(
    path_item: Mapping[str, Any],
    operation: Mapping[str, Any],
    document: Mapping[str, Any],
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "kind": "operation_contract",
        "name": str(operation.get("operationId") or "operation"),
        "ref": "operation_contract",
    }
    version = document.get("openapi", document.get("swagger"))
    if isinstance(version, str):
        contract["openapi_version"] = version
    dialect = document.get("jsonSchemaDialect")
    if isinstance(dialect, str):
        contract["json_schema_dialect"] = dialect
    operation_id = operation.get("operationId")
    if isinstance(operation_id, str):
        contract["operation_id"] = operation_id
    if isinstance(operation.get("deprecated"), bool):
        contract["deprecated"] = operation["deprecated"]

    raw_servers = operation.get("servers")
    if not isinstance(raw_servers, list):
        raw_servers = path_item.get("servers")
    if not isinstance(raw_servers, list):
        raw_servers = document.get("servers")
    if isinstance(raw_servers, list):
        servers = []
        for value in raw_servers:
            if not isinstance(value, Mapping) or not isinstance(value.get("url"), str):
                continue
            server = {"url": value["url"]}
            variables = value.get("variables")
            if isinstance(variables, Mapping):
                server["variables"] = _json_value(variables)
            servers.append(server)
        if servers:
            contract["servers"] = servers
    callbacks = operation.get("callbacks")
    if isinstance(callbacks, Mapping):
        contract["callbacks"] = sorted(str(name) for name in callbacks)
    return contract


def _openapi_transport_lineage(
    path_item: Mapping[str, Any],
    operation: Mapping[str, Any],
    responses: Mapping[str, Any],
    security: Any,
    document: Mapping[str, Any],
    *,
    method: str = "",
    available_reads: Mapping[str, int] | None = None,
) -> tuple[dict[str, Any], ...]:
    lineage: list[dict[str, Any]] = [
        _openapi_operation_contract(path_item, operation, document)
    ]
    parameters = _openapi_parameters(path_item, operation, document)
    swagger_2 = str(document.get("swagger", "")).startswith("2.")

    for (location, name), parameter in sorted(parameters.items()):
        if location not in {"body", "cookie", "formData", "header", "path", "query"}:
            continue
        item: dict[str, Any] = {
            "kind": "api_parameter",
            "name": name,
            "ref": f"api_parameter:{location}:{name}",
            "location": location,
            "required": parameter.get("required") is True,
            "provenance": "openapi:parameter",
            "edge": "declares_parameter",
        }
        if swagger_2:
            collection_format = parameter.get("collectionFormat")
            if isinstance(collection_format, str):
                item["collection_format"] = collection_format
        else:
            default_style = "form" if location in {"query", "cookie"} else "simple"
            style = parameter.get("style")
            item["style"] = style if isinstance(style, str) else default_style
            explode = parameter.get("explode")
            item["explode"] = (
                explode if isinstance(explode, bool) else item["style"] == "form"
            )
        schema = parameter.get("schema")
        if not isinstance(schema, Mapping) and swagger_2:
            schema = {
                key: parameter[key]
                for key in ("default", "enum", "format", "items", "type")
                if key in parameter
            }
        if isinstance(schema, Mapping):
            item["schema"] = _openapi_schema_shape(schema, document)
        for key in (
            "deprecated",
            "allowEmptyValue",
            "allowReserved",
        ):
            value = parameter.get(key)
            if isinstance(value, (bool, str)):
                item[key] = value
        lineage.append(item)

    request_body = operation.get("requestBody")
    if request_body is None:
        request_body = next(
            (
                parameter
                for (location, _name), parameter in parameters.items()
                if location == "body"
            ),
            None,
        )
    resolved_request_body = (
        _resolve_openapi_mapping(request_body, document)
        if isinstance(request_body, Mapping)
        else {}
    )
    request_required = resolved_request_body.get("required") is True
    request_media = _openapi_media_schemas(request_body, document)
    if swagger_2 and not request_media and isinstance(request_body, Mapping):
        schema = _openapi_content_schema(request_body, document)
        request_media = tuple(
            (media_type, schema)
            for media_type in _swagger_media_types(operation, document, "consumes")
        )
    for media_type, schema in request_media:
        item = {
            "kind": "request_media_type",
            "name": media_type,
            "ref": f"request_media_type:{media_type}",
            "required": request_required,
            "provenance": "openapi:request-body",
            "edge": "accepts_media_type",
        }
        if schema is not None:
            item["schema"] = schema
        lineage.append(item)

    for status, response_value in sorted(responses.items()):
        response_media = _openapi_media_schemas(response_value, document)
        if swagger_2 and not response_media:
            schema = _openapi_content_schema(response_value, document)
            response_media = tuple(
                (media_type, schema)
                for media_type in _swagger_media_types(operation, document, "produces")
            )
        for media_type, schema in response_media:
            item = {
                "kind": "response_media_type",
                "name": media_type,
                "ref": f"response_media_type:{status}:{media_type}",
                "status": status,
                "provenance": "openapi:response",
                "edge": "returns_media_type",
            }
            if schema is not None:
                item["schema"] = schema
            lineage.append(item)
        if not isinstance(response_value, Mapping):
            continue
        response = _resolve_openapi_mapping(response_value, document)
        headers = response.get("headers")
        if isinstance(headers, Mapping):
            for header_name, header_value in sorted(
                headers.items(), key=lambda item: str(item[0]).lower()
            ):
                if not isinstance(header_value, Mapping):
                    continue
                header = _resolve_openapi_mapping(header_value, document)
                item = {
                    "kind": "response_header",
                    "name": str(header_name),
                    "ref": f"response_header:{status}:{header_name}",
                    "status": status,
                    "provenance": "openapi:response-header",
                    "edge": "returns_header",
                }
                schema = header.get("schema")
                if isinstance(schema, Mapping):
                    item["schema"] = _openapi_schema_shape(schema, document)
                lineage.append(item)
        links = response.get("links")
        if isinstance(links, Mapping):
            link_rows = sorted(links.items(), key=lambda item: str(item[0]))
            for link_name, link_value in link_rows[:_OPENAPI_SCHEMA_VARIANT_LIMIT]:
                if not isinstance(link_value, Mapping):
                    continue
                link = _resolve_openapi_mapping(link_value, document)
                lineage.append(
                    {
                        "kind": "response_link",
                        "name": str(link_name),
                        "ref": f"response_link:{status}:{link_name}",
                        "status": status,
                        "operation_id": link.get("operationId"),
                        "operation_ref": link.get("operationRef"),
                        "parameters": _bounded_openapi_value(
                            link.get("parameters", {})
                        ),
                        "provenance": "openapi:response-link",
                        "edge": "returns_link",
                    }
                )
            if len(link_rows) > _OPENAPI_SCHEMA_VARIANT_LIMIT:
                lineage.append(
                    {
                        "kind": "contract_evidence_limit",
                        "name": "response_links",
                        "ref": f"contract_evidence_limit:{status}:response_links",
                        "status": status,
                        "axis": "response_links",
                        "observed_count": len(link_rows),
                        "limit": _OPENAPI_SCHEMA_VARIANT_LIMIT,
                        "truncated": True,
                        "capability_status": "unknown",
                        "provenance": "openapi:response-link",
                        "edge": "documents",
                    }
                )

    if isinstance(security, list):
        normalized_requirements = {
            tuple(
                sorted(
                    (
                        str(scheme),
                        (
                            tuple(sorted({str(scope) for scope in raw_scopes}))
                            if isinstance(raw_scopes, list)
                            else ()
                        ),
                    )
                    for scheme, raw_scopes in requirement.items()
                )
            )
            for requirement in security
            if isinstance(requirement, Mapping)
        }
        for index, requirement in enumerate(sorted(normalized_requirements)):
            parent = f"auth_alternative:{index}"
            lineage.append(
                {
                    "kind": "auth_alternative",
                    "name": f"alternative:{index + 1}",
                    "ref": parent,
                    "allows_anonymous": not requirement,
                    "provenance": "openapi:security",
                    "edge": "allows",
                }
            )
            for scheme, scopes in requirement:
                item = {
                    "kind": "auth_scheme_requirement",
                    "name": str(scheme),
                    "ref": f"auth_scheme_requirement:{index}:{scheme}",
                    "parent": parent,
                    "scopes": scopes,
                    "provenance": "openapi:security",
                    "edge": "requires",
                }
                components = document.get("components")
                definitions = (
                    components.get("securitySchemes")
                    if isinstance(components, Mapping)
                    else None
                )
                definition = (
                    definitions.get(scheme)
                    if isinstance(definitions, Mapping)
                    else None
                )
                if isinstance(definition, Mapping):
                    item["scheme"] = _bounded_openapi_value(
                        _resolve_openapi_mapping(definition, document)
                    )
                lineage.append(item)
    lineage.extend(
        _openapi_operation_obligations(
            operation,
            method=method,
            parameters=parameters,
            responses=responses,
            security=security,
            document=document,
            available_reads=(
                available_reads
                if available_reads is not None
                else _openapi_read_operation_counts(document)
            ),
        )
    )
    return _bounded_openapi_lineage(lineage)


def _bounded_openapi_lineage(
    values: list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Bound one operation's graph evidence and emit one fail-closed diagnostic."""

    output: list[dict[str, Any]] = []
    used_bytes = 0
    truncated = len(values) > _OPENAPI_LINEAGE_ITEM_LIMIT
    for raw in values[:_OPENAPI_LINEAGE_ITEM_LIMIT]:
        bounded = _bounded_openapi_value(raw)
        if not isinstance(bounded, dict):
            truncated = True
            continue
        if bounded != raw:
            truncated = True
        kind = bounded.get("kind")
        name = bounded.get("name")
        reference = bounded.get("ref")
        if kind == "operation_contract" and not name:
            bounded["name"] = "operation"
        elif not kind or not name or not reference:
            truncated = True
            continue
        encoded_bytes = len(
            json.dumps(bounded, sort_keys=True, default=str).encode("utf-8")
        )
        if used_bytes + encoded_bytes > _OPENAPI_LINEAGE_BYTE_LIMIT:
            truncated = True
            break
        used_bytes += encoded_bytes
        output.append(bounded)
    if truncated:
        output.append(
            {
                "kind": "contract_evidence_limit",
                "name": "operation_transport",
                "ref": "contract_evidence_limit:operation_transport",
                "axis": "operation_transport",
                "observed_count": len(values),
                "emitted_count": len(output),
                "item_limit": _OPENAPI_LINEAGE_ITEM_LIMIT,
                "byte_limit": _OPENAPI_LINEAGE_BYTE_LIMIT,
                "emitted_bytes": used_bytes,
                "truncated": True,
                "capability_status": "unknown",
                "provenance": "openapi:bounded-operation",
                "edge": "documents",
            }
        )
    return tuple(output)


def _openapi_media_schemas(
    value: Any,
    document: Mapping[str, Any],
) -> tuple[tuple[str, dict[str, Any] | None], ...]:
    if not isinstance(value, Mapping):
        return ()
    resolved_value = _resolve_openapi_mapping(value, document)
    content = resolved_value.get("content")
    if not isinstance(content, Mapping):
        return ()
    return tuple(
        (
            str(media_type),
            _openapi_schema_shape(schema, document)
            if isinstance((schema := item.get("schema")), Mapping)
            else None,
        )
        for media_type, item in sorted(content.items(), key=lambda row: str(row[0]))
        if isinstance(item, Mapping)
    )


def _openapi_content_schema(
    value: Any,
    document: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    resolved_value = _resolve_openapi_mapping(value, document)
    if not isinstance(resolved_value, Mapping):
        return None
    schema: Any = resolved_value.get("schema")
    if schema is None:
        content = resolved_value.get("content")
        if isinstance(content, Mapping):
            media = content.get("application/json")
            if not isinstance(media, Mapping):
                media = next(
                    (item for item in content.values() if isinstance(item, Mapping)),
                    None,
                )
            schema = media.get("schema") if isinstance(media, Mapping) else None
    if not isinstance(schema, Mapping):
        return None
    return _openapi_schema_shape(schema, document)


def _resolve_openapi_mapping(
    value: Mapping[str, Any],
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    reference = value.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return value
    target: Any = document
    for part in reference[2:].split("/"):
        if not isinstance(target, Mapping):
            return value
        target = target.get(part.replace("~1", "/").replace("~0", "~"))
    return target if isinstance(target, Mapping) else value


def _openapi_schema_shape(
    schema: Mapping[str, Any],
    document: Mapping[str, Any],
    seen: tuple[str, ...] = (),
    depth: int = 0,
) -> dict[str, Any]:
    budget = {"nodes": 0, "truncated": 0}
    result = _openapi_schema_shape_bounded(schema, document, seen, depth, budget)
    encoded_bytes = len(json.dumps(result, sort_keys=True, default=str).encode("utf-8"))
    if encoded_bytes > _OPENAPI_SCHEMA_BYTE_LIMIT:
        return _openapi_schema_limit(
            "byte_limit",
            observed=encoded_bytes,
            limit=_OPENAPI_SCHEMA_BYTE_LIMIT,
        )
    if budget["truncated"]:
        result.update(
            {
                "axis": "schema",
                "capability_status": "unknown",
                "truncated": True,
                "observed_nodes": budget["nodes"],
                "node_limit": _OPENAPI_SCHEMA_NODE_LIMIT,
            }
        )
    return result


def _openapi_schema_limit(reason: str, *, observed: int, limit: int) -> dict[str, Any]:
    return {
        "type": "unknown",
        "axis": "schema",
        "capability_status": "unknown",
        "truncated": True,
        "limit_reason": reason,
        "observed": observed,
        "limit": limit,
    }


def _openapi_schema_shape_bounded(
    schema: Mapping[str, Any],
    document: Mapping[str, Any],
    seen: tuple[str, ...],
    depth: int,
    budget: dict[str, int],
) -> dict[str, Any]:
    budget["nodes"] += 1
    if budget["nodes"] > _OPENAPI_SCHEMA_NODE_LIMIT:
        budget["truncated"] = 1
        return _openapi_schema_limit(
            "node_limit",
            observed=budget["nodes"],
            limit=_OPENAPI_SCHEMA_NODE_LIMIT,
        )
    reference = schema.get("$ref")
    name = ""
    if depth >= _OPENAPI_SCHEMA_DEPTH_LIMIT:
        return {"type": "unknown", "capability_status": "unknown", "truncated": True}
    if isinstance(reference, str):
        bounded_reference = _bounded_openapi_text(reference)
        if not bounded_reference or bounded_reference != reference:
            budget["truncated"] = 1
            return _openapi_schema_limit(
                "reference",
                observed=len(reference),
                limit=_OPENAPI_TEXT_LIMIT,
            )
        reference = bounded_reference
        name = _bounded_openapi_text(reference.rsplit("/", 1)[-1])
        if reference in seen:
            return {
                "name": name,
                "reference": reference,
                "type": "recursive",
                "capability_status": "unknown",
            }
        schema = _resolve_openapi_mapping(schema, document)
        seen = (*seen, reference)
    if isinstance(schema.get("allOf"), list):
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        all_of = schema["allOf"]
        variants = all_of[:_OPENAPI_SCHEMA_VARIANT_LIMIT]
        merged["allOf"] = []
        for member in variants:
            if not isinstance(member, Mapping):
                continue
            shape = _openapi_schema_shape_bounded(
                member, document, seen, depth + 1, budget
            )
            merged["allOf"].append(shape)
            merged["properties"].update(shape.get("properties", {}))
            merged["required"].extend(shape.get("required", []))
        if name:
            merged["name"] = name
        if isinstance(reference, str):
            merged["reference"] = reference
        merged["required"], required_truncated = _bounded_openapi_names(
            merged["required"]
        )
        if len(all_of) > _OPENAPI_SCHEMA_VARIANT_LIMIT or required_truncated:
            merged["truncated"] = True
            merged["capability_status"] = "unknown"
        return merged
    raw_type = schema.get("type")
    nullable = bool(schema.get("nullable", False))
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        non_null = [
            bounded
            for item in raw_type
            if item != "null"
            and (bounded := _bounded_openapi_text(item))
            and bounded == item
        ]
        if len(non_null) != len([item for item in raw_type if item != "null"]):
            budget["truncated"] = 1
        normalized_type: Any = non_null[0] if len(non_null) == 1 else non_null
    else:
        normalized_type = (
            _bounded_openapi_text(raw_type)
            if raw_type
            else (
                "object" if isinstance(schema.get("properties"), Mapping) else "unknown"
            )
        )
        if raw_type and normalized_type != raw_type:
            budget["truncated"] = 1
            normalized_type = "unknown"
    result: dict[str, Any] = {"type": normalized_type}
    if name:
        result["name"] = name
    if isinstance(reference, str):
        result["reference"] = reference
    if nullable:
        result["nullable"] = True
    for key in (
        "enum",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
        "uniqueItems",
        "default",
        "const",
        "readOnly",
        "writeOnly",
        "additionalProperties",
        "unevaluatedProperties",
    ):
        if key in schema:
            raw_value = schema[key]
            bounded = _bounded_openapi_value(raw_value)
            result[key] = bounded
            if bounded != raw_value:
                result["truncated"] = True
                result["capability_status"] = "unknown"
    required = schema.get("required")
    if isinstance(required, list):
        result["required"], required_truncated = _bounded_openapi_names(required)
        if required_truncated:
            result["truncated"] = True
            result["capability_status"] = "unknown"
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        property_rows = sorted(properties.items(), key=lambda item: str(item[0]))
        result["properties"] = {}
        property_truncated = len(property_rows) > _OPENAPI_SCHEMA_PROPERTY_LIMIT
        for raw_name, field in property_rows[:_OPENAPI_SCHEMA_PROPERTY_LIMIT]:
            field_name = _bounded_openapi_text(raw_name)
            if (
                not isinstance(raw_name, str)
                or not field_name
                or field_name != raw_name
                or not isinstance(field, Mapping)
            ):
                property_truncated = True
                continue
            result["properties"][field_name] = _openapi_schema_shape_bounded(
                field, document, seen, depth + 1, budget
            )
        if property_truncated:
            result["property_count"] = len(property_rows)
            result["truncated"] = True
            result["capability_status"] = "unknown"
    items = schema.get("items")
    if isinstance(items, Mapping):
        result["items"] = _openapi_schema_shape_bounded(
            items, document, seen, depth + 1, budget
        )
    for composition in ("oneOf", "anyOf"):
        values = schema.get(composition)
        if isinstance(values, list):
            result[composition] = [
                _openapi_schema_shape_bounded(value, document, seen, depth + 1, budget)
                for value in values[:_OPENAPI_SCHEMA_VARIANT_LIMIT]
                if isinstance(value, Mapping)
            ]
            if len(values) > _OPENAPI_SCHEMA_VARIANT_LIMIT:
                result["truncated"] = True
                result["capability_status"] = "unknown"
    discriminator = schema.get("discriminator")
    if isinstance(discriminator, Mapping):
        bounded = _bounded_openapi_value(discriminator)
        result["discriminator"] = bounded
        if bounded != discriminator:
            result["truncated"] = True
            result["capability_status"] = "unknown"
    return result


def _python_provenance(
    tree: ast.Module,
    classes: Mapping[str, ast.ClassDef],
) -> _PythonProvenance:
    """Resolve framework capabilities only from qualified import provenance."""

    model_bases: set[str] = set()
    declarative_bases: set[str] = set()
    declarative_factories: set[str] = set()
    dependency_injectors: set[str] = set()
    mapped_annotations: set[str] = set()
    security_injectors: set[str] = set()
    security_factories: set[str] = set()
    security_bindings: set[str] = set()
    for statement in tree.body:
        if not isinstance(statement, ast.ImportFrom):
            continue
        module = statement.module or ""
        for imported in statement.names:
            binding = imported.asname or imported.name
            if module == "pydantic" and imported.name == "BaseModel":
                model_bases.add(binding)
            elif module == "sqlalchemy.orm" and imported.name == "DeclarativeBase":
                declarative_bases.add(binding)
            elif module == "sqlalchemy.orm" and imported.name == "declarative_base":
                declarative_factories.add(binding)
            elif module == "sqlalchemy.orm" and imported.name == "Mapped":
                mapped_annotations.add(binding)
            elif module == "fastapi" and imported.name == "Depends":
                dependency_injectors.add(binding)
            elif module == "fastapi" and imported.name == "Security":
                security_injectors.add(binding)
            elif module.startswith("fastapi.security"):
                security_factories.add(binding)

    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        value = statement.value
        if not isinstance(value, ast.Call):
            continue
        targets = (
            statement.targets
            if isinstance(statement, ast.Assign)
            else [statement.target]
        )
        names = {target.id for target in targets if isinstance(target, ast.Name)}
        callee = _dotted_name(value.func)
        if callee in declarative_factories:
            declarative_bases.update(names)
        if callee in security_factories:
            security_bindings.update(names)

    model_classes: set[str] = set()
    entity_classes: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, node in classes.items():
            bases = {_dotted_name(base) for base in node.bases}
            if name not in model_classes and bases & (model_bases | model_classes):
                model_classes.add(name)
                changed = True
            if _python_class_has_table(node):
                if name not in entity_classes:
                    entity_classes.add(name)
                    changed = True
            elif bases & entity_classes and name not in entity_classes:
                entity_classes.add(name)
                changed = True
            elif bases & declarative_bases:
                declarative_bases.add(name)

    return _PythonProvenance(
        model_classes=frozenset(model_classes),
        entity_classes=frozenset(entity_classes),
        dependency_injectors=frozenset(dependency_injectors),
        mapped_annotations=frozenset(mapped_annotations),
        security_injectors=frozenset(security_injectors),
        security_bindings=frozenset(security_bindings),
    )


def _python_class_has_table(node: ast.ClassDef) -> bool:
    for statement in node.body:
        targets: Iterable[ast.expr]
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = (statement.target,)
        else:
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in targets
        ):
            return True
    return False


def _enrich_python_operations(
    operations: Iterable[ContractObservation],
    content: str,
) -> list[ContractObservation]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return list(operations)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    provenance = _python_provenance(tree, classes)
    model_schemas = {
        name: _python_class_schema(node, classes, provenance)
        for name, node in classes.items()
        if _python_class_kind(node, provenance) == "model"
    }
    entities = {
        name: _python_class_fields(node, classes, provenance)
        for name, node in classes.items()
        if _python_class_kind(node, provenance) == "entity"
    }
    return [
        _enrich_python_operation(
            operation, functions, classes, model_schemas, entities, provenance
        )
        for operation in operations
    ]


def _enrich_python_operation(
    operation: ContractObservation,
    functions: Mapping[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: Mapping[str, ast.ClassDef],
    model_schemas: Mapping[str, dict[str, Any]],
    entities: Mapping[str, dict[str, dict[str, Any]]],
    provenance: _PythonProvenance,
) -> ContractObservation:
    source_line = operation.sources[0].line if operation.sources else 0
    handler = next(
        (
            node
            for node in functions.values()
            if any(decorator.lineno == source_line for decorator in node.decorator_list)
        ),
        None,
    )
    if handler is None:
        return operation
    security_names: list[str] = []
    generic_dependency = False
    request_schemas = operation.request_schemas
    positional = [*handler.args.posonlyargs, *handler.args.args]
    defaults = [None] * (len(positional) - len(handler.args.defaults)) + list(
        handler.args.defaults
    )
    for argument, default in zip(positional, defaults, strict=True):
        if isinstance(default, ast.Call):
            injector = _dotted_name(default.func)
            dependency = _dotted_name(default.args[0]) if default.args else ""
            if (
                injector
                in (provenance.security_injectors | provenance.dependency_injectors)
                and dependency in provenance.security_bindings
            ):
                security_names.append(dependency)
                continue
            if injector.rsplit(".", 1)[-1] == "Depends":
                generic_dependency = True
                continue
        annotation_name = _annotation_name(argument.annotation)
        if annotation_name in model_schemas and not request_schemas:
            request_schemas = contract_schema_observations(
                model_schemas[annotation_name],
                fallback=annotation_name,
            )
    response_schemas = operation.response_schemas
    status_codes = list(operation.status_codes)
    for decorator in handler.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "response_model":
                response_name = _annotation_name(keyword.value)
                if response_name in model_schemas:
                    response_schemas = contract_schema_observations(
                        model_schemas[response_name],
                        fallback=response_name,
                    )
            elif keyword.arg == "status_code":
                status = _ast_literal(keyword.value)
                if status is not None:
                    status_codes.append(str(status))
            elif keyword.arg == "dependencies":
                generic_dependency = True
    if not response_schemas:
        return_name = _annotation_name(handler.returns)
        if return_name in model_schemas:
            response_schemas = contract_schema_observations(
                model_schemas[return_name],
                fallback=return_name,
            )

    anchor = operation.sources[0] if operation.sources else _unknown_anchor()
    lineage: list[dict[str, Any]] = [
        {
            "kind": "handler",
            "name": handler.name,
            "ref": f"handler:{handler.name}",
            "parent": "operation",
            "source": asdict(replace(anchor, line=handler.lineno)),
            "provenance": "python:decorated-handler",
        }
    ]
    calls = _function_call_names(handler)
    service_names = [
        name for name in calls if name in functions and name != handler.name
    ]
    entity_parents: list[tuple[str, str]] = [
        (name, f"handler:{handler.name}") for name in calls if name in entities
    ]
    for service_name in service_names:
        service = functions[service_name]
        lineage.append(
            {
                "kind": "service_operation",
                "name": service_name,
                "ref": f"service:{service_name}",
                "parent": f"handler:{handler.name}",
                "source": asdict(replace(anchor, line=service.lineno)),
                "provenance": "python:call-expression",
            }
        )
        entity_parents.extend(
            (name, f"service:{service_name}")
            for name in _function_call_names(service)
            if name in entities
        )
    for entity_name, parent in dict.fromkeys(entity_parents):
        entity = classes[entity_name]
        lineage.append(
            {
                "kind": "entity",
                "name": entity_name,
                "ref": f"entity:{parent}:{entity_name}",
                "parent": parent,
                "source": asdict(replace(anchor, line=entity.lineno)),
                "provenance": "python:constructor-reference",
                "fields": entities[entity_name],
            }
        )
    lineage.extend(
        {
            "kind": "auth_requirement",
            "name": name,
            "source": asdict(replace(anchor, line=handler.lineno)),
            "provenance": "fastapi:Security",
        }
        for name in dict.fromkeys(security_names)
    )
    evidence = {
        **operation.evidence,
        "request": (
            _schema_observation_state(request_schemas)
            if request_schemas
            else operation.evidence.get("request", "unknown")
        ),
        "response": (
            _schema_observation_state(
                response_schemas,
                statuses_distinguish=True,
            )
            if response_schemas
            else operation.evidence.get("response", "unknown")
        ),
        "status": (
            "present" if status_codes else operation.evidence.get("status", "unknown")
        ),
    }
    auth = (
        "present"
        if security_names
        else "unknown"
        if generic_dependency
        else operation.auth
    )
    return replace(
        operation,
        request_schemas=request_schemas,
        response_schemas=response_schemas,
        status_codes=tuple(sorted(set(status_codes))),
        auth=auth,
        authorization="absent" if auth == "absent" else operation.authorization,
        tenant="absent" if auth == "absent" else operation.tenant,
        handler=handler.name,
        lineage=tuple(lineage),
        evidence=evidence,
    )


def _enrich_javascript_operation(
    operation: ContractObservation,
    content: str,
) -> ContractObservation:
    source_line = operation.sources[0].line if operation.sources else 0
    lines = content.splitlines()
    line = lines[source_line - 1] if 0 < source_line <= len(lines) else ""
    handler_match = re.search(
        r",\s*(?P<handler>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)\s*\)?\s*;?\s*$",
        line,
    )
    if handler_match is None:
        return operation
    handler = handler_match.group("handler")
    anchor = operation.sources[0] if operation.sources else _unknown_anchor()
    return replace(
        operation,
        handler=handler,
        lineage=(
            {
                "kind": "handler",
                "name": handler,
                "ref": f"handler:{handler}",
                "parent": "operation",
                "source": asdict(anchor),
                "provenance": "javascript:route-handler-argument",
                "capability_status": "present",
            },
        ),
    )


def _python_class_kind(
    node: ast.ClassDef,
    provenance: _PythonProvenance,
) -> str:
    if node.name in provenance.model_classes:
        return "model"
    if node.name in provenance.entity_classes:
        return "entity"
    return "unknown"


def _python_class_schema(
    node: ast.ClassDef,
    classes: Mapping[str, ast.ClassDef],
    provenance: _PythonProvenance,
) -> dict[str, Any]:
    properties = _python_class_fields(node, classes, provenance)
    required = [
        statement.target.id
        for statement in node.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.value is None
        and not _annotation_nullable(statement.annotation)
    ]
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
    }


def _python_class_fields(
    node: ast.ClassDef,
    classes: Mapping[str, ast.ClassDef],
    provenance: _PythonProvenance,
) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(
            statement.target, ast.Name
        ):
            continue
        fields[statement.target.id] = _python_annotation_schema(
            statement.annotation, classes, provenance
        )
    return fields


def _python_annotation_schema(
    annotation: ast.expr | None,
    classes: Mapping[str, ast.ClassDef],
    provenance: _PythonProvenance,
) -> dict[str, Any]:
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        alternatives = (annotation.left, annotation.right)
        concrete = next(
            (
                item
                for item in alternatives
                if _annotation_name(item) not in {"None", "NoneType"}
            ),
            None,
        )
        result = _python_annotation_schema(concrete, classes, provenance)
        result["nullable"] = True
        return result
    if isinstance(annotation, ast.Subscript):
        annotation_base = _dotted_name(annotation.value)
        if annotation_base in provenance.mapped_annotations:
            return _python_annotation_schema(annotation.slice, classes, provenance)
        if _annotation_name(annotation.value) == "Optional":
            result = _python_annotation_schema(annotation.slice, classes, provenance)
            result["nullable"] = True
            return result
    name = _annotation_name(annotation)
    lowered = name.lower()
    scalar = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "dict": "object",
        "any": "unknown",
    }
    if lowered in {"list", "tuple", "set", "sequence"} and isinstance(
        annotation, ast.Subscript
    ):
        return {
            "type": "array",
            "items": _python_annotation_schema(annotation.slice, classes, provenance),
        }
    if isinstance(annotation, ast.Subscript) and name in classes:
        return {"type": "unknown"}
    if name in classes:
        return {"name": name, "type": "object"}
    result = {"type": scalar.get(lowered, "unknown")}
    if _annotation_nullable(annotation):
        result["nullable"] = True
    return result


def _annotation_nullable(annotation: ast.expr | None) -> bool:
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotation_name(annotation.left) in {
            "None",
            "NoneType",
        } or _annotation_name(annotation.right) in {"None", "NoneType"}
    if isinstance(annotation, ast.Subscript):
        return _annotation_name(annotation.value) == "Optional"
    return False


def _annotation_name(annotation: ast.expr | None) -> str:
    if annotation is None:
        return ""
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Subscript):
        return _annotation_name(annotation.value)
    if isinstance(annotation, ast.Constant):
        return str(annotation.value)
    return ""


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _function_call_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _dotted_name(candidate.func).rsplit(".", 1)[-1]
            for candidate in ast.walk(node)
            if isinstance(candidate, ast.Call) and _dotted_name(candidate.func)
        )
    )


def _ast_literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
