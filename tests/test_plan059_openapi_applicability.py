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


def test_openapi_response_link_overflow_emits_bounded_unknown_diagnostic(
    tmp_path,
) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "get": {
                    "responses": {
                        "200": {
                            "links": {
                                f"link-{index:02d}": {
                                    "operationId": f"operation{index}"
                                }
                                for index in range(33)
                            }
                        }
                    }
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)

    assert len(_nodes(project, "response_link")) == 32
    diagnostic = _nodes(project, "contract_evidence_limit")[0]
    assert diagnostic.capability_status == "unknown"
    assert diagnostic.attributes == {
        "axis": "response_links",
        "capability_status": "unknown",
        "edge": "documents",
        "limit": 32,
        "observed_count": 33,
        "provenance": "openapi:response-link",
        "status": "200",
        "truncated": True,
    }


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


def test_openapi_operation_aggregate_budget_bounds_hostile_evidence(tmp_path) -> None:
    oversized = "x" * 1_000_000
    nested: dict[str, object] = {"type": "string"}
    for depth in range(5):
        nested = {
            "type": "object",
            "properties": {f"field-{depth}-{index}": nested for index in range(8)},
        }
    document = {
        "openapi": "3.1.0",
        "jsonSchemaDialect": oversized,
        "servers": [{"url": oversized}],
        "paths": {
            "/hostile": {
                "get": {
                    "operationId": oversized,
                    "callbacks": {oversized: {}},
                    "parameters": [
                        {"in": "query", "name": oversized, "schema": nested}
                    ],
                    "responses": {
                        "200": {
                            "headers": {oversized: {"schema": nested}},
                            "content": {oversized: {"schema": nested}},
                        }
                    },
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    serialized = json.dumps(project.to_dict())

    assert len(serialized) < 500_000
    assert max((len(node.name) for node in project.nodes), default=0) <= 4096
    diagnostics = _nodes(project, "contract_evidence_limit")
    assert diagnostics
    assert all(node.capability_status == "unknown" for node in diagnostics)
    assert any(
        node.attributes.get("axis") == "operation_transport" for node in diagnostics
    )
    assert any(
        node.attributes.get("axis") == "schema"
        for node in diagnostics
        + [node for node in project.nodes if node.capability_status == "unknown"]
    )


def test_boolean_only_obligations_require_operation_specific_evidence(
    tmp_path,
) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/orders": {
                "post": {
                    "x-uidetox-operation": {
                        "retry": True,
                        "idempotency": True,
                        "affected-reads": True,
                    },
                    "responses": {"202": {"description": "accepted"}},
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    obligations = _nodes(project, "operation_obligation")

    assert {node.name for node in obligations} == {
        "affected-reads",
        "idempotency",
        "retry",
    }
    assert {node.capability_status for node in obligations} == {"unknown"}
    assert all(node.attributes["applicable"] is None for node in obligations)
    assert {
        node.name: tuple(node.attributes["missing_constraints"]) for node in obligations
    } == {
        "affected-reads": ("operations",),
        "idempotency": ("scope",),
        "retry": ("condition",),
    }


def test_schema_names_and_discriminator_are_bounded_and_fail_closed(tmp_path) -> None:
    oversized = "x" * 1_000_000
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/oversized": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": [oversized],
                                    "properties": {oversized: {"type": "string"}},
                                    "discriminator": {"propertyName": oversized},
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
    shape = _nodes(project, "request_media_type")[0].attributes["schema"]

    assert shape["required"] == []
    assert shape["properties"] == {}
    assert shape["discriminator"] == {"propertyName": ""}
    assert shape["truncated"] is True
    assert shape["capability_status"] == "unknown"
    assert len(json.dumps(project.to_dict())) < 100_000


def test_nested_items_truncation_survives_graph_reconciliation(tmp_path) -> None:
    properties = {f"field_{index:03d}": {"type": "string"} for index in range(129)}
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": properties,
                                        },
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
    backend = _nodes(project, "route")[0]
    backend_schema = next(
        node for node in _nodes(project, "response_schema") if node.side == "backend"
    )
    frontend = ContractNode(
        "front",
        "client_operation",
        backend.name,
        "frontend",
        "present",
        backend.source,
        dict(backend.attributes),
    )
    frontend_schema = ContractNode(
        "front-schema",
        "response_schema",
        "response:200",
        "frontend",
        "present",
        backend.source,
        {"type": "array", "status": "200"},
    )
    findings = reconcile_contract_graph(
        (frontend, frontend_schema, backend, backend_schema),
        (
            ContractEdge(
                "front", "front-schema", "returns", "test", 1.0, backend.source
            ),
            ContractEdge(
                backend.id,
                backend_schema.id,
                "returns",
                "openapi",
                1.0,
                backend.source,
            ),
        ),
    )

    assert backend_schema.capability_status == "unknown"
    assert any(
        finding.detector_id == "contract-response-schema-evidence-unknown"
        and finding.status == "investigate"
        for finding in findings
    )


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


def test_duplicate_operation_status_subsets_are_contradictory_in_both_orders() -> None:
    from uidetox.contract_graph import _contract_group_contradiction

    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)

    def operation(identifier: str, statuses: list[str]) -> ContractNode:
        return ContractNode(
            identifier,
            "route",
            "POST /orders",
            "backend",
            "present",
            source,
            {
                "method": "POST",
                "normalized_path": "/orders",
                "status_codes": statuses,
                "evidence": {"status": "present"},
            },
        )

    narrow = operation("narrow", ["200"])
    broad = operation("broad", ["200", "202"])

    assert _contract_group_contradiction((narrow, broad), {}) == "status"
    assert _contract_group_contradiction((broad, narrow), {}) == "status"


def test_native_openapi_evidence_derives_only_proven_operation_obligations(
    tmp_path,
) -> None:
    document = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {"OAuth": {"type": "http", "scheme": "bearer"}}
        },
        "paths": {
            "/orders": {
                "get": {
                    "security": [{"OAuth": []}],
                    "responses": {
                        "200": {"headers": {"ETag": {"schema": {"type": "string"}}}},
                        "403": {},
                        "429": {
                            "headers": {"Retry-After": {"schema": {"type": "integer"}}}
                        },
                    },
                }
            },
            "/orders/{orderId}": {
                "patch": {
                    "parameters": [
                        {"in": "path", "name": "orderId", "required": True},
                        {"in": "header", "name": "If-Match", "required": True},
                        {
                            "in": "header",
                            "name": "Idempotency-Key",
                            "required": True,
                        },
                    ],
                    "responses": {"207": {}, "412": {}, "422": {}},
                }
            },
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    obligations = {
        (node.name, node.attributes.get("condition"), node.attributes.get("scope"))
        for node in _nodes(project, "operation_obligation")
        if node.capability_status == "present"
    }

    assert {
        "auth-required",
        "forbidden",
        "rate-limit",
        "retry",
        "stale-refresh",
    } <= {name for name, _condition, _scope in obligations}
    assert {
        "conflict",
        "duplicate-submit",
        "idempotency",
        "partial-success",
        "validation",
    } <= {name for name, _condition, _scope in obligations}
    assert ("retry", "safe-method", None) in obligations
    assert ("retry", "idempotency-key", None) in obligations
    assert ("idempotency", None, "request-header:Idempotency-Key") in obligations
    assert {
        node.attributes["provenance"]
        for node in _nodes(project, "operation_obligation")
    } == {"openapi:native-operation"}


def test_duplicate_transport_evidence_is_contradictory_in_both_orders() -> None:
    from uidetox.contract_graph import _contract_group_contradiction

    source = SourceAnchor("openapi.json", 1, "test", "test", 1.0)

    def operation(identifier: str) -> ContractNode:
        return ContractNode(
            identifier,
            "route",
            "GET /orders",
            "backend",
            "present",
            source,
            {
                "method": "GET",
                "normalized_path": "/orders",
                "status_codes": ["200"],
                "evidence": {"response": "present", "status": "present"},
            },
        )

    def media(identifier: str, name: str) -> ContractNode:
        return ContractNode(
            identifier,
            "response_media_type",
            name,
            "backend",
            "present",
            source,
            {"status": "200", "schema": {"type": "object"}},
        )

    left, right = operation("left"), operation("right")
    outgoing = {
        ("left", "returns_media_type"): [media("json", "application/json")],
        ("right", "returns_media_type"): [media("cbor", "application/cbor")],
    }

    assert _contract_group_contradiction((left, right), outgoing) == (
        "response_media_type"
    )
    assert _contract_group_contradiction((right, left), outgoing) == (
        "response_media_type"
    )


def test_richer_duplicate_backend_evidence_is_selected_order_independently() -> None:
    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)

    def operation(identifier: str, side: str) -> ContractNode:
        return ContractNode(
            identifier,
            "client_operation" if side == "frontend" else "route",
            "GET /orders",
            side,
            "present",
            source,
            {
                "method": "GET",
                "normalized_path": "/orders",
                "status_codes": ["200"],
                "evidence": {
                    "request": "absent",
                    "response": "absent",
                    "error": "absent",
                    "status": "present",
                },
            },
        )

    def parameter(identifier: str, side: str) -> ContractNode:
        return ContractNode(
            identifier,
            "api_parameter",
            "ids",
            side,
            "present",
            source,
            {"location": "query", "style": "form", "explode": False},
        )

    frontend = operation("frontend", "frontend")
    coarse = operation("coarse", "backend")
    rich = operation("rich", "backend")
    front_parameter = parameter("front-ids", "frontend")
    back_parameter = parameter("back-ids", "backend")
    edges = (
        ContractEdge(
            frontend.id,
            front_parameter.id,
            "declares_parameter",
            "test",
            1.0,
            source,
        ),
        ContractEdge(
            rich.id,
            back_parameter.id,
            "declares_parameter",
            "test",
            1.0,
            source,
        ),
    )

    for backends in ((coarse, rich), (rich, coarse)):
        findings = reconcile_contract_graph(
            (frontend, *backends, front_parameter, back_parameter), edges
        )
        assert not [finding for finding in findings if finding.status == "pending"]


def test_swagger_2_body_and_media_transport_survive_projection(tmp_path) -> None:
    document = {
        "swagger": "2.0",
        "consumes": ["application/json"],
        "produces": ["application/problem+json"],
        "paths": {
            "/items": {
                "post": {
                    "parameters": [
                        {
                            "in": "body",
                            "name": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {"name": {"type": "string"}},
                            },
                        }
                    ],
                    "responses": {
                        "201": {
                            "schema": {
                                "type": "object",
                                "properties": {"id": {"type": "integer"}},
                            }
                        }
                    },
                }
            }
        },
    }
    (tmp_path / "swagger.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    route = _nodes(project, "route")[0]

    assert route.attributes["evidence"]["request"] == "present"
    assert route.attributes["evidence"]["response"] == "present"
    assert {node.name for node in _nodes(project, "request_media_type")} == {
        "application/json"
    }
    response_media = _nodes(project, "response_media_type")
    assert {(node.name, node.attributes["status"]) for node in response_media} == {
        ("application/problem+json", "201")
    }
    body = next(
        node
        for node in _nodes(project, "api_parameter")
        if node.attributes["location"] == "body"
    )
    assert body.attributes["required"] is True
    assert body.attributes["schema"]["type"] == "object"


def test_retry_after_without_429_does_not_prove_rate_limit(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/health": {
                "get": {
                    "responses": {
                        "200": {"description": "ok"},
                        "503": {
                            "description": "maintenance",
                            "headers": {"Retry-After": {"schema": {"type": "integer"}}},
                        },
                    }
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    obligations = _nodes(build_project_map(tmp_path), "operation_obligation")
    assert {node.name for node in obligations} == {"retry"}


def test_operation_contract_overflow_emits_fail_closed_diagnostic(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "get": {
                    "servers": [
                        {"url": f"https://server-{index}.example"}
                        for index in range(33)
                    ],
                    "callbacks": {f"callback-{index}": {} for index in range(33)},
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    diagnostics = _nodes(build_project_map(tmp_path), "contract_evidence_limit")
    assert diagnostics
    assert any(
        node.attributes.get("axis") == "operation_transport"
        and node.capability_status == "unknown"
        for node in diagnostics
    )


def test_cache_remediation_requires_exact_affected_read_applicability() -> None:
    from uidetox.contract_graph import _first_contract_difference

    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)
    base = {
        "method": "POST",
        "normalized_path": "/orders",
        "status_codes": ["204"],
        "ui_required": False,
        "cache_invalidation": "absent",
        "evidence": {
            "request": "absent",
            "response": "absent",
            "error": "absent",
            "status": "present",
            "ui_lifecycle": "absent",
            "cache": "absent",
        },
    }
    frontend = ContractNode(
        "frontend",
        "client_operation",
        "POST /orders",
        "frontend",
        "present",
        source,
        {**base, "mutation": True},
    )
    backend = ContractNode(
        "backend",
        "route",
        "POST /orders",
        "backend",
        "present",
        source,
        {**base, "mutation": False},
    )
    frontend_auth = ContractNode(
        "frontend-auth",
        "auth_requirement",
        "auth",
        "frontend",
        "absent",
        source,
        {"authorization": "absent", "tenant": "absent"},
    )
    backend_auth = ContractNode(
        "backend-auth",
        "auth_requirement",
        "auth",
        "backend",
        "absent",
        source,
        {"authorization": "absent", "tenant": "absent"},
    )
    outgoing = {
        (frontend.id, "requires"): [frontend_auth],
        (backend.id, "requires"): [backend_auth],
    }

    assert _first_contract_difference(frontend, backend, outgoing) is None

    affected_reads = ContractNode(
        "affected-reads",
        "operation_obligation",
        "affected-reads",
        "backend",
        "present",
        source,
        {"applicable": True, "operations": ["GET /orders"]},
    )
    outgoing[(backend.id, "requires_behavior")] = [affected_reads]
    difference = _first_contract_difference(frontend, backend, outgoing)
    assert difference is not None
    assert difference[0] == "cache_invalidation_missing"
