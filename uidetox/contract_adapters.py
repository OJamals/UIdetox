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


_CODE_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".py"}


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


def extract_backend_observations(
    root: Path,
) -> tuple[list[ContractObservation], dict[str, Any]]:
    operations: list[ContractObservation] = []
    adapters: set[str] = set()
    source_manifest: dict[str, str] = {}
    files_scanned = 0
    unknown = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in _IGNORED_DIRS for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        if _is_test_source(relative):
            continue
        lower_name = path.name.lower()
        if path.suffix.lower() in {".json", ".yaml", ".yml"} and (
            lower_name.startswith(("openapi", "swagger"))
        ):
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            source_manifest[relative] = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()
            files_scanned += 1
            extracted = _extract_openapi(path, relative)
            if extracted:
                adapters.add("openapi")
                operations.extend(extracted)
            else:
                operations.append(_unknown_backend(relative, "openapi", "openapi"))
                unknown += 1
            continue
        if path.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        suffix = path.suffix.lower()
        if not _looks_like_backend_source(content, suffix):
            continue
        source_manifest[relative] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        files_scanned += 1
        extracted: list[ContractObservation] = []
        if suffix == ".py":
            extracted, found_adapters = _extract_python_routes(relative, content)
        else:
            extracted, found_adapters = _extract_javascript_routes(relative, content)
        if extracted:
            operations.extend(extracted)
            adapters.update(found_adapters)
            unknown += sum(item.classification == "unknown" for item in extracted)
        elif _contains_route_syntax(content, suffix):
            operations.append(_unknown_backend(relative, "unknown", "route-syntax"))
            unknown += 1
    return operations, {
        "adapters": adapters,
        "files_scanned": files_scanned,
        "unknown": unknown,
        "source_manifest": dict(sorted(source_manifest.items())),
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


def _extract_openapi(path: Path, relative: str) -> list[ContractObservation]:
    try:
        if path.suffix.lower() == ".json":
            document = json.loads(path.read_text(encoding="utf-8"))
        else:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError):
        return []
    if not isinstance(document, Mapping) or not isinstance(
        document.get("paths"), Mapping
    ):
        return []
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
            request_schema = _openapi_content_schema(
                operation.get("requestBody"), document
            )
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
                if str(status).startswith(("4", "5"))
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
            if security is None:
                auth = "absent"
                security_names: tuple[str, ...] = ()
            elif security == []:
                auth = "absent"
                security_names = ()
            else:
                auth = "present"
                security_names = tuple(
                    sorted(
                        {
                            str(name)
                            for requirement in security
                            if isinstance(requirement, Mapping)
                            for name in requirement
                        }
                    )
                )
            lineage = tuple(
                {
                    "kind": "auth_requirement",
                    "name": name,
                    "provenance": "openapi:security",
                }
                for name in security_names
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
                    status_codes=tuple(sorted((*success_statuses, *error_statuses))),
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
    markers = (
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
    return any(marker in lowered for marker in markers)


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
) -> dict[str, Any]:
    reference = schema.get("$ref")
    name = ""
    if isinstance(reference, str):
        name = reference.rsplit("/", 1)[-1]
        if reference in seen:
            return {"name": name, "type": "recursive", "capability_status": "unknown"}
        schema = _resolve_openapi_mapping(schema, document)
        seen = (*seen, reference)
    if isinstance(schema.get("allOf"), list):
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for member in schema["allOf"]:
            if not isinstance(member, Mapping):
                continue
            shape = _openapi_schema_shape(member, document, seen)
            merged["properties"].update(shape.get("properties", {}))
            merged["required"].extend(shape.get("required", []))
        if name:
            merged["name"] = name
        merged["required"] = sorted(set(merged["required"]))
        return merged
    raw_type = schema.get("type")
    nullable = bool(schema.get("nullable", False))
    if isinstance(raw_type, list):
        nullable = nullable or "null" in raw_type
        non_null = [str(item) for item in raw_type if item != "null"]
        normalized_type: Any = non_null[0] if len(non_null) == 1 else non_null
    else:
        normalized_type = raw_type or (
            "object" if isinstance(schema.get("properties"), Mapping) else "unknown"
        )
    result: dict[str, Any] = {"type": normalized_type}
    if name:
        result["name"] = name
    if nullable:
        result["nullable"] = True
    for key in (
        "enum",
        "format",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
    ):
        if key in schema:
            result[key] = _json_value(schema[key])
    required = schema.get("required")
    if isinstance(required, list):
        result["required"] = sorted(str(item) for item in required)
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        result["properties"] = {
            str(field_name): _openapi_schema_shape(field, document, seen)
            for field_name, field in sorted(
                properties.items(), key=lambda item: str(item[0])
            )
            if isinstance(field, Mapping)
        }
    items = schema.get("items")
    if isinstance(items, Mapping):
        result["items"] = _openapi_schema_shape(items, document, seen)
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
