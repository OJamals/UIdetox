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


def test_absent_required_parameter_evidence_fails_closed() -> None:
    back = _lineage(
        "back-order-id",
        "backend",
        "api_parameter",
        "orderId",
        location="path",
        required=True,
        style="simple",
        explode=False,
    )

    findings = _findings((), ((back, "declares_parameter"),))

    assert [finding.detector_id for finding in findings] == [
        "contract-required-parameter-evidence-unknown"
    ]
    assert findings[0].status == "investigate"
    assert findings[0].contract_anchor["field"] == "path:orderId"


def test_missing_required_parameter_evidence_is_investigative() -> None:
    required = _lineage(
        "back-tenant",
        "backend",
        "api_parameter",
        "tenant",
        location="query",
        required=True,
    )

    findings = _findings((), ((required, "declares_parameter"),))

    assert [finding.detector_id for finding in findings] == [
        "contract-required-parameter-evidence-unknown"
    ]
    assert findings[0].status == "investigate"


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
                                "idempotency": {
                                    "applicable": True,
                                    "scope": "one order creation",
                                },
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
    frontend_obligations = {
        node.name: node
        for node in frontend_nodes
        if node.kind == "operation_obligation"
    }
    assert set(frontend_obligations) == {"cancellation", "conflict", "idempotency"}
    assert {node.capability_status for node in frontend_obligations.values()} == {
        "unknown"
    }
    assert {
        node.attributes["evidence_status"] for node in frontend_obligations.values()
    } == {"transport-token-only"}
    obligation_findings = [
        finding
        for finding in project_map.findings
        if finding.detector_id.startswith("contract-operation-obligation-")
    ]
    assert {
        (finding.contract_anchor["field"], finding.status)
        for finding in obligation_findings
    } == {
        ("cancellation", "investigate"),
        ("conflict", "investigate"),
        ("duplicate-submit", "pending"),
        ("idempotency", "investigate"),
        ("retry", "pending"),
    }


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


def test_literal_url_serialization_becomes_exact_parameter_evidence(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function list(orderId: string) {
  await fetch("/orders?ids=a,b&page=2&sort=name", {
    headers: { "Cookie": "session=abc; theme=dark" }
  });
  return fetch(`/orders/${orderId}`, { headers: { "If-Match": "v1" } });
}
""".strip(),
        encoding="utf-8",
    )

    project = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)
    frontend = [
        node
        for node in project.nodes
        if node.side == "frontend" and node.kind == "api_parameter"
    ]
    values = {
        (
            node.attributes.get("location"),
            node.name,
            node.attributes.get("style"),
            node.attributes.get("explode"),
        )
        for node in frontend
    }

    assert ("query", "ids", "form", False) in values
    assert ("query", "page", "form", True) in values
    assert ("query", "sort", "form", True) in values
    assert ("cookie", "session", "form", True) in values
    assert ("cookie", "theme", "form", True) in values
    assert ("path", "orderId", "simple", False) in values


def test_literal_url_search_params_preserve_stable_query_semantics(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function list() {
  return fetch("/orders?" + new URLSearchParams({
    page: "2",
    filter: "open",
    sort: "created_at"
  }), {});
}
""".strip(),
        encoding="utf-8",
    )

    project = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)
    frontend = [
        node
        for node in project.nodes
        if node.side == "frontend"
        and node.kind == "api_parameter"
        and node.attributes.get("location") == "query"
    ]

    assert {node.name for node in frontend} == {"filter", "page", "sort"}
    assert {
        (node.attributes.get("style"), node.attributes.get("explode"))
        for node in frontend
    } == {("form", True)}


def test_request_media_requires_matching_body_serialization(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function save(payload: unknown) {
  return fetch("/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload
  });
}
""".strip(),
        encoding="utf-8",
    )

    project = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert not [
        node
        for node in project.nodes
        if node.side == "frontend" and node.kind == "request_media_type"
    ]


def test_dynamic_url_search_params_do_not_become_exact_evidence(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function list(page: string) {
  return fetch("/orders?" + new URLSearchParams({ page }), {});
}
""".strip(),
        encoding="utf-8",
    )

    project = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert not [
        node
        for node in project.nodes
        if node.side == "frontend" and node.kind == "api_parameter"
    ]


def test_header_like_text_inside_fetch_body_is_not_transport_evidence(
    tmp_path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function save() {
  return fetch("/orders", {
    method: "POST",
    body: '\"Content-Type\": \"application/json\"'
  });
}
""".strip(),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert not [
        node
        for node in project_map.nodes
        if node.side == "frontend"
        and node.kind in {"api_parameter", "request_media_type"}
    ]


def test_accept_header_without_exact_response_parser_does_not_guess(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function load() {
  const response = await fetch("/orders", {
    headers: { "Accept": "application/json" }
  });
  if (response.status !== 200) throw new Error("request failed");
  return response;
}
""".strip(),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert not [
        node
        for node in project_map.nodes
        if node.side == "frontend" and node.kind == "response_media_type"
    ]


def test_response_parsers_are_scoped_to_their_fetch_binding(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function loadOrders() {
  const response = await fetch("/orders", {
    headers: { "Accept": "application/json" }
  });
  if (response.status !== 200) throw new Error("orders failed");
  return response.json();
}
export async function loadReport() {
  const response = await fetch("/report", {
    headers: { "Accept": "text/plain" }
  });
  if (response.status !== 206) throw new Error("report failed");
  return response.text();
}
""".strip(),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert {
        (node.name, node.attributes.get("status"))
        for node in project_map.nodes
        if node.side == "frontend" and node.kind == "response_media_type"
    } == {("application/json", "200"), ("text/plain", "206")}


def test_unrelated_object_status_does_not_become_fetch_response_evidence(
    tmp_path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
export async function load(local: { status: number }) {
  const response = await fetch("/orders", {
    headers: { "Accept": "application/json" }
  });
  if (local.status === 409) throw new Error("local conflict");
  if (response.status !== 200) throw new Error("request failed");
  return response.json();
}
""".strip(),
        encoding="utf-8",
    )

    project_map = ProjectMap.from_dict(map_frontend(tmp_path, "src").project_map)

    assert {
        (node.name, node.attributes.get("status"))
        for node in project_map.nodes
        if node.side == "frontend" and node.kind == "response_media_type"
    } == {("application/json", "200")}
