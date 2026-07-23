"""Deterministic cross-stack HTTP operation mapping and reconciliation."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import tokenize
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import yaml


HTTP_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")
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
_DYNAMIC_SEGMENT = re.compile(
    r"^(?::(?P<colon>[A-Za-z_$][\w$]*)"
    r"|\{(?P<brace>[A-Za-z_$][\w$]*)\}"
    r"|\[\[?(?:\.\.\.)?(?P<bracket>[A-Za-z_$][\w$]*)\]?\]"
    r"|\$(?P<dollar>[A-Za-z_$][\w$]*)"
    r"|<(?:(?:[^:>]+):)?(?P<angle>[A-Za-z_$][\w$]*)>)$"
)
_TEMPLATE_SEGMENT = re.compile(
    r"\$\{(?P<name>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\}"
)


@dataclass(frozen=True)
class SourceAnchor:
    """One extraction site retained when duplicate routes are merged."""

    file: str
    line: int
    framework: str
    extractor: str
    confidence: float

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SourceAnchor":
        return cls(
            file=str(value.get("file", "")),
            line=int(value.get("line", 0)),
            framework=str(value.get("framework", "unknown")),
            extractor=str(value.get("extractor", "unknown")),
            confidence=float(value.get("confidence", 0.0)),
        )


@dataclass(frozen=True)
class OperationEvidence:
    """A normalized frontend request or backend route."""

    side: str
    method: str | None
    path: str | None
    normalized_path: str | None
    parameters: tuple[str, ...] = ()
    schemas: tuple[str, ...] = ()
    dynamic: bool = False
    classification: str = "application"
    sources: tuple[SourceAnchor, ...] = ()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OperationEvidence":
        return cls(
            side=str(value.get("side", "unknown")),
            method=_normalize_method(value.get("method")),
            path=_string_or_none(value.get("path")),
            normalized_path=_string_or_none(value.get("normalized_path")),
            parameters=tuple(str(item) for item in value.get("parameters", [])),
            schemas=tuple(str(item) for item in value.get("schemas", [])),
            dynamic=bool(value.get("dynamic", False)),
            classification=str(value.get("classification", "application")),
            sources=tuple(
                SourceAnchor.from_dict(item) for item in value.get("sources", [])
            ),
        )

    @property
    def ref(self) -> str:
        method = self.method or "?"
        path = self.normalized_path or self.path or "?"
        return f"{self.side}:{method}:{path}"


@dataclass(frozen=True)
class ParityFinding:
    """One deterministic reconciliation result."""

    kind: str
    normalized_path: str | None
    frontend: tuple[str, ...] = ()
    backend: tuple[str, ...] = ()
    detail: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ParityFinding":
        return cls(
            kind=str(value.get("kind", "unresolved")),
            normalized_path=_string_or_none(value.get("normalized_path")),
            frontend=tuple(str(item) for item in value.get("frontend", [])),
            backend=tuple(str(item) for item in value.get("backend", [])),
            detail=str(value.get("detail", "")),
        )


@dataclass(frozen=True)
class ProjectMap:
    """Cross-stack evidence stored additively inside a frontend-map artifact."""

    schema_version: int = 1
    frontend_operations: tuple[OperationEvidence, ...] = ()
    backend_operations: tuple[OperationEvidence, ...] = ()
    findings: tuple[ParityFinding, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Normalize tuples to JSON arrays before this is nested in FrontendMap.
        return json.loads(json.dumps(asdict(self), sort_keys=True))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ProjectMap":
        if not value:
            return cls()
        version = int(value.get("schema_version", 1))
        if version != 1:
            raise ValueError(f"Unsupported project map schema {version}; expected 1.")
        return cls(
            schema_version=version,
            frontend_operations=tuple(
                OperationEvidence.from_dict(item)
                for item in value.get("frontend_operations", [])
            ),
            backend_operations=tuple(
                OperationEvidence.from_dict(item)
                for item in value.get("backend_operations", [])
            ),
            findings=tuple(
                ParityFinding.from_dict(item) for item in value.get("findings", [])
            ),
            evidence=dict(value.get("evidence", {})),
        )

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            "frontend_only": 0,
            "backend_only": 0,
            "method_mismatch": 0,
            "unresolved": 0,
        }
        for finding in self.findings:
            if finding.kind in counts:
                counts[finding.kind] += 1
        return counts


def normalize_route_path(path: str | None) -> tuple[str | None, tuple[str, ...], bool]:
    """Return comparable route shape, parameter identities, and uncertainty."""

    if path is None:
        return None, (), True
    candidate = path.strip()
    if not candidate:
        candidate = "/"
    if "://" in candidate:
        candidate = urlsplit(candidate).path or "/"
    else:
        candidate = candidate.split("?", 1)[0].split("#", 1)[0]
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    candidate = re.sub(r"/+", "/", candidate)

    parameters: list[str] = []
    normalized: list[str] = []
    unresolved = False
    for segment in candidate.split("/"):
        if not segment:
            continue
        match = _DYNAMIC_SEGMENT.match(segment)
        if match:
            name = next(value for value in match.groupdict().values() if value)
            parameters.append(name)
            normalized.append("{}")
            continue
        template_names = _TEMPLATE_SEGMENT.findall(segment)
        if template_names:
            parameters.extend(template_names)
            normalized.append(_TEMPLATE_SEGMENT.sub("{}", segment))
            continue
        if any(token in segment for token in ("${", "`", "*")):
            unresolved = True
        normalized.append(segment)
    normalized_path = "/" + "/".join(normalized)
    return normalized_path or "/", tuple(parameters), unresolved


def build_project_map(
    root: str | Path,
    frontend_nodes: Iterable[Any] = (),
    *,
    suppress_internal: bool = True,
) -> ProjectMap:
    """Extract both sides and reconcile only comparable HTTP evidence."""

    root_path = Path(root).expanduser().resolve()
    frontend = _dedupe_operations(_frontend_operations(frontend_nodes))
    backend, extraction = _extract_backend_operations(root_path)
    backend = _dedupe_operations(backend)
    findings, suppressed = reconcile_operations(
        frontend,
        backend,
        suppress_internal=suppress_internal,
    )
    evidence = {
        "mode": "static",
        "adapters": sorted(extraction["adapters"]),
        "backend_files_scanned": extraction["files_scanned"],
        "unknown_backend_evidence": extraction["unknown"],
        "suppressed_internal": suppressed,
        "source_manifest": extraction["source_manifest"],
    }
    return ProjectMap(
        frontend_operations=frontend,
        backend_operations=backend,
        findings=findings,
        evidence=evidence,
    )


def project_source_manifest(root: str | Path) -> dict[str, str]:
    """Hash every source that can contribute backend/API evidence."""

    root_path = Path(root).expanduser().resolve()
    _, extraction = _extract_backend_operations(root_path)
    return dict(extraction["source_manifest"])


def reconcile_operations(
    frontend: Iterable[OperationEvidence],
    backend: Iterable[OperationEvidence],
    *,
    suppress_internal: bool = True,
) -> tuple[tuple[ParityFinding, ...], list[str]]:
    """Compare operations without promoting unresolved evidence to matches."""

    front = tuple(frontend)
    back = tuple(backend)
    findings: list[ParityFinding] = []
    suppressed: list[str] = []

    unresolved_front = [
        item
        for item in front
        if item.dynamic or item.normalized_path is None or item.method is None
    ]
    unresolved_back = [
        item
        for item in back
        if item.dynamic or item.normalized_path is None or item.method is None
    ]
    for item in [*unresolved_front, *unresolved_back]:
        findings.append(
            ParityFinding(
                kind="unresolved",
                normalized_path=item.normalized_path,
                frontend=(item.ref,) if item.side == "frontend" else (),
                backend=(item.ref,) if item.side == "backend" else (),
                detail="Dynamic or incomplete operation evidence cannot be compared safely.",
            )
        )

    comparable_front = [item for item in front if item not in unresolved_front]
    comparable_back = [item for item in back if item not in unresolved_back]
    front_by_path = _group_by_path(comparable_front)
    back_by_path = _group_by_path(comparable_back)

    for path in sorted(set(front_by_path) | set(back_by_path)):
        front_items = front_by_path.get(path, ())
        back_items = back_by_path.get(path, ())
        if front_items and back_items:
            front_methods = {item.method for item in front_items}
            back_methods = {item.method for item in back_items}
            unmatched_front = tuple(
                item for item in front_items if item.method not in back_methods
            )
            unmatched_back = tuple(
                item for item in back_items if item.method not in front_methods
            )
            if unmatched_front or unmatched_back:
                findings.append(
                    ParityFinding(
                        kind="method_mismatch",
                        normalized_path=path,
                        frontend=tuple(item.ref for item in unmatched_front),
                        backend=tuple(item.ref for item in unmatched_back),
                        detail=(
                            "Same path has unmatched methods: "
                            f"frontend={sorted(item.method for item in unmatched_front)}, "
                            f"backend={sorted(item.method for item in unmatched_back)}."
                        ),
                    )
                )
            continue
        if front_items:
            for item in front_items:
                findings.append(
                    ParityFinding(
                        kind="frontend_only",
                        normalized_path=path,
                        frontend=(item.ref,),
                        detail="No comparable backend operation was found.",
                    )
                )
            continue
        for item in back_items:
            if suppress_internal and item.classification == "internal":
                suppressed.append(item.ref)
                continue
            findings.append(
                ParityFinding(
                    kind="backend_only",
                    normalized_path=path,
                    backend=(item.ref,),
                    detail="No comparable frontend operation was found.",
                )
            )

    findings.sort(
        key=lambda item: (
            item.kind,
            item.normalized_path or "",
            item.frontend,
            item.backend,
        )
    )
    return tuple(findings), sorted(suppressed)


def _frontend_operations(nodes: Iterable[Any]) -> list[OperationEvidence]:
    operations: list[OperationEvidence] = []
    for node in nodes:
        kind = _node_value(node, "kind", "")
        if kind != "data":
            continue
        metadata = dict(_node_value(node, "metadata", {}) or {})
        if metadata.get("transport") != "http":
            continue
        path = _string_or_none(_node_value(node, "name", None))
        normalized, parameters, unresolved = normalize_route_path(path)
        method = _normalize_method(metadata.get("method"))
        dynamic = bool(metadata.get("dynamic", False)) or unresolved or path is None
        operations.append(
            OperationEvidence(
                side="frontend",
                method=method,
                path=path,
                normalized_path=normalized,
                parameters=parameters,
                dynamic=dynamic,
                sources=(
                    SourceAnchor(
                        file=str(_node_value(node, "file", "")),
                        line=int(_node_value(node, "line", 0)),
                        framework=str(metadata.get("framework", "frontend")),
                        extractor=str(metadata.get("extractor", "frontend-map")),
                        confidence=float(metadata.get("confidence", 0.5)),
                    ),
                ),
            )
        )
    return operations


def _extract_backend_operations(
    root: Path,
) -> tuple[list[OperationEvidence], dict[str, Any]]:
    operations: list[OperationEvidence] = []
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
            lower_name.startswith("openapi") or lower_name.startswith("swagger")
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
        extracted: list[OperationEvidence] = []
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


def _extract_openapi(path: Path, relative: str) -> list[OperationEvidence]:
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
    operations: list[OperationEvidence] = []
    for route, path_item in sorted(
        document["paths"].items(), key=lambda item: str(item[0])
    ):
        if not isinstance(path_item, Mapping):
            continue
        inherited_schemas = _schema_references(path_item.get("parameters", []))
        for method, operation in sorted(
            path_item.items(), key=lambda item: str(item[0])
        ):
            normalized_method = _normalize_method(method)
            if normalized_method is None or not isinstance(operation, Mapping):
                continue
            normalized, parameters, unresolved = normalize_route_path(str(route))
            schemas = sorted(inherited_schemas | _schema_references(operation))
            operations.append(
                OperationEvidence(
                    side="backend",
                    method=normalized_method,
                    path=str(route),
                    normalized_path=normalized,
                    parameters=parameters,
                    schemas=tuple(schemas),
                    dynamic=unresolved,
                    classification=_classify_path(normalized),
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
) -> tuple[list[OperationEvidence], set[str]]:
    operations: list[OperationEvidence] = []
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
    return operations, adapters


def _extract_javascript_routes(
    relative: str,
    content: str,
) -> tuple[list[OperationEvidence], set[str]]:
    operations: list[OperationEvidence] = []
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
    return operations, adapters


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
) -> OperationEvidence:
    normalized, parameters, unresolved = normalize_route_path(path)
    return OperationEvidence(
        side=side,
        method=_normalize_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=unresolved,
        classification=_classify_path(normalized),
        sources=(SourceAnchor(file, line, framework, extractor, confidence),),
    )


def _unknown_backend(file: str, framework: str, extractor: str) -> OperationEvidence:
    return OperationEvidence(
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
) -> OperationEvidence:
    normalized, parameters, _unresolved = normalize_route_path(path)
    return OperationEvidence(
        side="backend",
        method=_normalize_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=True,
        classification="unknown",
        sources=(SourceAnchor(file, line, "unknown", extractor, 0.2),),
    )


def _dedupe_operations(
    operations: Iterable[OperationEvidence],
) -> tuple[OperationEvidence, ...]:
    grouped: dict[
        tuple[str, str | None, str | None, bool, str],
        list[OperationEvidence],
    ] = {}
    for operation in operations:
        key = (
            operation.side,
            operation.method,
            operation.normalized_path,
            operation.dynamic,
            operation.classification,
        )
        grouped.setdefault(key, []).append(operation)
    result: list[OperationEvidence] = []
    for key in sorted(
        grouped,
        key=lambda item: (
            item[0],
            item[2] or "",
            item[1] or "",
            item[3],
            item[4],
        ),
    ):
        members = grouped[key]
        sources = sorted(
            {source for item in members for source in item.sources},
            key=lambda item: (
                item.file,
                item.line,
                item.framework,
                item.extractor,
                item.confidence,
            ),
        )
        result.append(
            OperationEvidence(
                side=members[0].side,
                method=members[0].method,
                path=next(
                    (item.path for item in members if item.path is not None), None
                ),
                normalized_path=members[0].normalized_path,
                parameters=tuple(
                    sorted({value for item in members for value in item.parameters})
                ),
                schemas=tuple(
                    sorted({value for item in members for value in item.schemas})
                ),
                dynamic=members[0].dynamic,
                classification=members[0].classification,
                sources=tuple(sources),
            )
        )
    return tuple(result)


def _group_by_path(
    operations: Iterable[OperationEvidence],
) -> dict[str, tuple[OperationEvidence, ...]]:
    grouped: dict[str, list[OperationEvidence]] = {}
    for operation in operations:
        if operation.normalized_path is not None:
            grouped.setdefault(operation.normalized_path, []).append(operation)
    return {
        path: tuple(sorted(items, key=lambda item: (item.method or "", item.ref)))
        for path, items in grouped.items()
    }


def _schema_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str):
                references.add(item.rsplit("/", 1)[-1])
            else:
                references.update(_schema_references(item))
    elif isinstance(value, list):
        for item in value:
            references.update(_schema_references(item))
    return references


def _methods_from_text(value: str) -> tuple[str, ...]:
    methods = {
        method
        for token in re.findall(r"[\"']([A-Za-z]+)[\"']", value)
        if (method := _normalize_method(token)) is not None
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
    assignment = re.compile(
        r"\b(?P<receiver>[A-Za-z_$][\w$]*)\s*=\s*"
        r"(?P<factory>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?)"
        r"\s*\((?P<args>.*?)\)",
        re.DOTALL,
    )
    for match in assignment.finditer(content):
        if not code_positions[match.start()]:
            continue
        factory = factories.get(match.group("factory"))
        if factory is None or factory[1] not in {"APIRouter", "Blueprint"}:
            continue
        prefix_match = re.search(
            r"\b(?:prefix|url_prefix)\s*=\s*[\"'](?P<prefix>.*?)[\"']",
            match.group("args"),
            re.DOTALL,
        )
        if prefix_match:
            prefixes[match.group("receiver")] = prefix_match.group("prefix")

    mount = re.compile(
        r"\b[A-Za-z_$][\w$]*\.(?:include_router|register_blueprint)"
        r"\(\s*(?P<receiver>[A-Za-z_$][\w$]*)(?P<args>.*?)\)",
        re.DOTALL,
    )
    for match in mount.finditer(content):
        if not code_positions[match.start()]:
            continue
        prefix_match = re.search(
            r"\b(?:prefix|url_prefix)\s*=\s*[\"'](?P<prefix>.*?)[\"']",
            match.group("args"),
            re.DOTALL,
        )
        if prefix_match:
            receiver = match.group("receiver")
            prefixes[receiver] = _join_routes(
                prefix_match.group("prefix"),
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


def _normalize_method(value: Any) -> str | None:
    if value is None:
        return None
    method = str(value).upper()
    return method if method in HTTP_METHODS else None


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
        if character == "/" and following == "/":
            end = content.find("\n", index + 2)
            end = len(content) if end == -1 else end
            positions[index:end] = [False] * (end - index)
            index = end
            continue
        if character == "/" and following == "*":
            close = content.find("*/", index + 2)
            end = len(content) if close == -1 else close + 2
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


def _node_value(node: Any, key: str, default: Any) -> Any:
    if isinstance(node, Mapping):
        return node.get(key, default)
    return getattr(node, key, default)


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
