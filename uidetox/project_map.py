"""Versioned, conservative full-stack contract lineage."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import tokenize
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import yaml

from uidetox.findings import Finding

HTTP_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")
CONTRACT_GRAPH_SCHEMA_VERSION = 2
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
class ContractNode:
    """One typed contract concept with explicit evidence state."""

    id: str
    kind: str
    name: str
    side: str
    capability_status: str
    source: SourceAnchor
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "side": self.side,
            "capability_status": self.capability_status,
            "source": asdict(self.source),
            "attributes": _json_mapping(self.attributes),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContractNode":
        return cls(
            id=str(value.get("id", "")),
            kind=str(value.get("kind", "unknown")),
            name=str(value.get("name", "")),
            side=str(value.get("side", "unknown")),
            capability_status=str(value.get("capability_status", "unknown")),
            source=SourceAnchor.from_dict(dict(value.get("source", {}))),
            attributes=dict(value.get("attributes", {})),
        )


@dataclass(frozen=True)
class ContractEdge:
    """One source-anchored lineage relationship."""

    source: str
    target: str
    kind: str
    provenance: str
    confidence: float
    anchor: SourceAnchor
    capability_status: str = "present"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "anchor": asdict(self.anchor),
            "capability_status": self.capability_status,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContractEdge":
        return cls(
            source=str(value.get("source", "")),
            target=str(value.get("target", "")),
            kind=str(value.get("kind", "unknown")),
            provenance=str(value.get("provenance", "unknown")),
            confidence=float(value.get("confidence", 0.0)),
            anchor=SourceAnchor.from_dict(dict(value.get("anchor", {}))),
            capability_status=str(value.get("capability_status", "unknown")),
        )


@dataclass(frozen=True)
class _AdapterOperation:
    """Internal adapter fact converted into contract graph nodes."""

    side: str
    method: str | None
    path: str | None
    normalized_path: str | None
    parameters: tuple[str, ...] = ()
    dynamic: bool = False
    classification: str = "application"
    sources: tuple[SourceAnchor, ...] = ()
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    error_schemas: tuple[tuple[str, dict[str, Any]], ...] = ()
    status_codes: tuple[str, ...] = ()
    auth: str = "unknown"
    authorization: str = "unknown"
    tenant: str = "unknown"
    handler: str | None = None
    lineage: tuple[dict[str, Any], ...] = ()
    ui_states: tuple[str, ...] = ()
    mutation: bool = False
    cache_invalidation: str = "unknown"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "_AdapterOperation":
        return cls(
            side=str(value.get("side", "unknown")),
            method=_normalize_method(value.get("method")),
            path=_string_or_none(value.get("path")),
            normalized_path=_string_or_none(value.get("normalized_path")),
            parameters=tuple(str(item) for item in value.get("parameters", [])),
            dynamic=bool(value.get("dynamic", False)),
            classification=str(value.get("classification", "application")),
            sources=tuple(
                SourceAnchor.from_dict(item) for item in value.get("sources", [])
            ),
            request_schema=_mapping_or_none(value.get("request_schema")),
            response_schema=_mapping_or_none(value.get("response_schema")),
            error_schemas=tuple(
                (str(status), dict(schema))
                for status, schema in value.get("error_schemas", [])
            ),
            status_codes=tuple(str(item) for item in value.get("status_codes", [])),
            auth=str(value.get("auth", "unknown")),
            authorization=str(value.get("authorization", "unknown")),
            tenant=str(value.get("tenant", "unknown")),
            handler=_string_or_none(value.get("handler")),
            lineage=tuple(dict(item) for item in value.get("lineage", [])),
            ui_states=tuple(str(item) for item in value.get("ui_states", [])),
            mutation=bool(value.get("mutation", False)),
            cache_invalidation=str(value.get("cache_invalidation", "unknown")),
        )

    @property
    def ref(self) -> str:
        method = self.method or "?"
        path = self.normalized_path or self.path or "?"
        return f"{self.side}:{method}:{path}"


@dataclass(frozen=True)
class ProjectMap:
    """Single application contract graph stored inside a frontend-map artifact."""

    schema_version: int = CONTRACT_GRAPH_SCHEMA_VERSION
    nodes: tuple[ContractNode, ...] = ()
    edges: tuple[ContractEdge, ...] = ()
    findings: tuple[Finding, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "findings": [item.to_dict() for item in self.findings],
            "evidence": _json_mapping(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "ProjectMap":
        if not value:
            return cls()
        version = int(value.get("schema_version", 1))
        if version == 1:
            return _migrate_legacy_project_map(value)
        if version != CONTRACT_GRAPH_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported project map schema {version}; "
                f"expected {CONTRACT_GRAPH_SCHEMA_VERSION}."
            )
        return cls(
            schema_version=version,
            nodes=tuple(ContractNode.from_dict(item) for item in value.get("nodes", [])),
            edges=tuple(ContractEdge.from_dict(item) for item in value.get("edges", [])),
            findings=tuple(
                Finding.from_dict(item) for item in value.get("findings", [])
            ),
            evidence=dict(value.get("evidence", {})),
        )

    @property
    def counts(self) -> dict[str, int]:
        counts = {"contract_mismatch": 0, "coverage_gap": 0}
        for finding in self.findings:
            if finding.status == "investigate":
                counts["coverage_gap"] += 1
            else:
                counts["contract_mismatch"] += 1
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
    """Build one graph spanning frontend calls and backend contract evidence."""

    root_path = Path(root).expanduser().resolve()
    frontend = _dedupe_adapter_facts(_frontend_adapter_facts(frontend_nodes))
    backend, extraction = _extract_backend_adapter_facts(root_path)
    backend = _dedupe_adapter_facts(backend)
    nodes, edges, suppressed = _build_contract_graph(
        frontend, backend, suppress_internal=suppress_internal
    )
    findings = reconcile_contract_graph(nodes, edges)
    evidence = {
        "mode": "static",
        "adapters": sorted(extraction["adapters"]),
        "backend_files_scanned": extraction["files_scanned"],
        "unknown_backend_evidence": extraction["unknown"],
        "suppressed_internal": suppressed,
        "source_manifest": extraction["source_manifest"],
    }
    return ProjectMap(
        nodes=nodes,
        edges=edges,
        findings=findings,
        evidence=evidence,
    )


def project_source_manifest(root: str | Path) -> dict[str, str]:
    """Hash every source that can contribute backend/API evidence."""

    root_path = Path(root).expanduser().resolve()
    _, extraction = _extract_backend_adapter_facts(root_path)
    return dict(extraction["source_manifest"])


def reconcile_contract_graph(
    nodes: Iterable[ContractNode],
    edges: Iterable[ContractEdge],
    *,
    suppress_internal: bool = True,
) -> tuple[Finding, ...]:
    """Compare source-backed operation slices without treating unknown as parity."""

    node_index = {node.id: node for node in nodes}
    outgoing: dict[tuple[str, str], list[ContractNode]] = {}
    for edge in edges:
        target = node_index.get(edge.target)
        if target is not None:
            outgoing.setdefault((edge.source, edge.kind), []).append(target)
    operations = tuple(
        node
        for node in node_index.values()
        if node.kind in {"client_operation", "route"}
    )
    frontend = tuple(node for node in operations if node.side == "frontend")
    backend = tuple(node for node in operations if node.side == "backend")
    findings: list[Finding] = []

    unresolved: set[str] = set()
    for node in (*frontend, *backend):
        attributes = node.attributes
        if (
            bool(attributes.get("dynamic"))
            or not attributes.get("normalized_path")
            or not attributes.get("method")
        ):
            unresolved.add(node.id)
            findings.append(
                _graph_finding(
                    "evidence_unknown",
                    node,
                    None,
                    "Static evidence is incomplete; contract parity cannot be asserted.",
                    status="investigate",
                )
            )

    comparable_front = tuple(
        node
        for node in frontend
        if node.id not in unresolved
        and node.attributes.get("normalized_path")
        and node.attributes.get("method")
    )
    comparable_back = tuple(
        node
        for node in backend
        if node.id not in unresolved
        and node.attributes.get("normalized_path")
        and node.attributes.get("method")
    )
    front_by_path = _graph_operations_by_path(comparable_front)
    back_by_path = _graph_operations_by_path(comparable_back)

    for path in sorted(set(front_by_path) | set(back_by_path)):
        front_items = front_by_path.get(path, ())
        back_items = back_by_path.get(path, ())
        if not front_items:
            for backend_node in back_items:
                if (
                    suppress_internal
                    and backend_node.attributes.get("classification") == "internal"
                ):
                    continue
                findings.append(
                    _graph_finding(
                        "backend_only",
                        None,
                        backend_node,
                        "No comparable frontend operation was found.",
                        status="investigate",
                    )
                )
            continue
        if not back_items:
            findings.extend(
                _graph_finding(
                    "frontend_only",
                    frontend_node,
                    None,
                    "No comparable backend operation was found.",
                )
                for frontend_node in front_items
            )
            continue

        front_by_method = {
            str(node.attributes["method"]): node for node in front_items
        }
        back_by_method = {
            str(node.attributes["method"]): node for node in back_items
        }
        unmatched_front = sorted(set(front_by_method) - set(back_by_method))
        unmatched_back = sorted(set(back_by_method) - set(front_by_method))
        if unmatched_front or unmatched_back:
            findings.append(
                _graph_finding(
                    "method_mismatch",
                    front_by_method[unmatched_front[0]]
                    if unmatched_front
                    else front_items[0],
                    back_by_method[unmatched_back[0]]
                    if unmatched_back
                    else back_items[0],
                    "Same path has unmatched methods: "
                    f"frontend={unmatched_front}, backend={unmatched_back}.",
                )
            )
        for method in sorted(set(front_by_method) & set(back_by_method)):
            frontend_node = front_by_method[method]
            backend_node = back_by_method[method]
            difference = _first_contract_difference(
                frontend_node, backend_node, outgoing
            )
            if difference is not None:
                kind, field_name, detail, expected, actual, investigate = difference
                findings.append(
                    _graph_finding(
                        kind,
                        frontend_node,
                        backend_node,
                        detail,
                        field=field_name,
                        expected=expected,
                        actual=actual,
                        status="investigate" if investigate else "pending",
                    )
                )

    deduped = {finding.fingerprint: finding for finding in findings}
    return tuple(
        sorted(
            deduped.values(),
            key=lambda finding: (
                finding.normalized_path,
                finding.detector_id,
                finding.fingerprint,
            ),
        )
    )


def _build_contract_graph(
    frontend: Iterable[_AdapterOperation],
    backend: Iterable[_AdapterOperation],
    *,
    suppress_internal: bool,
) -> tuple[tuple[ContractNode, ...], tuple[ContractEdge, ...], list[str]]:
    nodes: list[ContractNode] = []
    edges: list[ContractEdge] = []
    suppressed: list[str] = []
    for operation in (*tuple(frontend), *tuple(backend)):
        if (
            suppress_internal
            and operation.side == "backend"
            and operation.classification == "internal"
        ):
            suppressed.append(operation.ref)
        operation_node = _operation_contract_node(operation)
        nodes.append(operation_node)
        _append_operation_contract(nodes, edges, operation_node, operation)
    unique_nodes = {node.id: node for node in nodes}
    unique_edges = {
        (edge.source, edge.target, edge.kind, edge.provenance): edge for edge in edges
    }
    return (
        tuple(
            sorted(
                unique_nodes.values(),
                key=lambda node: (node.side, node.kind, node.name, node.id),
            )
        ),
        tuple(
            sorted(
                unique_edges.values(),
                key=lambda edge: (edge.source, edge.kind, edge.target),
            )
        ),
        sorted(suppressed),
    )


def _operation_contract_node(operation: _AdapterOperation) -> ContractNode:
    anchor = operation.sources[0] if operation.sources else _unknown_anchor()
    kind = "client_operation" if operation.side == "frontend" else "route"
    capability_status = (
        "unknown"
        if operation.dynamic
        or operation.method is None
        or operation.normalized_path is None
        or not any(
            (
                operation.request_schema,
                operation.response_schema,
                operation.error_schemas,
                operation.status_codes,
                operation.auth != "unknown",
                operation.handler,
                operation.lineage,
                operation.ui_states,
            )
        )
        else "present"
    )
    identifier = _contract_id(
        kind,
        operation.side,
        operation.method or "?",
        operation.normalized_path or operation.path or "?",
        anchor.file,
        anchor.line,
    )
    return ContractNode(
        id=identifier,
        kind=kind,
        name=f"{operation.method or '?'} {operation.normalized_path or operation.path or '?'}",
        side=operation.side,
        capability_status=capability_status,
        source=anchor,
        attributes={
            "method": operation.method,
            "path": operation.path,
            "normalized_path": operation.normalized_path,
            "parameters": list(operation.parameters),
            "classification": operation.classification,
            "dynamic": operation.dynamic,
            "status_codes": list(operation.status_codes),
            "handler": operation.handler,
            "mutation": operation.mutation,
            "cache_invalidation": operation.cache_invalidation,
            "sources": [asdict(source) for source in operation.sources],
        },
    )


def _append_operation_contract(
    nodes: list[ContractNode],
    edges: list[ContractEdge],
    operation_node: ContractNode,
    operation: _AdapterOperation,
) -> None:
    for kind, schema in (
        ("request_schema", operation.request_schema),
        ("response_schema", operation.response_schema),
    ):
        if schema:
            _append_schema_contract(
                nodes,
                edges,
                operation_node,
                kind,
                schema,
                name=str(schema.get("name", kind)),
            )
    for status, schema in operation.error_schemas:
        _append_schema_contract(
            nodes,
            edges,
            operation_node,
            "error_schema",
            schema,
            name=str(schema.get("name", f"error:{status}")),
            status=status,
        )
    auth_name = str(
        next(
            (
                item.get("name")
                for item in operation.lineage
                if item.get("kind") == "auth_requirement"
            ),
            "authentication",
        )
    )
    auth_node = ContractNode(
        _contract_id("auth_requirement", operation_node.id, auth_name),
        "auth_requirement",
        auth_name,
        operation.side,
        operation.auth,
        operation_node.source,
        {
            "authorization": operation.authorization,
            "tenant": operation.tenant,
        },
    )
    nodes.append(auth_node)
    edges.append(
        _contract_edge(
            operation_node,
            auth_node,
            "requires",
            "static:auth",
        )
    )
    previous = operation_node
    for item in operation.lineage:
        kind = str(item.get("kind", "unknown"))
        if kind == "auth_requirement":
            continue
        name = str(item.get("name", kind))
        anchor = SourceAnchor.from_dict(
            dict(item.get("source", asdict(operation_node.source)))
        )
        lineage_node = ContractNode(
            _contract_id(kind, operation_node.id, name),
            kind,
            name,
            operation.side,
            str(item.get("capability_status", "present")),
            anchor,
            {
                key: _json_value(value)
                for key, value in item.items()
                if key not in {"kind", "name", "source", "fields"}
            },
        )
        nodes.append(lineage_node)
        if kind == "ui_action":
            edges.append(
                _contract_edge(
                    lineage_node,
                    operation_node,
                    "triggers",
                    str(item.get("provenance", "frontend-map:action")),
                )
            )
            continue
        edges.append(
            _contract_edge(
                previous,
                lineage_node,
                str(item.get("edge", _lineage_edge(kind))),
                str(item.get("provenance", "static:lineage")),
            )
        )
        previous = lineage_node
        for field_name, field_schema in dict(item.get("fields", {})).items():
            field_node = ContractNode(
                _contract_id("database_field", lineage_node.id, str(field_name)),
                "database_field",
                str(field_name),
                operation.side,
                "present",
                anchor,
                dict(field_schema),
            )
            nodes.append(field_node)
            edges.append(
                _contract_edge(
                    lineage_node,
                    field_node,
                    "stores",
                    str(item.get("provenance", "static:lineage")),
                )
            )
    for state in operation.ui_states:
        state_node = ContractNode(
            _contract_id("ui_state", operation_node.id, state),
            "ui_state",
            state,
            "frontend",
            "present",
            operation_node.source,
            {},
        )
        nodes.append(state_node)
        edges.append(
            _contract_edge(operation_node, state_node, "renders_state", "frontend-map")
        )


def _append_schema_contract(
    nodes: list[ContractNode],
    edges: list[ContractEdge],
    operation_node: ContractNode,
    kind: str,
    schema: Mapping[str, Any],
    *,
    name: str,
    status: str | None = None,
) -> None:
    schema_node = ContractNode(
        _contract_id(kind, operation_node.id, name, status or ""),
        kind,
        name,
        operation_node.side,
        "present",
        operation_node.source,
        {
            key: _json_value(value)
            for key, value in schema.items()
            if key not in {"properties", "items"}
        }
        | ({"status": status} if status is not None else {}),
    )
    nodes.append(schema_node)
    edges.append(
        _contract_edge(
            operation_node,
            schema_node,
            {
                "request_schema": "accepts",
                "response_schema": "returns",
                "error_schema": "returns_error",
            }[kind],
            "static:schema",
        )
    )
    _append_schema_fields(nodes, edges, schema_node, schema)


def _append_schema_fields(
    nodes: list[ContractNode],
    edges: list[ContractEdge],
    parent: ContractNode,
    schema: Mapping[str, Any],
) -> None:
    required = {str(item) for item in schema.get("required", [])}
    for field_name, raw_field in sorted(dict(schema.get("properties", {})).items()):
        field_schema = dict(raw_field) if isinstance(raw_field, Mapping) else {}
        field_node = ContractNode(
            _contract_id("schema_field", parent.id, str(field_name)),
            "schema_field",
            str(field_name),
            parent.side,
            "present",
            parent.source,
            {
                key: _json_value(value)
                for key, value in field_schema.items()
                if key != "properties"
            }
            | {"required": str(field_name) in required},
        )
        nodes.append(field_node)
        edges.append(_contract_edge(parent, field_node, "has_field", "static:schema"))
        _append_schema_fields(nodes, edges, field_node, field_schema)


def _contract_edge(
    source: ContractNode,
    target: ContractNode,
    kind: str,
    provenance: str,
) -> ContractEdge:
    return ContractEdge(
        source.id,
        target.id,
        kind,
        provenance,
        min(source.source.confidence, target.source.confidence),
        target.source,
        target.capability_status,
    )


def _first_contract_difference(
    frontend: ContractNode,
    backend: ContractNode,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> tuple[str, str, str, Any, Any, bool] | None:
    front = frontend.attributes
    back = backend.attributes
    if "unknown" in {
        frontend.capability_status,
        backend.capability_status,
    }:
        return (
            "evidence_unknown",
            "",
            "Static evidence is incomplete; contract parity cannot be asserted.",
            backend.capability_status,
            frontend.capability_status,
            True,
        )
    for label in ("request", "response"):
        relation = "accepts" if label == "request" else "returns"
        front_schema = _schema_from_graph(frontend.id, relation, outgoing)
        back_schema = _schema_from_graph(backend.id, relation, outgoing)
        if front_schema and back_schema:
            difference = _schema_difference(front_schema, back_schema)
            if difference is not None:
                suffix, field_name, detail, expected, actual = difference
                return (
                    f"{label}_{suffix}",
                    field_name,
                    f"{label.title()} contract {detail}.",
                    expected,
                    actual,
                    False,
                )
        elif bool(front_schema) != bool(back_schema):
            return (
                f"{label}_evidence_unknown",
                "",
                f"{label.title()} schema exists on only one side; parity is unknown.",
                back_schema,
                front_schema,
                True,
            )

    front_auth = _auth_from_graph(frontend.id, outgoing)
    back_auth = _auth_from_graph(backend.id, outgoing)
    for attribute in ("auth", "authorization", "tenant"):
        frontend_value = front_auth[attribute]
        backend_value = back_auth[attribute]
        if "unknown" in {frontend_value, backend_value}:
            if frontend_value != backend_value:
                return (
                    f"{attribute}_evidence_unknown",
                    "",
                    f"{attribute.title()} evidence is incomplete.",
                    backend_value,
                    frontend_value,
                    True,
                )
        elif frontend_value != backend_value:
            return (
                f"{attribute}_mismatch",
                "",
                f"{attribute.title()} requirements contradict.",
                backend_value,
                frontend_value,
                False,
            )

    front_statuses = {str(item) for item in front.get("status_codes", [])}
    back_statuses = {str(item) for item in back.get("status_codes", [])}
    if front_statuses and back_statuses and front_statuses != back_statuses:
        return (
            "status_mismatch",
            "",
            "Success/error status sets differ.",
            sorted(back_statuses),
            sorted(front_statuses),
            False,
        )
    front_states = {
        node.name for node in outgoing.get((frontend.id, "renders_state"), [])
    }
    back_errors = outgoing.get((backend.id, "returns_error"), [])
    if back_errors and "error" not in front_states:
        return (
            "error_state_missing",
            "",
            "Backend error contract has no user-visible frontend error state.",
            sorted(str(node.attributes.get("status", "")) for node in back_errors),
            sorted(front_states),
            False,
        )
    if front.get("mutation") and front.get("cache_invalidation") == "absent":
        return (
            "cache_invalidation_missing",
            "",
            "Mutation has no static cache invalidation evidence.",
            "present",
            "absent",
            False,
        )
    return None


def _schema_difference(
    frontend: Mapping[str, Any],
    backend: Mapping[str, Any],
    prefix: str = "",
) -> tuple[str, str, str, Any, Any] | None:
    front_type = _schema_type(frontend)
    back_type = _schema_type(backend)
    if front_type and back_type and front_type != back_type:
        return (
            "field_type_mismatch",
            prefix,
            f"field {prefix or '<root>'} type differs",
            back_type,
            front_type,
        )
    front_nullable = bool(frontend.get("nullable", False))
    back_nullable = bool(backend.get("nullable", False))
    if front_nullable != back_nullable:
        return (
            "field_nullability_mismatch",
            prefix,
            f"field {prefix or '<root>'} nullability differs",
            back_nullable,
            front_nullable,
        )
    front_enum = tuple(frontend.get("enum", ()))
    back_enum = tuple(backend.get("enum", ()))
    if front_enum and back_enum and set(front_enum) != set(back_enum):
        return (
            "field_enum_mismatch",
            prefix,
            f"field {prefix or '<root>'} enum differs",
            sorted(back_enum, key=str),
            sorted(front_enum, key=str),
        )
    for constraint in (
        "format",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
    ):
        if (
            constraint in frontend
            and constraint in backend
            and frontend[constraint] != backend[constraint]
        ):
            return (
                "field_validation_mismatch",
                prefix,
                f"field {prefix or '<root>'} {constraint} differs",
                backend[constraint],
                frontend[constraint],
            )
    front_required = {str(item) for item in frontend.get("required", [])}
    back_required = {str(item) for item in backend.get("required", [])}
    if front_required != back_required:
        field_name = sorted(front_required ^ back_required)[0]
        return (
            "field_required_mismatch",
            _field_path(prefix, field_name),
            f"field {_field_path(prefix, field_name)} requiredness differs",
            field_name in back_required,
            field_name in front_required,
        )
    front_properties = dict(frontend.get("properties", {}))
    back_properties = dict(backend.get("properties", {}))
    if set(front_properties) != set(back_properties):
        field_name = sorted(set(front_properties) ^ set(back_properties))[0]
        return (
            "field_missing",
            _field_path(prefix, field_name),
            f"field {_field_path(prefix, field_name)} exists on only one side",
            field_name in back_properties,
            field_name in front_properties,
        )
    for field_name in sorted(front_properties):
        front_field = front_properties[field_name]
        back_field = back_properties[field_name]
        if isinstance(front_field, Mapping) and isinstance(back_field, Mapping):
            difference = _schema_difference(
                front_field,
                back_field,
                _field_path(prefix, field_name),
            )
            if difference is not None:
                return difference
    front_items = frontend.get("items")
    back_items = backend.get("items")
    if isinstance(front_items, Mapping) and isinstance(back_items, Mapping):
        return _schema_difference(front_items, back_items, f"{prefix}[]" or "[]")
    return None


def _schema_from_graph(
    operation_id: str,
    relation: str,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> dict[str, Any] | None:
    schemas = outgoing.get((operation_id, relation), [])
    if not schemas:
        return None
    return _schema_from_node(schemas[0], outgoing)


def _schema_from_node(
    node: ContractNode,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> dict[str, Any]:
    schema = {
        key: _json_value(value)
        for key, value in node.attributes.items()
        if key not in {"required", "status"}
    }
    fields = outgoing.get((node.id, "has_field"), [])
    if fields:
        schema["properties"] = {
            field.name: _schema_from_node(field, outgoing) for field in fields
        }
        required = sorted(
            field.name for field in fields if field.attributes.get("required")
        )
        if required:
            schema["required"] = required
    return schema


def _auth_from_graph(
    operation_id: str,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> dict[str, str]:
    nodes = outgoing.get((operation_id, "requires"), [])
    if not nodes:
        return {"auth": "unknown", "authorization": "unknown", "tenant": "unknown"}
    node = nodes[0]
    return {
        "auth": node.capability_status,
        "authorization": str(node.attributes.get("authorization", "unknown")),
        "tenant": str(node.attributes.get("tenant", "unknown")),
    }


def _graph_finding(
    kind: str,
    frontend: ContractNode | None,
    backend: ContractNode | None,
    detail: str,
    *,
    field: str = "",
    expected: Any = None,
    actual: Any = None,
    status: str = "pending",
) -> Finding:
    anchor_node = frontend or backend
    assert anchor_node is not None
    path = str(anchor_node.attributes.get("normalized_path", ""))
    method = str(anchor_node.attributes.get("method", ""))
    detector_kind = kind.replace("_", "-")
    contract_anchor = {
        "kind": kind,
        "normalized_path": path,
        "method": method,
    }
    if field:
        contract_anchor["field"] = field
    return Finding.create(
        detector_id=f"contract-{detector_kind}",
        category="contract",
        severity="info" if status == "investigate" else "warning",
        confidence=(
            min(
                node.source.confidence
                for node in (frontend, backend)
                if node is not None
            )
            if status != "investigate"
            else 0.5
        ),
        message=detail,
        provenance="contract",
        evidence={
            "frontend": [frontend.id] if frontend else [],
            "backend": [backend.id] if backend else [],
            "expected": _finding_evidence_value(expected),
            "actual": _finding_evidence_value(actual),
        },
        source_anchor={
            "path": anchor_node.source.file,
            "line": anchor_node.source.line,
            "column": 0,
        },
        contract_anchor=contract_anchor,
        suppression_key=f"contract:{kind}:{method}:{path}:{field}",
        verifier={
            "kind": "contract",
            "normalized_path": path,
            "method": method,
            "field": field,
        },
        status=status,
    )


def _graph_operations_by_path(
    operations: Iterable[ContractNode],
) -> dict[str, tuple[ContractNode, ...]]:
    grouped: dict[str, list[ContractNode]] = {}
    for operation in operations:
        path = str(operation.attributes.get("normalized_path", ""))
        if path:
            grouped.setdefault(path, []).append(operation)
    return {
        path: tuple(
            sorted(items, key=lambda item: str(item.attributes.get("method", "")))
        )
        for path, items in grouped.items()
    }


def _frontend_adapter_facts(nodes: Iterable[Any]) -> list[_AdapterOperation]:
    operations: list[_AdapterOperation] = []
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
        request_schema = _first_contract_shape(
            metadata.get("request_contracts"),
            metadata.get("request_schema"),
        )
        response_schema = _first_contract_shape(
            metadata.get("response_contracts"),
            metadata.get("response_schema"),
        )
        ui_states = tuple(
            sorted(
                {
                    str(item).lower()
                    for item in metadata.get("ui_states", [])
                    if str(item).lower() in {"loading", "error", "empty", "success"}
                }
            )
        )
        operations.append(
            _AdapterOperation(
                side="frontend",
                method=method,
                path=path,
                normalized_path=normalized,
                parameters=parameters,
                dynamic=dynamic,
                request_schema=request_schema,
                response_schema=response_schema,
                error_schemas=tuple(
                    (str(status), dict(schema))
                    for status, schema in dict(
                        metadata.get("error_schemas", {})
                    ).items()
                    if isinstance(schema, Mapping)
                ),
                status_codes=tuple(
                    sorted(str(item) for item in metadata.get("status_codes", []))
                ),
                auth=str(metadata.get("auth", "unknown")),
                authorization=str(metadata.get("authorization", "unknown")),
                tenant=str(metadata.get("tenant", "unknown")),
                lineage=tuple(
                    [
                        {
                            "kind": "ui_action",
                            "name": str(item),
                            "provenance": "frontend-map:action",
                        }
                        for item in metadata.get("ui_actions", [])
                    ]
                    + [
                        dict(item)
                        for item in metadata.get("lineage", [])
                        if isinstance(item, Mapping)
                    ]
                ),
                ui_states=ui_states,
                mutation=bool(
                    metadata.get(
                        "mutation", method not in {None, "GET", "HEAD", "OPTIONS"}
                    )
                ),
                cache_invalidation=str(
                    metadata.get("cache_invalidation", "unknown")
                ),
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


def _extract_backend_adapter_facts(
    root: Path,
) -> tuple[list[_AdapterOperation], dict[str, Any]]:
    operations: list[_AdapterOperation] = []
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
        extracted: list[_AdapterOperation] = []
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


def _extract_openapi(path: Path, relative: str) -> list[_AdapterOperation]:
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
    operations: list[_AdapterOperation] = []
    for route, path_item in sorted(
        document["paths"].items(), key=lambda item: str(item[0])
    ):
        if not isinstance(path_item, Mapping):
            continue
        for method, operation in sorted(
            path_item.items(), key=lambda item: str(item[0])
        ):
            normalized_method = _normalize_method(method)
            if normalized_method is None or not isinstance(operation, Mapping):
                continue
            normalized, parameters, unresolved = normalize_route_path(str(route))
            request_schema = _openapi_content_schema(
                operation.get("requestBody"), document
            )
            responses = operation.get("responses", {})
            response_map = (
                {str(key): value for key, value in responses.items()}
                if isinstance(responses, Mapping)
                else {}
            )
            success_statuses = sorted(
                str(status)
                for status in response_map
                if str(status).startswith("2")
            )
            error_statuses = sorted(
                str(status)
                for status in response_map
                if str(status).startswith(("4", "5"))
            )
            response_schema = next(
                (
                    schema
                    for status in success_statuses
                    if (
                        schema := _openapi_content_schema(
                            response_map.get(status), document
                        )
                    )
                ),
                None,
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
                auth = "unknown"
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
                _AdapterOperation(
                    side="backend",
                    method=normalized_method,
                    path=str(route),
                    normalized_path=normalized,
                    parameters=parameters,
                    dynamic=unresolved,
                    classification=_classify_path(normalized),
                    request_schema=request_schema,
                    response_schema=response_schema,
                    error_schemas=error_schemas,
                    status_codes=tuple(
                        sorted((*success_statuses, *error_statuses))
                    ),
                    auth=auth,
                    authorization=str(
                        operation.get("x-uidetox-authorization", "unknown")
                    ),
                    tenant=str(operation.get("x-uidetox-tenant", "unknown")),
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
) -> tuple[list[_AdapterOperation], set[str]]:
    operations: list[_AdapterOperation] = []
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
) -> tuple[list[_AdapterOperation], set[str]]:
    operations: list[_AdapterOperation] = []
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
    return [_enrich_javascript_operation(item, content) for item in operations], adapters


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
) -> _AdapterOperation:
    normalized, parameters, unresolved = normalize_route_path(path)
    return _AdapterOperation(
        side=side,
        method=_normalize_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=unresolved,
        classification=_classify_path(normalized),
        sources=(SourceAnchor(file, line, framework, extractor, confidence),),
    )


def _unknown_backend(file: str, framework: str, extractor: str) -> _AdapterOperation:
    return _AdapterOperation(
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
) -> _AdapterOperation:
    normalized, parameters, _unresolved = normalize_route_path(path)
    return _AdapterOperation(
        side="backend",
        method=_normalize_method(method),
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=True,
        classification="unknown",
        sources=(SourceAnchor(file, line, "unknown", extractor, 0.2),),
    )


def _dedupe_adapter_facts(
    operations: Iterable[_AdapterOperation],
) -> tuple[_AdapterOperation, ...]:
    grouped: dict[
        tuple[str, str | None, str | None, bool, str],
        list[_AdapterOperation],
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
    result: list[_AdapterOperation] = []
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
            _AdapterOperation(
                side=members[0].side,
                method=members[0].method,
                path=next(
                    (item.path for item in members if item.path is not None), None
                ),
                normalized_path=members[0].normalized_path,
                parameters=tuple(
                    sorted({value for item in members for value in item.parameters})
                ),
                dynamic=members[0].dynamic,
                classification=members[0].classification,
                sources=tuple(sources),
                request_schema=next(
                    (
                        item.request_schema
                        for item in members
                        if item.request_schema is not None
                    ),
                    None,
                ),
                response_schema=next(
                    (
                        item.response_schema
                        for item in members
                        if item.response_schema is not None
                    ),
                    None,
                ),
                error_schemas=tuple(
                    (status, json.loads(encoded))
                    for status, encoded in sorted(
                        {
                            (status, json.dumps(schema, sort_keys=True))
                            for item in members
                            for status, schema in item.error_schemas
                        }
                    )
                ),
                status_codes=tuple(
                    sorted(
                        {
                            status
                            for item in members
                            for status in item.status_codes
                        }
                    )
                ),
                auth=_merge_evidence_state(item.auth for item in members),
                authorization=_merge_evidence_state(
                    item.authorization for item in members
                ),
                tenant=_merge_evidence_state(item.tenant for item in members),
                handler=next(
                    (item.handler for item in members if item.handler is not None),
                    None,
                ),
                lineage=tuple(
                    _dedupe_mappings(
                        item for member in members for item in member.lineage
                    )
                ),
                ui_states=tuple(
                    sorted(
                        {
                            state
                            for item in members
                            for state in item.ui_states
                        }
                    )
                ),
                mutation=any(item.mutation for item in members),
                cache_invalidation=_merge_evidence_state(
                    item.cache_invalidation for item in members
                ),
            )
        )
    return tuple(result)


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


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(_json_value(dict(value)))


def _finding_evidence_value(value: Any) -> Any:
    normalized = _json_value(value)
    if isinstance(normalized, (dict, list)):
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return normalized


def _mapping_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None


def _unknown_anchor() -> SourceAnchor:
    return SourceAnchor("", 0, "unknown", "unknown", 0.0)


def _contract_id(*parts: object) -> str:
    identity = "|".join(str(part) for part in parts)
    prefix = str(parts[0]) if parts else "contract"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _field_path(prefix: str, field_name: str) -> str:
    return f"{prefix}.{field_name}" if prefix else field_name


def _schema_type(schema: Mapping[str, Any]) -> str:
    value = schema.get("type", "")
    if isinstance(value, list):
        return "|".join(sorted(str(item) for item in value if item != "null"))
    return str(value)


def _lineage_edge(kind: str) -> str:
    return {
        "handler": "handled_by",
        "service_operation": "calls",
        "entity": "accesses",
        "model": "uses_model",
    }.get(kind, "relates_to")


def _first_contract_shape(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            if "type" in value or "properties" in value or "items" in value:
                return dict(value)
            for name, candidate in sorted(value.items(), key=lambda item: str(item[0])):
                if isinstance(candidate, Mapping):
                    return {"name": str(name), **dict(candidate)}
    return None


def _migrate_legacy_project_map(value: Mapping[str, Any]) -> ProjectMap:
    frontend = tuple(
        _AdapterOperation.from_dict(item)
        for item in value.get("frontend_operations", [])
    )
    backend = tuple(
        _AdapterOperation.from_dict(item)
        for item in value.get("backend_operations", [])
    )
    nodes, edges, _suppressed = _build_contract_graph(
        frontend, backend, suppress_internal=False
    )
    return ProjectMap(
        nodes=nodes,
        edges=edges,
        findings=tuple(Finding.from_dict(item) for item in value.get("findings", [])),
        evidence={
            **dict(value.get("evidence", {})),
            "migrated_from_schema": 1,
        },
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


def _enrich_python_operations(
    operations: Iterable[_AdapterOperation],
    content: str,
) -> list[_AdapterOperation]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return list(operations)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    model_schemas = {
        name: _python_class_schema(node, classes)
        for name, node in classes.items()
        if _python_class_kind(node) == "model"
    }
    entities = {
        name: _python_class_fields(node, classes)
        for name, node in classes.items()
        if _python_class_kind(node) == "entity"
    }
    return [
        _enrich_python_operation(
            operation, functions, classes, model_schemas, entities
        )
        for operation in operations
    ]


def _enrich_python_operation(
    operation: _AdapterOperation,
    functions: Mapping[str, ast.FunctionDef | ast.AsyncFunctionDef],
    classes: Mapping[str, ast.ClassDef],
    model_schemas: Mapping[str, dict[str, Any]],
    entities: Mapping[str, dict[str, dict[str, Any]]],
) -> _AdapterOperation:
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
    dependency_names: list[str] = []
    request_schema = operation.request_schema
    positional = [*handler.args.posonlyargs, *handler.args.args]
    defaults = [None] * (len(positional) - len(handler.args.defaults)) + list(
        handler.args.defaults
    )
    for argument, default in zip(positional, defaults, strict=True):
        if isinstance(default, ast.Call) and _dotted_name(default.func).endswith(
            "Depends"
        ):
            if default.args:
                dependency_names.append(_dotted_name(default.args[0]))
            continue
        annotation_name = _annotation_name(argument.annotation)
        if annotation_name in model_schemas and request_schema is None:
            request_schema = {
                "name": annotation_name,
                **model_schemas[annotation_name],
            }
    response_schema = operation.response_schema
    status_codes = list(operation.status_codes)
    for decorator in handler.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "response_model":
                response_name = _annotation_name(keyword.value)
                if response_name in model_schemas:
                    response_schema = {
                        "name": response_name,
                        **model_schemas[response_name],
                    }
            elif keyword.arg == "status_code":
                status = _ast_literal(keyword.value)
                if status is not None:
                    status_codes.append(str(status))
            elif keyword.arg == "dependencies":
                dependency_names.append("decorator-dependency")
    if response_schema is None:
        return_name = _annotation_name(handler.returns)
        if return_name in model_schemas:
            response_schema = {"name": return_name, **model_schemas[return_name]}

    anchor = operation.sources[0] if operation.sources else _unknown_anchor()
    lineage: list[dict[str, Any]] = [
        {
            "kind": "handler",
            "name": handler.name,
            "source": asdict(replace(anchor, line=handler.lineno)),
            "provenance": "python:decorated-handler",
        }
    ]
    calls = _function_call_names(handler)
    service_names = [name for name in calls if name in functions and name != handler.name]
    entity_names = [name for name in calls if name in entities]
    for service_name in service_names:
        service = functions[service_name]
        lineage.append(
            {
                "kind": "service_operation",
                "name": service_name,
                "source": asdict(replace(anchor, line=service.lineno)),
                "provenance": "python:call-expression",
            }
        )
        entity_names.extend(
            name for name in _function_call_names(service) if name in entities
        )
    for entity_name in dict.fromkeys(entity_names):
        entity = classes[entity_name]
        lineage.append(
            {
                "kind": "entity",
                "name": entity_name,
                "source": asdict(replace(anchor, line=entity.lineno)),
                "provenance": "python:constructor-reference",
                "fields": entities[entity_name],
            }
        )
    lineage.extend(
        {
            "kind": "auth_requirement",
            "name": name or "dependency",
            "source": asdict(replace(anchor, line=handler.lineno)),
            "provenance": "fastapi:Depends",
        }
        for name in dict.fromkeys(dependency_names)
    )
    return replace(
        operation,
        request_schema=request_schema,
        response_schema=response_schema,
        status_codes=tuple(sorted(set(status_codes))),
        auth="present" if dependency_names else operation.auth,
        handler=handler.name,
        lineage=tuple(lineage),
    )


def _enrich_javascript_operation(
    operation: _AdapterOperation,
    content: str,
) -> _AdapterOperation:
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
                "source": asdict(anchor),
                "provenance": "javascript:route-handler-argument",
                "capability_status": "present",
            },
        ),
    )


def _python_class_kind(node: ast.ClassDef) -> str:
    bases = {_dotted_name(base).rsplit(".", 1)[-1] for base in node.bases}
    if "BaseModel" in bases:
        return "model"
    has_table = any(
        isinstance(statement, (ast.Assign, ast.AnnAssign))
        and any(
            target == "__tablename__"
            for target in (
                [
                    item.id
                    for item in statement.targets
                    if isinstance(item, ast.Name)
                ]
                if isinstance(statement, ast.Assign)
                else (
                    [statement.target.id]
                    if isinstance(statement.target, ast.Name)
                    else []
                )
            )
        )
        for statement in node.body
    )
    if has_table or bases & {"Base", "DeclarativeBase"}:
        return "entity"
    return "unknown"


def _python_class_schema(
    node: ast.ClassDef,
    classes: Mapping[str, ast.ClassDef],
) -> dict[str, Any]:
    properties = _python_class_fields(node, classes)
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
) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for statement in node.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(
            statement.target, ast.Name
        ):
            continue
        fields[statement.target.id] = _python_annotation_schema(
            statement.annotation, classes
        )
    return fields


def _python_annotation_schema(
    annotation: ast.expr | None,
    classes: Mapping[str, ast.ClassDef],
) -> dict[str, Any]:
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
            "items": _python_annotation_schema(annotation.slice, classes),
        }
    if name in classes:
        return {"name": name, "type": "object"}
    result = {"type": scalar.get(lowered, "unknown")}
    if _annotation_nullable(annotation):
        result["nullable"] = True
    return result


def _annotation_nullable(annotation: ast.expr | None) -> bool:
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotation_name(annotation.left) in {"None", "NoneType"} or _annotation_name(
            annotation.right
        ) in {"None", "NoneType"}
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


def _merge_evidence_state(values: Iterable[str]) -> str:
    states = {str(value) for value in values}
    known = states - {"unknown"}
    if len(known) > 1:
        return "contradictory"
    if known:
        return next(iter(known))
    return "unknown"


def _dedupe_mappings(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for value in values:
        payload = dict(value)
        deduped[json.dumps(payload, sort_keys=True, default=str)] = payload
    return [deduped[key] for key in sorted(deduped)]
