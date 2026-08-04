from __future__ import annotations

import json

from uidetox.frontend_map import map_frontend
from uidetox.project_map import (
    ContractEdge,
    ContractNode,
    ProjectMap,
    SourceAnchor,
    reconcile_contract_graph,
)

SOURCE = SourceAnchor("client.ts", 1, "test", "test", 1.0)


def _operation(identifier: str, side: str) -> ContractNode:
    return ContractNode(
        identifier,
        "client_operation" if side == "frontend" else "route",
        "POST /orders",
        side,
        "present",
        SOURCE,
        {
            "method": "POST",
            "normalized_path": "/orders",
            "dynamic": False,
            "status_codes": ["200", "409"],
            "mutation": False,
            "evidence": {
                "request": "absent",
                "response": "absent",
                "error": "absent",
                "status": "present",
                "ui_lifecycle": "absent",
                "cache": "absent",
            },
        },
    )


def _lineage(
    identifier: str,
    side: str,
    kind: str,
    name: str,
    **attributes,
) -> ContractNode:
    return ContractNode(
        identifier,
        kind,
        name,
        side,
        "present",
        SOURCE,
        attributes,
    )


def _findings(
    front_lineage: tuple[tuple[ContractNode, str], ...],
    back_lineage: tuple[tuple[ContractNode, str], ...],
):
    front = _operation("front", "frontend")
    back = _operation("back", "backend")
    front_auth = _lineage(
        "front-auth",
        "frontend",
        "auth_requirement",
        "authentication",
        authorization="absent",
        tenant="absent",
    )
    back_auth = _lineage(
        "back-auth",
        "backend",
        "auth_requirement",
        "authentication",
        authorization="absent",
        tenant="absent",
    )
    nodes = [front, back, front_auth, back_auth]
    edges = [
        ContractEdge("front", "front-auth", "requires", "test", 1.0, SOURCE),
        ContractEdge("back", "back-auth", "requires", "test", 1.0, SOURCE),
    ]
    for parent, rows in ((front, front_lineage), (back, back_lineage)):
        for node, relation in rows:
            nodes.append(node)
            edges.append(
                ContractEdge(parent.id, node.id, relation, "test", 1.0, SOURCE)
            )
    return reconcile_contract_graph(nodes, edges)


def test_selected_request_media_must_match_exact_backend_media() -> None:
    front = _lineage(
        "front-json",
        "frontend",
        "request_media_type",
        "application/json",
        schema={"type": "object"},
    )
    back = _lineage(
        "back-cbor",
        "backend",
        "request_media_type",
        "application/cbor",
        schema={"type": "object"},
    )

    findings = _findings(
        ((front, "accepts_media_type"),), ((back, "accepts_media_type"),)
    )

    assert [finding.detector_id for finding in findings] == [
        "contract-request-media-type-mismatch"
    ]
    assert findings[0].evidence["expected"] == '["application/cbor"]'
    assert findings[0].evidence["actual"] == '["application/json"]'


def test_parameter_serialization_mismatch_is_smallest_causal_finding() -> None:
    front = _lineage(
        "front-query",
        "frontend",
        "api_parameter",
        "ids",
        location="query",
        style="form",
        explode=False,
    )
    back = _lineage(
        "back-query",
        "backend",
        "api_parameter",
        "ids",
        location="query",
        style="pipeDelimited",
        explode=False,
    )

    findings = _findings(
        ((front, "declares_parameter"),), ((back, "declares_parameter"),)
    )

    assert [finding.detector_id for finding in findings] == [
        "contract-parameter-serialization-mismatch"
    ]
    assert findings[0].contract_anchor["field"] == "query:ids"


def test_response_media_is_compared_within_exact_status() -> None:
    front = _lineage(
        "front-problem",
        "frontend",
        "response_media_type",
        "application/problem+json",
        status="409",
    )
    back = _lineage(
        "back-text",
        "backend",
        "response_media_type",
        "text/plain",
        status="409",
    )

    findings = _findings(
        ((front, "returns_media_type"),), ((back, "returns_media_type"),)
    )

    assert [finding.detector_id for finding in findings] == [
        "contract-response-media-type-mismatch"
    ]
    assert findings[0].contract_anchor["field"] == "409"


def test_matching_transport_evidence_adds_no_finding() -> None:
    front = _lineage(
        "front-json",
        "frontend",
        "request_media_type",
        "application/json",
        schema={"type": "object"},
    )
    back = _lineage(
        "back-json",
        "backend",
        "request_media_type",
        "application/json",
        schema={"type": "object"},
    )

    assert not _findings(
        ((front, "accepts_media_type"),),
        ((back, "accepts_media_type"),),
    )


def test_absent_frontend_transport_evidence_does_not_guess() -> None:
    back = _lineage(
        "back-json",
        "backend",
        "request_media_type",
        "application/json",
        schema={"type": "object"},
    )

    assert not _findings((), ((back, "accepts_media_type"),))


def test_literal_fetch_options_become_exact_operation_evidence(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function save(payload: unknown, signal: AbortSignal) {
  const response = await fetch("/orders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "Idempotency-Key": "create-order-1",
      "If-Match": "v1"
    },
    body: JSON.stringify(payload),
    signal
  });
  if (response.status === 409) throw new Error("conflict");
  if (response.status !== 200) throw new Error("request failed");
  return response.json();
}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/orders": {
                        "post": {
                            "parameters": [
                                {"in": "header", "name": "Idempotency-Key"},
                                {"in": "header", "name": "If-Match"},
                            ],
                            "requestBody": {
                                "content": {
                                    "application/json": {"schema": {"type": "object"}}
                                }
                            },
                            "responses": {
                                status: {
                                    "content": {
                                        "application/json": {
                                            "schema": {"type": "object"}
                                        }
                                    }
                                }
                                for status in ("200", "409")
                            },
                            "x-uidetox-operation": {
                                "idempotency": {"applicable": True},
                                "cancellation": {"applicable": True},
                                "conflict": {"applicable": True},
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)
    frontend_nodes = [node for node in project_map.nodes if node.side == "frontend"]

    assert {
        (node.kind, node.name, node.attributes.get("status"))
        for node in frontend_nodes
        if node.kind in {"request_media_type", "response_media_type"}
    } == {
        ("request_media_type", "application/json", None),
        ("response_media_type", "application/json", "200"),
        ("response_media_type", "application/json", "409"),
    }
    assert {node.name for node in frontend_nodes if node.kind == "api_parameter"} == {
        "Idempotency-Key",
        "If-Match",
    }
    assert {
        node.name for node in frontend_nodes if node.kind == "operation_obligation"
    } == {"cancellation", "conflict", "idempotency"}
    assert not [
        finding
        for finding in project_map.findings
        if finding.detector_id.startswith("contract-operation-obligation-")
    ]


def test_dynamic_fetch_options_do_not_create_literal_transport_evidence(
    tmp_path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
const options = { headers: { "Content-Type": mediaType } };
export async function load() {
  return fetch("/orders", options);
}
""".strip(),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert not [
        node
        for node in project_map.nodes
        if node.side == "frontend"
        and node.kind in {"api_parameter", "request_media_type", "response_media_type"}
    ]
