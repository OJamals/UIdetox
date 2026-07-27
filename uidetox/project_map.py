"""Stable facade for versioned full-stack contract lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from uidetox.contract_adapters import extract_backend_observations
from uidetox.contract_graph import (
    CONTRACT_GRAPH_SCHEMA_VERSION,
    ContractEdge,
    ContractNode,
    ContractObservation,
    ProjectMap,
    SourceAnchor,
    _schema_observation_state,
    _string_or_none,
    build_contract_graph,
    contract_schema_observations,
    dedupe_contract_observations,
    normalize_http_method,
    normalize_route_path,
    reconcile_contract_graph,
)

__all__ = [
    "CONTRACT_GRAPH_SCHEMA_VERSION",
    "ContractEdge",
    "ContractNode",
    "ProjectMap",
    "SourceAnchor",
    "build_project_map",
    "normalize_route_path",
    "project_source_manifest",
    "reconcile_contract_graph",
]


def build_project_map(
    root: str | Path,
    frontend_nodes: Iterable[Any] = (),
    *,
    suppress_internal: bool = True,
) -> ProjectMap:
    """Build one graph spanning frontend calls and backend contract evidence."""

    root_path = Path(root).expanduser().resolve()
    backend, extraction = extract_backend_observations(root_path)
    backend = dedupe_contract_observations(backend)
    backend_sites = {
        (source.file, source.line)
        for operation in backend
        for source in operation.sources
    }
    frontend = dedupe_contract_observations(
        _frontend_observations(frontend_nodes, backend_sites)
    )
    nodes, edges, suppressed = build_contract_graph(
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
    return ProjectMap(nodes=nodes, edges=edges, findings=findings, evidence=evidence)


def project_source_manifest(root: str | Path) -> dict[str, str]:
    """Hash every source that can contribute backend/API evidence."""

    root_path = Path(root).expanduser().resolve()
    _, extraction = extract_backend_observations(root_path)
    return dict(extraction["source_manifest"])


def _frontend_observations(
    nodes: Iterable[Any],
    backend_sites: set[tuple[str, int]],
) -> list[ContractObservation]:
    operations: list[ContractObservation] = []
    for node in nodes:
        kind = _node_value(node, "kind", "")
        if kind != "data":
            continue
        metadata = dict(_node_value(node, "metadata", {}) or {})
        if metadata.get("transport") != "http":
            continue
        source_site = (
            str(_node_value(node, "file", "")),
            int(_node_value(node, "line", 0)),
        )
        if source_site in backend_sites:
            continue
        path = _string_or_none(_node_value(node, "name", None))
        normalized, parameters, unresolved = normalize_route_path(path)
        method = normalize_http_method(metadata.get("method"))
        dynamic = bool(metadata.get("dynamic", False)) or unresolved or path is None
        request_schemas = contract_schema_observations(
            metadata.get("request_contracts"),
            metadata.get("request_schema"),
            fallback="request_schema",
        )
        response_schemas = contract_schema_observations(
            metadata.get("response_contracts"),
            metadata.get("response_schema"),
            fallback="response_schema",
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
            ContractObservation(
                identity=str(_node_value(node, "id", "")),
                side="frontend",
                method=method,
                path=path,
                normalized_path=normalized,
                parameters=parameters,
                dynamic=dynamic,
                request_schemas=request_schemas,
                response_schemas=response_schemas,
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
                ui_required=bool(metadata.get("ui_required", False)),
                mutation=bool(
                    metadata.get(
                        "mutation", method not in {None, "GET", "HEAD", "OPTIONS"}
                    )
                ),
                cache_invalidation=str(metadata.get("cache_invalidation", "unknown")),
                evidence={
                    "request": (
                        _schema_observation_state(request_schemas)
                        if request_schemas
                        else "absent"
                        if method in {"GET", "HEAD", "OPTIONS"}
                        else "unknown"
                    ),
                    "response": (
                        _schema_observation_state(
                            response_schemas,
                            statuses_distinguish=True,
                        )
                        if response_schemas
                        else "unknown"
                    ),
                    "error": (
                        "present"
                        if metadata.get("error_schemas")
                        else str(metadata.get("error_evidence", "unknown"))
                    ),
                    "status": (
                        "present" if metadata.get("status_codes") else "unknown"
                    ),
                    "ui_lifecycle": (
                        str(metadata["ui_lifecycle_evidence"])
                        if metadata.get("ui_lifecycle_evidence")
                        in {"present", "absent", "unknown", "contradictory"}
                        else "present"
                        if ui_states
                        else "unknown"
                        if metadata.get("ui_required")
                        else "absent"
                    ),
                    "cache": str(metadata.get("cache_invalidation", "unknown")),
                },
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


def _node_value(node: Any, key: str, default: Any) -> Any:
    if isinstance(node, Mapping):
        return node.get(key, default)
    return getattr(node, key, default)
