from __future__ import annotations

import json

from uidetox.project_map import (
    ContractEdge,
    ContractNode,
    SourceAnchor,
    build_project_map,
    reconcile_contract_graph,
)


def _nodes(project, kind: str):
    return [node for node in project.nodes if node.kind == kind]


def test_openapi_preserves_exact_document_transport_and_security_evidence(
    tmp_path,
) -> None:
    document = {
        "openapi": "3.2.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "servers": [{"url": "https://api.example.test/v2"}],
        "components": {
            "securitySchemes": {
                "OAuth": {
                    "type": "oauth2",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": "/token",
                            "scopes": {"orders:read": "Read orders"},
                        }
                    },
                }
            }
        },
        "paths": {
            "/orders": {
                "get": {
                    "parameters": [
                        {
                            "name": "ids",
                            "in": "query",
                            "style": "form",
                            "explode": False,
                            "schema": {"type": "array", "items": {"type": "string"}},
                        }
                    ],
                    "security": [{}, {"OAuth": ["orders:read"]}],
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"type": "object"}},
                            "application/cbor": {
                                "schema": {"type": "string", "format": "binary"}
                            },
                        }
                    },
                    "responses": {
                        "200": {
                            "headers": {"ETag": {"schema": {"type": "string"}}},
                            "links": {
                                "next": {
                                    "operationId": "listOrders",
                                    "parameters": {"cursor": "$response.body#/next"},
                                }
                            },
                            "content": {
                                "application/json": {"schema": {"type": "array"}},
                                "text/csv": {"schema": {"type": "string"}},
                            },
                        },
                        "default": {
                            "content": {
                                "application/problem+json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        },
                    },
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)

    route = _nodes(project, "route")[0]
    assert route.attributes["contract"] == {
        "json_schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        "openapi_version": "3.2.0",
        "servers": [{"url": "https://api.example.test/v2"}],
    }
    parameter = _nodes(project, "api_parameter")[0]
    assert (
        parameter.attributes["location"],
        parameter.attributes["style"],
        parameter.attributes["explode"],
    ) == (
        "query",
        "form",
        False,
    )
    assert {
        (
            node.kind,
            node.name,
            node.attributes.get("status"),
            node.attributes.get("schema", {}).get("type"),
        )
        for node in project.nodes
        if node.kind in {"request_media_type", "response_media_type"}
    } == {
        ("request_media_type", "application/cbor", None, "string"),
        ("request_media_type", "application/json", None, "object"),
        ("response_media_type", "application/json", "200", "array"),
        ("response_media_type", "application/problem+json", "default", "object"),
        ("response_media_type", "text/csv", "200", "string"),
    }
    link = _nodes(project, "response_link")[0]
    assert link.name == "next"
    assert link.attributes["operation_id"] == "listOrders"
    alternatives = _nodes(project, "auth_alternative")
    assert any(node.attributes["allows_anonymous"] for node in alternatives)
    scheme = _nodes(project, "auth_scheme_requirement")[0]
    assert scheme.attributes["scheme"]["type"] == "oauth2"


def test_openapi_schema_evidence_is_bounded_recursive_and_directional(tmp_path) -> None:
    properties = {f"field_{index:03d}": {"type": "string"} for index in range(160)}
    properties["aaaServerOnly"] = {
        "type": "string",
        "readOnly": True,
        "default": "ready",
    }
    properties["aabClientOnly"] = {
        "type": "integer",
        "writeOnly": True,
        "multipleOf": 2,
    }
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "unevaluatedProperties": False,
                    "properties": {
                        "child": {"$ref": "#/components/schemas/Node"},
                        **properties,
                    },
                }
            }
        },
        "paths": {
            "/nodes": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {"$ref": "#/components/schemas/Node"},
                                        {"type": "null"},
                                    ],
                                    "discriminator": {"propertyName": "kind"},
                                }
                            }
                        }
                    },
                    "responses": {"204": {"description": "done"}},
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    schema = _nodes(project, "request_media_type")[0].attributes["schema"]

    assert len(schema["oneOf"]) == 2
    assert schema["discriminator"] == {"propertyName": "kind"}
    node_shape = schema["oneOf"][0]
    assert node_shape["reference"] == "#/components/schemas/Node"
    assert node_shape["unevaluatedProperties"] is False
    assert node_shape["truncated"] is True
    assert node_shape["capability_status"] == "unknown"
    assert len(node_shape["properties"]) == 128
    assert node_shape["properties"]["aaaServerOnly"] == {
        "default": "ready",
        "readOnly": True,
        "type": "string",
    }
    child = node_shape["properties"]["child"]
    assert child == {
        "capability_status": "unknown",
        "name": "Node",
        "reference": "#/components/schemas/Node",
        "type": "recursive",
    }
    assert _nodes(project, "request_schema")[0].capability_status == "unknown"


def test_openapi_all_of_overflow_is_explicitly_unknown(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/aggregate": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "allOf": [
                                            {
                                                "type": "object",
                                                "properties": {
                                                    f"field_{index}": {"type": "string"}
                                                },
                                            }
                                            for index in range(40)
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    shape = _nodes(project, "response_media_type")[0].attributes["schema"]

    assert len(shape["allOf"]) == 32
    assert shape["truncated"] is True
    assert shape["capability_status"] == "unknown"


def test_openapi_schema_scalars_are_bounded_and_fail_closed(tmp_path) -> None:
    oversized = "x" * 1_000_000
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/oversized": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "string",
                                        "default": oversized,
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    shape = _nodes(project, "response_media_type")[0].attributes["schema"]

    assert shape["default"] == ""
    assert shape["truncated"] is True
    assert shape["capability_status"] == "unknown"
    assert len(json.dumps(project.to_dict())) < 100_000


def test_explicit_operation_applicability_is_bounded_and_fail_closed(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "post": {
                    "x-uidetox-operation": {
                        "auth-required": {"applicable": True, "scheme": "OAuth"},
                        "forbidden": {"applicable": True, "status": "403"},
                        "rate-limit": {"applicable": True, "status": "429"},
                        "retry": {"applicable": True, "condition": "503"},
                        "stale-refresh": {"applicable": True},
                        "timeout": {"applicable": True, "condition": "30s"},
                        "validation": {"applicable": True, "status": "422"},
                        "idempotency": {"applicable": False},
                        "conflict": "unknown",
                        "partial-success": {"applicable": True, "status": "207"},
                        "affected-reads": {
                            "applicable": True,
                            "operations": ["GET /orders"],
                        },
                        "cancellation": {"applicable": True},
                        "duplicate-submit": {"applicable": True},
                        "optimistic-rollback": {
                            "applicable": True,
                            "scope": "<script>alert(1)</script>",
                        },
                        "<script>alert(1)</script>": {"applicable": True},
                    },
                    "responses": {"202": {"description": "accepted"}},
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    obligations = _nodes(project, "operation_obligation")
    by_name = {node.name: node for node in obligations}

    assert set(by_name) == {
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
    }
    assert by_name["retry"].capability_status == "present"
    assert by_name["idempotency"].capability_status == "absent"
    assert by_name["conflict"].capability_status == "unknown"
    assert by_name["optimistic-rollback"].capability_status == "unknown"
    assert by_name["optimistic-rollback"].attributes["applicable"] is None
    assert by_name["optimistic-rollback"].attributes["constraint_status"] == "unknown"
    assert by_name["affected-reads"].attributes["operations"] == ["GET /orders"]
    assert "<script>" not in json.dumps([node.to_dict() for node in obligations])


def test_truncated_schema_comparison_is_investigate_not_equal() -> None:
    from uidetox.contract_graph import _schema_difference

    difference = _schema_difference(
        {"type": "object", "properties": {}},
        {
            "type": "object",
            "properties": {},
            "truncated": True,
            "capability_status": "unknown",
        },
    )

    assert difference == (
        "schema_evidence_unknown",
        "",
        "field <root> schema evidence is incomplete",
        "unknown",
        "present",
        True,
    )

    nested = _schema_difference(
        {"oneOf": [{"type": "object"}]},
        {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "child": {
                            "type": "recursive",
                            "capability_status": "unknown",
                        }
                    },
                }
            ]
        },
    )
    assert nested is not None
    assert nested[0] == "schema_evidence_unknown"
    assert nested[-1] is True


def test_reconciliation_reports_only_missing_applicable_operation_obligations() -> None:
    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)
    common = {
        "method": "POST",
        "normalized_path": "/orders",
        "dynamic": False,
        "status_codes": ["202"],
        "evidence": {
            "request": "absent",
            "response": "absent",
            "error": "absent",
            "status": "present",
            "ui_lifecycle": "present",
            "cache": "absent",
        },
    }
    frontend = ContractNode(
        "front",
        "client_operation",
        "POST /orders",
        "frontend",
        "present",
        source,
        common,
    )
    backend = ContractNode(
        "back", "route", "POST /orders", "backend", "present", source, common
    )
    retry = ContractNode(
        "back-retry",
        "operation_obligation",
        "retry",
        "backend",
        "present",
        source,
        {"applicable": True, "condition": "503"},
    )
    unknown = ContractNode(
        "back-conflict",
        "operation_obligation",
        "conflict",
        "backend",
        "unknown",
        source,
        {"applicable": None},
    )
    edges = (
        ContractEdge("back", "back-retry", "requires_behavior", "openapi", 1.0, source),
        ContractEdge(
            "back",
            "back-conflict",
            "requires_behavior",
            "openapi",
            1.0,
            source,
            "unknown",
        ),
    )

    findings = reconcile_contract_graph((frontend, backend, retry, unknown), edges)

    obligation_findings = [
        finding for finding in findings if "operation-obligation" in finding.detector_id
    ]
    assert [finding.detector_id for finding in obligation_findings] == [
        "contract-operation-obligation-evidence-unknown",
        "contract-operation-obligation-missing",
    ]
    unknown_finding, finding = obligation_findings
    assert unknown_finding.status == "investigate"
    assert unknown_finding.contract_anchor["field"] == "conflict"
    assert finding.status == "pending"
    assert finding.contract_anchor["field"] == "retry"
    assert finding.evidence["expected"] == ('{"applicable":true,"condition":"503"}')

    frontend_retry = ContractNode(
        "front-retry",
        "operation_obligation",
        "retry",
        "frontend",
        "present",
        source,
        {"applicable": True, "condition": "503"},
    )
    matched = reconcile_contract_graph(
        (frontend, backend, retry, unknown, frontend_retry),
        (
            *edges,
            ContractEdge(
                "front", "front-retry", "requires_behavior", "source", 1.0, source
            ),
        ),
    )
    matched_obligations = [
        finding for finding in matched if "operation-obligation" in finding.detector_id
    ]
    assert [finding.detector_id for finding in matched_obligations] == [
        "contract-operation-obligation-evidence-unknown"
    ]
    assert matched_obligations[0].status == "investigate"


def test_contradictory_operation_applicability_blocks_actionable_remediation() -> None:
    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)
    common = {
        "method": "POST",
        "normalized_path": "/orders",
        "dynamic": False,
        "status_codes": ["202"],
        "evidence": {},
    }
    frontend = ContractNode(
        "front",
        "client_operation",
        "POST /orders",
        "frontend",
        "present",
        source,
        common,
    )
    first = ContractNode(
        "back-a", "route", "POST /orders", "backend", "present", source, common
    )
    second = ContractNode(
        "back-b", "route", "POST /orders", "backend", "present", source, common
    )
    retry_true = ContractNode(
        "retry-a",
        "operation_obligation",
        "retry",
        "backend",
        "present",
        source,
        {"applicable": True, "condition": "503"},
    )
    retry_false = ContractNode(
        "retry-b",
        "operation_obligation",
        "retry",
        "backend",
        "absent",
        source,
        {"applicable": False},
    )

    findings = reconcile_contract_graph(
        (frontend, first, second, retry_true, retry_false),
        (
            ContractEdge("back-a", "retry-a", "requires_behavior", "a", 1.0, source),
            ContractEdge("back-b", "retry-b", "requires_behavior", "b", 1.0, source),
        ),
    )

    contradiction = next(
        finding
        for finding in findings
        if finding.detector_id == "contract-evidence-contradictory"
    )
    assert contradiction.status == "investigate"
    assert contradiction.contract_anchor["field"] == "operation_obligation"
    assert not [
        finding
        for finding in findings
        if finding.detector_id == "contract-operation-obligation-missing"
    ]
