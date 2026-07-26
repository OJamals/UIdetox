"""Canonical typed contract graph, evidence lattice, and reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from uidetox.findings import Finding

CONTRACT_GRAPH_SCHEMA_VERSION = 2
HTTP_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")


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
class ContractSchema:
    """One source-identified schema variant, optionally anchored to a status."""

    identities: tuple[str, ...]
    shape: dict[str, Any]
    status: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContractSchema":
        return cls(
            identities=tuple(str(item) for item in value.get("identities", [])),
            shape=dict(value.get("shape", {})),
            status=_string_or_none(value.get("status")),
        )


@dataclass(frozen=True)
class ContractObservation:
    """Internal adapter fact converted into contract graph nodes."""

    side: str
    method: str | None
    path: str | None
    normalized_path: str | None
    identity: str = ""
    parameters: tuple[str, ...] = ()
    dynamic: bool = False
    classification: str = "application"
    sources: tuple[SourceAnchor, ...] = ()
    request_schemas: tuple[ContractSchema, ...] = ()
    response_schemas: tuple[ContractSchema, ...] = ()
    error_schemas: tuple[tuple[str, dict[str, Any]], ...] = ()
    status_codes: tuple[str, ...] = ()
    auth: str = "unknown"
    authorization: str = "unknown"
    tenant: str = "unknown"
    handler: str | None = None
    lineage: tuple[dict[str, Any], ...] = ()
    ui_states: tuple[str, ...] = ()
    ui_required: bool = False
    mutation: bool = False
    cache_invalidation: str = "unknown"
    evidence: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContractObservation":
        return cls(
            identity=str(value.get("identity", "")),
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
            request_schemas=_schemas_from_observation_dict(value, "request"),
            response_schemas=_schemas_from_observation_dict(value, "response"),
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
            ui_required=bool(value.get("ui_required", False)),
            mutation=bool(value.get("mutation", False)),
            cache_invalidation=str(value.get("cache_invalidation", "unknown")),
            evidence={
                str(key): str(state)
                for key, state in dict(value.get("evidence", {})).items()
            },
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


def reconcile_contract_graph(
    nodes: Iterable[ContractNode],
    edges: Iterable[ContractEdge],
    *,
    suppress_internal: bool = True,
) -> tuple[Finding, ...]:
    """Compare source-backed operation slices without collapsing source identities."""

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
    contradictory_backend: set[tuple[str, str]] = set()
    for path, path_items in back_by_path.items():
        for method, method_items in _graph_operations_by_method(path_items).items():
            axis = _contract_group_contradiction(method_items, outgoing)
            if axis is None:
                continue
            contradictory_backend.add((path, method))
            findings.append(
                _graph_finding(
                    "evidence_contradictory",
                    None,
                    method_items[0],
                    f"Backend {axis} observations contradict for {method} {path}.",
                    field=axis,
                    expected="one consistent source-backed contract",
                    actual=[node.id for node in method_items],
                    status="investigate",
                )
            )

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

        front_by_method = _graph_operations_by_method(front_items)
        back_by_method = _graph_operations_by_method(back_items)
        unmatched_front = sorted(set(front_by_method) - set(back_by_method))
        unmatched_back = sorted(set(back_by_method) - set(front_by_method))
        if unmatched_front or unmatched_back:
            findings.append(
                _graph_finding(
                    "method_mismatch",
                    front_by_method[unmatched_front[0]][0]
                    if unmatched_front
                    else front_items[0],
                    back_by_method[unmatched_back[0]][0]
                    if unmatched_back
                    else back_items[0],
                    "Same path has unmatched methods: "
                    f"frontend={unmatched_front}, backend={unmatched_back}.",
                )
            )
        for method in sorted(set(front_by_method) & set(back_by_method)):
            if (path, method) in contradictory_backend:
                continue
            for frontend_node in front_by_method[method]:
                for backend_node in back_by_method[method]:
                    difference = _first_contract_difference(
                        frontend_node, backend_node, outgoing
                    )
                    if difference is not None:
                        (
                            kind,
                            field_name,
                            detail,
                            expected,
                            actual,
                            investigate,
                        ) = difference
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

    deduped = {_semantic_finding_key(finding): finding for finding in findings}
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


def _graph_operations_by_method(
    operations: Iterable[ContractNode],
) -> dict[str, tuple[ContractNode, ...]]:
    grouped: dict[str, list[ContractNode]] = {}
    for operation in operations:
        grouped.setdefault(str(operation.attributes["method"]), []).append(operation)
    return {
        method: tuple(sorted(items, key=lambda item: item.id))
        for method, items in grouped.items()
    }


def _contract_group_contradiction(
    operations: tuple[ContractNode, ...],
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> str | None:
    """Return the first axis with contradictory concrete backend evidence."""

    axis_relations = {
        "request": "accepts",
        "response": "returns",
        "error": "returns_error",
    }
    for axis, relation in axis_relations.items():
        states = {
            _operation_evidence_state(
                operation,
                axis,
                bool(outgoing.get((operation.id, relation), [])),
            )
            for operation in operations
        } - {"unknown"}
        if len(states) > 1 or "contradictory" in states:
            return axis
        if states == {"present"}:
            shapes = {
                json.dumps(
                    (
                        _error_schemas_from_graph(operation.id, outgoing)
                        if axis == "error"
                        else sorted(
                            {
                                json.dumps(shape, sort_keys=True, default=str)
                                for _status, shape in _schema_variants_from_graph(
                                    operation.id,
                                    relation,
                                    outgoing,
                                )
                            }
                        )
                    ),
                    sort_keys=True,
                    default=str,
                )
                for operation in operations
                if _operation_evidence_state(operation, axis, True) == "present"
            }
            if len(shapes) > 1:
                return axis

    auth_values = [_auth_from_graph(operation.id, outgoing) for operation in operations]
    for axis in ("auth", "authorization", "tenant"):
        states = {value[axis] for value in auth_values} - {"unknown"}
        if len(states) > 1 or "contradictory" in states:
            return axis

    status_sets = {
        tuple(sorted(str(item) for item in operation.attributes.get("status_codes", [])))
        for operation in operations
        if _operation_evidence_state(
            operation,
            "status",
            bool(operation.attributes.get("status_codes")),
        )
        == "present"
    }
    if len(status_sets) > 1:
        return "status"
    return None


def _semantic_finding_key(finding: Finding) -> str:
    """Deduplicate one causal contract failure across duplicate observations."""

    evidence = finding.evidence
    return json.dumps(
        {
            "detector": finding.detector_id,
            "anchor": dict(finding.contract_anchor),
            "expected": evidence.get("expected"),
            "actual": evidence.get("actual"),
            "status": finding.status,
        },
        sort_keys=True,
        default=str,
    )


def build_contract_graph(
    frontend: Iterable[ContractObservation],
    backend: Iterable[ContractObservation],
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


def _operation_contract_node(operation: ContractObservation) -> ContractNode:
    anchor = operation.sources[0] if operation.sources else _unknown_anchor()
    kind = "client_operation" if operation.side == "frontend" else "route"
    evidence = {
        "request": _schema_observation_state(operation.request_schemas),
        "response": _schema_observation_state(
            operation.response_schemas,
            statuses_distinguish=True,
        ),
        "error": "present" if operation.error_schemas else "unknown",
        "status": "present" if operation.status_codes else "unknown",
        "ui_lifecycle": "present" if operation.ui_states else "unknown",
        "cache": operation.cache_invalidation,
        **operation.evidence,
    }
    evidence_states = {*evidence.values(), operation.auth, operation.authorization, operation.tenant}
    if "contradictory" in evidence_states:
        capability_status = "contradictory"
    elif (
        operation.dynamic
        or operation.method is None
        or operation.normalized_path is None
    ):
        capability_status = "unknown"
    else:
        capability_status = "present"
    identifier = _contract_id(
        kind,
        operation.side,
        operation.identity,
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
            "ui_required": operation.ui_required,
            "cache_invalidation": operation.cache_invalidation,
            "evidence": evidence,
            "identity": operation.identity,
            "sources": [asdict(source) for source in operation.sources],
        },
    )


def _append_operation_contract(
    nodes: list[ContractNode],
    edges: list[ContractEdge],
    operation_node: ContractNode,
    operation: ContractObservation,
) -> None:
    for kind, schemas in (
        ("request_schema", operation.request_schemas),
        ("response_schema", operation.response_schemas),
    ):
        for schema in schemas:
            _append_schema_contract(
                nodes,
                edges,
                operation_node,
                kind,
                schema.shape,
                name=(
                    schema.identities[0]
                    if schema.identities
                    else str(schema.shape.get("name", kind))
                ),
                status=schema.status,
                identities=schema.identities,
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
    lineage_nodes: dict[str, ContractNode] = {"operation": operation_node}
    lineage_items: list[tuple[dict[str, Any], ContractNode]] = []
    for item in operation.lineage:
        kind = str(item.get("kind", "unknown"))
        if kind == "auth_requirement":
            continue
        name = str(item.get("name", kind))
        reference = str(item.get("ref", f"{kind}:{name}"))
        anchor = SourceAnchor.from_dict(
            dict(item.get("source", asdict(operation_node.source)))
        )
        lineage_node = ContractNode(
            _contract_id(kind, operation_node.id, reference),
            kind,
            name,
            operation.side,
            str(item.get("capability_status", "present")),
            anchor,
            {
                key: _json_value(value)
                for key, value in item.items()
                if key not in {"kind", "name", "source", "fields", "ref", "parent"}
            },
        )
        nodes.append(lineage_node)
        lineage_nodes[reference] = lineage_node
        lineage_items.append((item, lineage_node))

    for item, lineage_node in lineage_items:
        kind = lineage_node.kind
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
        parent_reference = str(item.get("parent", "operation"))
        parent = lineage_nodes.get(parent_reference, operation_node)
        edges.append(
            _contract_edge(
                parent,
                lineage_node,
                str(item.get("edge", _lineage_edge(kind))),
                str(item.get("provenance", "static:lineage")),
            )
        )
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
    identities: tuple[str, ...] = (),
) -> None:
    schema_node = ContractNode(
        _contract_id(kind, operation_node.id, *identities, name, status or ""),
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
        | ({"status": status} if status is not None else {})
        | ({"type_identities": list(identities)} if identities else {}),
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
    capabilities = {frontend.capability_status, backend.capability_status}
    if "contradictory" in capabilities:
        return (
            "evidence_contradictory",
            "",
            "Static evidence contradicts itself; contract parity cannot be asserted.",
            backend.capability_status,
            frontend.capability_status,
            True,
        )
    if "unknown" in capabilities:
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
        front_schemas = _schema_variants_from_graph(frontend.id, relation, outgoing)
        back_schemas = _schema_variants_from_graph(backend.id, relation, outgoing)
        front_state = _operation_evidence_state(frontend, label, bool(front_schemas))
        back_state = _operation_evidence_state(backend, label, bool(back_schemas))
        state_difference = _evidence_state_difference(
            label, front_state, back_state, "schema"
        )
        if state_difference is not None:
            return state_difference
        if front_state == back_state == "present" and front_schemas and back_schemas:
            difference = _schema_variants_difference(
                label,
                front_schemas,
                back_schemas,
            )
            if difference is not None:
                return difference
        elif front_state == back_state == "present":
            return (
                f"{label}_evidence_unknown",
                "",
                f"{label.title()} schema evidence is incomplete.",
                back_schemas,
                front_schemas,
                True,
            )

    ui_difference = _ui_lifecycle_difference(frontend, backend, outgoing)
    if ui_difference is not None:
        return ui_difference

    front_auth = _auth_from_graph(frontend.id, outgoing)
    back_auth = _auth_from_graph(backend.id, outgoing)
    for attribute in ("auth", "authorization", "tenant"):
        frontend_value = front_auth[attribute]
        backend_value = back_auth[attribute]
        difference = _evidence_state_difference(
            attribute, frontend_value, backend_value, "requirement"
        )
        if difference is not None:
            return difference

    front_errors = _error_schemas_from_graph(frontend.id, outgoing)
    back_errors = _error_schemas_from_graph(backend.id, outgoing)
    front_error_state = _operation_evidence_state(
        frontend, "error", bool(front_errors)
    )
    back_error_state = _operation_evidence_state(backend, "error", bool(back_errors))
    difference = _evidence_state_difference(
        "error", front_error_state, back_error_state, "envelope"
    )
    if difference is not None:
        return difference
    if front_error_state == back_error_state == "present":
        if set(front_errors) != set(back_errors):
            return (
                "error_status_mismatch",
                "",
                "Error status envelopes differ.",
                sorted(back_errors),
                sorted(front_errors),
                False,
            )
        for status in sorted(front_errors):
            schema_difference = _schema_difference(
                front_errors[status], back_errors[status]
            )
            if schema_difference is not None:
                suffix, field, detail, expected, actual, investigate = (
                    schema_difference
                )
                return (
                    f"error_{suffix}",
                    field,
                    f"Error {status} contract {detail}.",
                    expected,
                    actual,
                    investigate,
                )

    front_statuses = {str(item) for item in front.get("status_codes", [])}
    back_statuses = {str(item) for item in back.get("status_codes", [])}
    front_status_state = _operation_evidence_state(
        frontend, "status", bool(front_statuses)
    )
    back_status_state = _operation_evidence_state(
        backend, "status", bool(back_statuses)
    )
    difference = _evidence_state_difference(
        "status", front_status_state, back_status_state, "set"
    )
    if difference is not None:
        return difference
    if (
        front_status_state == back_status_state == "present"
        and front_statuses != back_statuses
    ):
        return (
            "status_mismatch",
            "",
            "Success/error status sets differ.",
            sorted(back_statuses),
            sorted(front_statuses),
            False,
        )
    if front.get("mutation"):
        cache_state = _operation_evidence_state(
            frontend,
            "cache",
            front.get("cache_invalidation") == "present",
        )
        if cache_state == "unknown":
            return (
                "cache_invalidation_evidence_unknown",
                "",
                "Mutation cache invalidation evidence is incomplete.",
                "present",
                cache_state,
                True,
            )
        if cache_state == "contradictory":
            return (
                "cache_invalidation_evidence_contradictory",
                "",
                "Mutation cache invalidation evidence contradicts itself.",
                "present",
                cache_state,
                True,
            )
        if cache_state == "absent":
            return (
                "cache_invalidation_missing",
                "",
                "Mutation has no static cache invalidation evidence.",
                "present",
                "absent",
                False,
            )
    return None


def _ui_lifecycle_difference(
    frontend: ContractNode,
    backend: ContractNode,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> tuple[str, str, str, Any, Any, bool] | None:
    if not bool(frontend.attributes.get("ui_required", True)):
        return None
    states = {
        node.name for node in outgoing.get((frontend.id, "renders_state"), [])
    }
    evidence = _operation_evidence_state(frontend, "ui_lifecycle", bool(states))
    expected = (
        {"loading", "error", "success"}
        if frontend.attributes.get("mutation")
        else {"loading", "error", "empty", "success"}
    )
    if evidence == "contradictory":
        return (
            "ui_state_evidence_contradictory",
            "",
            "Frontend lifecycle evidence contradicts itself.",
            sorted(expected),
            evidence,
            True,
        )
    if evidence == "unknown":
        return (
            "ui_state_evidence_unknown",
            "",
            "Frontend lifecycle ownership is ambiguous.",
            sorted(expected),
            evidence,
            True,
        )
    response_bearing = (
        _operation_evidence_state(frontend, "response", False) == "present"
        or _operation_evidence_state(backend, "response", False) == "present"
    )
    if not response_bearing:
        return None
    missing = expected - states
    if evidence == "absent" or missing:
        return (
            "ui_state_missing",
            "",
            "Response-bearing UI operation lacks lifecycle coverage.",
            sorted(expected),
            sorted(states),
            False,
        )
    return None


def _operation_evidence_state(
    operation: ContractNode,
    axis: str,
    inferred_present: bool,
) -> str:
    evidence = operation.attributes.get("evidence", {})
    if isinstance(evidence, Mapping) and axis in evidence:
        state = str(evidence[axis])
        if state in {"present", "absent", "unknown", "contradictory"}:
            return state
    return "present" if inferred_present else "unknown"


def _evidence_state_difference(
    axis: str,
    frontend: str,
    backend: str,
    noun: str,
) -> tuple[str, str, str, Any, Any, bool] | None:
    states = {frontend, backend}
    if "contradictory" in states:
        return (
            f"{axis}_evidence_contradictory",
            "",
            f"{axis.title()} {noun} evidence contradicts itself.",
            backend,
            frontend,
            True,
        )
    if "unknown" in states:
        return (
            f"{axis}_evidence_unknown",
            "",
            f"{axis.title()} {noun} evidence is incomplete.",
            backend,
            frontend,
            True,
        )
    if frontend != backend:
        return (
            f"{axis}_mismatch",
            "",
            f"{axis.title()} {noun} presence differs.",
            backend,
            frontend,
            False,
        )
    return None


def _schema_difference(
    frontend: Mapping[str, Any],
    backend: Mapping[str, Any],
    prefix: str = "",
) -> tuple[str, str, str, Any, Any, bool] | None:
    front_type = _schema_type(frontend)
    back_type = _schema_type(backend)
    if bool(front_type) != bool(back_type):
        return (
            "field_type_evidence_unknown",
            prefix,
            f"field {prefix or '<root>'} type evidence is incomplete",
            back_type or "unknown",
            front_type or "unknown",
            True,
        )
    if front_type and back_type and front_type != back_type:
        return (
            "field_type_mismatch",
            prefix,
            f"field {prefix or '<root>'} type differs",
            back_type,
            front_type,
            False,
        )
    front_nullable = _schema_nullable(frontend)
    back_nullable = _schema_nullable(backend)
    if front_nullable != back_nullable:
        return (
            "field_nullability_mismatch",
            prefix,
            f"field {prefix or '<root>'} nullability differs",
            back_nullable,
            front_nullable,
            False,
        )
    front_enum = tuple(frontend.get("enum", ()))
    back_enum = tuple(backend.get("enum", ()))
    if set(front_enum) != set(back_enum):
        return (
            "field_enum_mismatch",
            prefix,
            f"field {prefix or '<root>'} enum differs",
            sorted(back_enum, key=str),
            sorted(front_enum, key=str),
            False,
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
        if frontend.get(constraint) != backend.get(constraint) and (
            constraint in frontend or constraint in backend
        ):
            return (
                "field_validation_mismatch",
                prefix,
                f"field {prefix or '<root>'} {constraint} differs",
                backend.get(constraint),
                frontend.get(constraint),
                False,
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
            False,
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
            False,
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
    if isinstance(front_items, Mapping) != isinstance(back_items, Mapping):
        return (
            "array_items_evidence_unknown",
            prefix,
            f"field {prefix or '<root>'} array item evidence is incomplete",
            bool(back_items),
            bool(front_items),
            True,
        )
    if isinstance(front_items, Mapping) and isinstance(back_items, Mapping):
        return _schema_difference(front_items, back_items, f"{prefix}[]" or "[]")
    return None


def _schema_variants_from_graph(
    operation_id: str,
    relation: str,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> tuple[tuple[str | None, dict[str, Any]], ...]:
    return tuple(
        (
            _string_or_none(node.attributes.get("status")),
            _schema_from_node(node, outgoing),
        )
        for node in sorted(
            outgoing.get((operation_id, relation), []),
            key=lambda item: (
                str(item.attributes.get("status", "")),
                item.name,
                item.id,
            ),
        )
    )


def _schema_variants_difference(
    label: str,
    frontend: tuple[tuple[str | None, dict[str, Any]], ...],
    backend: tuple[tuple[str | None, dict[str, Any]], ...],
) -> tuple[str, str, str, Any, Any, bool] | None:
    front_statuses = {status for status, _shape in frontend if status is not None}
    back_statuses = {status for status, _shape in backend if status is not None}
    fully_statused = len(front_statuses) == len(frontend) and len(back_statuses) == len(
        backend
    )
    comparisons: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    if fully_statused:
        if front_statuses != back_statuses:
            return (
                f"{label}_status_mismatch",
                "",
                f"{label.title()} status variants differ.",
                sorted(back_statuses),
                sorted(front_statuses),
                False,
            )
        front_by_status = {status: shape for status, shape in frontend}
        back_by_status = {status: shape for status, shape in backend}
        comparisons = [
            (str(status), front_by_status[status], back_by_status[status])
            for status in sorted(front_statuses)
        ]
    else:
        front_shapes = _unique_schema_shapes(frontend)
        back_shapes = _unique_schema_shapes(backend)
        if len(front_shapes) != 1 or len(back_shapes) != 1:
            return (
                f"{label}_evidence_unknown",
                "",
                f"{label.title()} variants are not fully status-anchored.",
                back_shapes,
                front_shapes,
                True,
            )
        comparisons = [("", front_shapes[0], back_shapes[0])]

    for status, front_shape, back_shape in comparisons:
        difference = _schema_difference(front_shape, back_shape)
        if difference is None:
            continue
        suffix, field_name, detail, expected, actual, investigate = difference
        status_detail = f" status {status}" if status else ""
        return (
            f"{label}_{suffix}",
            field_name,
            f"{label.title()}{status_detail} contract {detail}.",
            expected,
            actual,
            investigate,
        )
    return None


def _unique_schema_shapes(
    variants: tuple[tuple[str | None, dict[str, Any]], ...],
) -> tuple[dict[str, Any], ...]:
    unique = {
        json.dumps(shape, sort_keys=True, default=str): shape
        for _status, shape in variants
    }
    return tuple(unique[key] for key in sorted(unique))


def _error_schemas_from_graph(
    operation_id: str,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> dict[str, dict[str, Any]]:
    return {
        str(node.attributes.get("status", "")): _schema_from_node(node, outgoing)
        for node in outgoing.get((operation_id, "returns_error"), [])
    }


def _schema_from_node(
    node: ContractNode,
    outgoing: Mapping[tuple[str, str], list[ContractNode]],
) -> dict[str, Any]:
    schema = {
        key: _json_value(value)
        for key, value in node.attributes.items()
        if key not in {"status", "type_identities"}
        and not (key == "required" and isinstance(value, bool))
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


def _normalize_method(value: Any) -> str | None:
    if value is None:
        return None
    method = str(value).upper()
    return method if method in HTTP_METHODS else None


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


def _schema_nullable(schema: Mapping[str, Any]) -> bool:
    value = schema.get("type")
    return bool(schema.get("nullable", False)) or (
        isinstance(value, list) and "null" in value
    )


def _lineage_edge(kind: str) -> str:
    return {
        "handler": "handled_by",
        "service_operation": "calls",
        "entity": "accesses",
        "model": "uses_model",
    }.get(kind, "relates_to")


def contract_schema_observations(
    *values: Any,
    fallback: str,
    status: str | None = None,
) -> tuple[ContractSchema, ...]:
    """Normalize all schema identities; collapse only semantic duplicates."""

    candidates: list[tuple[str, dict[str, Any]]] = []
    for value in values:
        if isinstance(value, Mapping):
            if "type" in value or "properties" in value or "items" in value:
                shape = dict(value)
                identity = str(shape.pop("name", fallback))
                candidates.append((identity, shape))
                continue
            for name, candidate in value.items():
                if isinstance(candidate, Mapping):
                    shape = dict(candidate)
                    identity = str(shape.pop("name", name))
                    candidates.append((identity, shape))
    grouped: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for identity, shape in candidates:
        key = json.dumps(
            {"status": status, "shape": shape},
            sort_keys=True,
            default=str,
        )
        existing_shape, identities = grouped.setdefault(key, (shape, []))
        if identity not in identities:
            identities.append(identity)
        grouped[key] = (existing_shape, identities)
    return tuple(
        ContractSchema(tuple(sorted(identities)), shape, status)
        for key, (shape, identities) in sorted(grouped.items())
    )


def _schemas_from_observation_dict(
    value: Mapping[str, Any],
    label: str,
) -> tuple[ContractSchema, ...]:
    plural = value.get(f"{label}_schemas")
    if isinstance(plural, list):
        return tuple(
            ContractSchema.from_dict(item)
            for item in plural
            if isinstance(item, Mapping)
        )
    return contract_schema_observations(
        value.get(f"{label}_schema"),
        fallback=f"{label}_schema",
    )


def _schema_observation_state(
    schemas: tuple[ContractSchema, ...],
    *,
    statuses_distinguish: bool = False,
) -> str:
    if not schemas:
        return "unknown"
    if len(schemas) == 1:
        return "present"
    if statuses_distinguish and all(schema.status is not None for schema in schemas):
        statuses = [schema.status for schema in schemas]
        return "present" if len(statuses) == len(set(statuses)) else "contradictory"
    return "contradictory"


def _migrate_legacy_project_map(value: Mapping[str, Any]) -> ProjectMap:
    frontend = tuple(
        ContractObservation.from_dict(item)
        for item in value.get("frontend_operations", [])
    )
    backend = tuple(
        ContractObservation.from_dict(item)
        for item in value.get("backend_operations", [])
    )
    nodes, edges, _suppressed = build_contract_graph(
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


def dedupe_contract_observations(
    operations: Iterable[ContractObservation],
) -> tuple[ContractObservation, ...]:
    """Remove byte-for-byte duplicate observations without merging identities."""

    deduped: dict[str, ContractObservation] = {}
    for operation in operations:
        anchor = operation.sources[0] if operation.sources else _unknown_anchor()
        identity = operation.identity or _contract_id(
            "observation",
            operation.side,
            anchor.file,
            anchor.line,
            anchor.extractor,
            operation.method or "?",
            operation.normalized_path or operation.path or "?",
        )
        normalized = (
            operation
            if operation.identity
            else replace(operation, identity=identity)
        )
        payload = json.dumps(asdict(normalized), sort_keys=True, default=str)
        deduped[payload] = normalized
    return tuple(
        sorted(
            deduped.values(),
            key=lambda item: (
                item.side,
                item.normalized_path or item.path or "",
                item.method or "",
                item.identity,
            ),
        )
    )
