from __future__ import annotations

import inspect
import json

from uidetox.contract_adapters import extract_backend_observations
from uidetox.frontend_map import FrontendMap, map_frontend
from uidetox.project_map import ProjectMap, build_project_map
from uidetox.prototype import build_prototype_brief
from uidetox.redesign import RedesignSet, propose_redesigns


def test_plan059_public_facade_signatures_are_frozen() -> None:
    assert {
        function.__name__: str(inspect.signature(function))
        for function in (
            extract_backend_observations,
            build_project_map,
            map_frontend,
            propose_redesigns,
            build_prototype_brief,
        )
    } == {
        "extract_backend_observations": (
            "(root: 'Path') -> 'tuple[list[ContractObservation], dict[str, Any]]'"
        ),
        "build_project_map": (
            "(root: 'str | Path', frontend_nodes: 'Iterable[Any]' = (), *, "
            "suppress_internal: 'bool' = True) -> 'ProjectMap'"
        ),
        "map_frontend": (
            "(root: 'str | Path', target: 'str | Path | None' = None, "
            "runtime: 'RuntimeObservation | None' = None) -> 'FrontendMap'"
        ),
        "propose_redesigns": (
            "(frontend_map: 'FrontendMap', brief: 'RedesignBrief | None' = None) "
            "-> 'RedesignSet'"
        ),
        "build_prototype_brief": (
            "(redesign_set: 'RedesignSet', proposal_id: 'str') -> 'str'"
        ),
    }


def test_plan059_legacy_artifact_loaders_keep_exact_contracts(tmp_path) -> None:
    project = ProjectMap.from_dict({})
    assert project.to_dict() == {
        "schema_version": 2,
        "nodes": [],
        "edges": [],
        "findings": [],
        "evidence": {},
    }

    frontend_payload = map_frontend(tmp_path).to_dict()
    frontend_payload.pop("project_map")
    loaded_frontend = FrontendMap.from_dict(frontend_payload)
    assert loaded_frontend.project_map == {}
    assert loaded_frontend.to_dict() == {**frontend_payload, "project_map": {}}

    for loader, expected_error in (
        (FrontendMap.from_dict, "Unsupported frontend map schema 0; expected 1."),
        (RedesignSet.from_dict, "Unsupported redesign schema 0; expected 2."),
    ):
        try:
            loader({})
        except ValueError as error:
            assert str(error) == expected_error
        else:  # pragma: no cover - contract guard
            raise AssertionError("legacy loader accepted an unsupported schema")


def test_plan059_openapi_wire_evidence_remains_distinct(tmp_path) -> None:
    document = {
        "openapi": "3.1.1",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "servers": [{"url": "https://api.example.test/v1"}],
        "components": {
            "securitySchemes": {
                "oauth": {
                    "type": "oauth2",
                    "flows": {
                        "clientCredentials": {
                            "tokenUrl": "/token",
                            "scopes": {"orders:write": "Write orders"},
                        }
                    },
                }
            }
        },
        "paths": {
            "/orders/{orderId}": {
                "post": {
                    "operationId": "replaceOrder",
                    "deprecated": True,
                    "security": [{"oauth": ["orders:write"]}, {}],
                    "parameters": [
                        {
                            "name": "orderId",
                            "in": "path",
                            "required": True,
                            "style": "simple",
                            "explode": False,
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "oneOf": [
                                        {"$ref": "#/components/schemas/OrderPatch"},
                                        {"type": "null"},
                                    ],
                                    "discriminator": {"propertyName": "kind"},
                                }
                            },
                            "application/merge-patch+json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": True,
                                }
                            },
                        },
                    },
                    "responses": {
                        "200": {
                            "headers": {"ETag": {"schema": {"type": "string"}}},
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Order"}
                                }
                            },
                        },
                        "409": {
                            "content": {
                                "application/problem+json": {
                                    "schema": {"$ref": "#/components/schemas/Problem"}
                                },
                                "text/plain": {"schema": {"type": "string"}},
                            }
                        },
                    },
                }
            }
        },
    }
    document["components"]["schemas"] = {
        "OrderPatch": {
            "type": "object",
            "unevaluatedProperties": False,
            "properties": {
                "kind": {"type": "string", "default": "standard"},
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "exclusiveMaximum": 100,
                    "writeOnly": True,
                },
            },
            "required": ["kind"],
        },
        "Order": {
            "allOf": [
                {"$ref": "#/components/schemas/OrderPatch"},
                {
                    "type": "object",
                    "properties": {"id": {"type": "string", "readOnly": True}},
                },
            ]
        },
        "Problem": {
            "type": "object",
            "properties": {"detail": {"type": "string", "maxLength": 400}},
        },
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")

    project = build_project_map(tmp_path)
    route = next(node for node in project.nodes if node.kind == "route")
    assert route.attributes["contract"] == {
        "deprecated": True,
        "json_schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        "openapi_version": "3.1.1",
        "operation_id": "replaceOrder",
        "servers": [{"url": "https://api.example.test/v1"}],
    }

    request_media = {
        node.name: node for node in project.nodes if node.kind == "request_media_type"
    }
    assert request_media["application/json"].attributes["required"] is True
    request_shape = request_media["application/json"].attributes["schema"]
    assert request_shape["discriminator"] == {"propertyName": "kind"}
    assert request_shape["oneOf"][0]["reference"] == ("#/components/schemas/OrderPatch")
    assert request_shape["oneOf"][0]["properties"]["quantity"] == {
        "exclusiveMaximum": 100,
        "minimum": 1,
        "type": "integer",
        "writeOnly": True,
    }
    assert request_media["application/merge-patch+json"].attributes["schema"] == {
        "additionalProperties": True,
        "type": "object",
    }

    response_media = {
        (node.attributes["status"], node.name): node
        for node in project.nodes
        if node.kind == "response_media_type"
    }
    assert (
        response_media[("200", "application/json")].attributes["schema"]["reference"]
        == "#/components/schemas/Order"
    )
    assert (
        response_media[("409", "application/problem+json")].attributes["schema"][
            "reference"
        ]
        == "#/components/schemas/Problem"
    )
    assert response_media[("409", "text/plain")].attributes["schema"] == {
        "type": "string"
    }

    oauth = next(
        node
        for node in project.nodes
        if node.kind == "auth_scheme_requirement" and node.name == "oauth"
    )
    assert oauth.attributes["scheme"] == {
        "flows": {
            "clientCredentials": {
                "scopes": {"orders:write": "Write orders"},
                "tokenUrl": "/token",
            }
        },
        "type": "oauth2",
    }


def test_plan059_openapi_caps_recursive_hostile_evidence_deterministically(
    tmp_path,
) -> None:
    properties = {f"field_{index:03d}": {"type": "string"} for index in range(130)}
    properties["child"] = {"$ref": "#/components/schemas/Node"}
    properties["<script>HOSTILE_DIAGNOSTIC</script>"] = {"type": "string"}
    document = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": properties,
                }
            }
        },
        "paths": {
            "/nodes": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                },
                                "application/octet-stream": {},
                            }
                        }
                    }
                }
            }
        },
    }

    def reversed_mappings(value):
        if isinstance(value, dict):
            return {
                key: reversed_mappings(item)
                for key, item in reversed(tuple(value.items()))
            }
        if isinstance(value, list):
            return [reversed_mappings(item) for item in value]
        return value

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "openapi.json").write_text(json.dumps(document), encoding="utf-8")
    (second_root / "openapi.json").write_text(
        json.dumps(reversed_mappings(document)), encoding="utf-8"
    )

    first = build_project_map(first_root)
    second = build_project_map(second_root)
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.findings == second.findings
    assert {
        key: value for key, value in first.evidence.items() if key != "source_manifest"
    } == {
        key: value for key, value in second.evidence.items() if key != "source_manifest"
    }

    media = {
        node.name: node for node in first.nodes if node.kind == "response_media_type"
    }
    schema = media["application/json"].attributes["schema"]
    assert schema["reference"] == "#/components/schemas/Node"
    assert schema["property_count"] == 132
    assert schema["truncated"] is True
    assert schema["capability_status"] == "unknown"
    assert schema["properties"]["child"] == {
        "capability_status": "unknown",
        "name": "Node",
        "reference": "#/components/schemas/Node",
        "type": "recursive",
    }
    assert "schema" not in media["application/octet-stream"].attributes
    assert all(
        "HOSTILE_DIAGNOSTIC" not in finding.message for finding in first.findings
    )
