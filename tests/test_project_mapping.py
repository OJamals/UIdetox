from __future__ import annotations

import json
from pathlib import Path

import pytest

from uidetox.frontend_map import FrontendMap, map_frontend
from uidetox.project_map import (
    ContractEdge,
    ContractNode,
    ProjectMap,
    SourceAnchor,
    build_project_map,
    normalize_route_path,
    reconcile_contract_graph,
)
from uidetox.prototype import build_prototype_brief
from uidetox.redesign import RedesignBrief, propose_redesigns


def _frontend_node(
    path: str,
    method: str | None = "GET",
    *,
    line: int = 1,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "transport": "http",
        "extractor": "test",
        "confidence": 1.0,
    }
    if method is not None:
        metadata["method"] = method
    return {
        "kind": "data",
        "name": path,
        "file": "src/client.ts",
        "line": line,
        "metadata": metadata,
    }


def _operation_nodes(project: ProjectMap, side: str) -> tuple[ContractNode, ...]:
    kind = "client_operation" if side == "frontend" else "route"
    return tuple(
        node for node in project.nodes if node.side == side and node.kind == kind
    )


def test_route_normalization_preserves_identity_but_compares_shapes() -> None:
    colon = normalize_route_path("/users/:userId")
    brace = normalize_route_path("/users/{id}")
    bracket = normalize_route_path("/users/[account]")
    flask = normalize_route_path("/users/<int:member>")

    assert {item[0] for item in (colon, brace, bracket, flask)} == {"/users/{}"}
    assert [item[1] for item in (colon, brace, bracket, flask)] == [
        ("userId",),
        ("id",),
        ("account",),
        ("member",),
    ]
    assert (
        normalize_route_path("https://example.test/api/items?page=1")[0] == "/api/items"
    )
    assert normalize_route_path("/experiments/${experiment.key}") == (
        "/experiments/{}",
        ("experiment.key",),
        False,
    )


def test_openapi_json_yaml_preserve_schema_source_identity(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/users/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {"schemas": {"User": {"type": "object"}}},
    }
    (tmp_path / "openapi.json").write_text(json.dumps(document), encoding="utf-8")
    (tmp_path / "swagger.yaml").write_text(
        """
openapi: 3.0.0
paths:
  /users/:userId:
    get:
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/User"
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(
        tmp_path,
        [_frontend_node("/users/${id}", "GET")],
    )

    backend = _operation_nodes(project, "backend")
    assert len(backend) == 2
    assert {
        (node.source.file, tuple(node.attributes["parameters"]))
        for node in backend
    } == {
        ("openapi.json", ("id",)),
        ("swagger.yaml", ("userId",)),
    }
    assert all(node.attributes["normalized_path"] == "/users/{}" for node in backend)
    assert any(
        node.kind == "response_schema" and node.name == "User"
        for node in project.nodes
    )
    assert project.counts == {"contract_mismatch": 0, "coverage_gap": 1}


def test_fastapi_and_flask_decorator_adapters(tmp_path) -> None:
    (tmp_path / "fastapi_app.py").write_text(
        """
from fastapi import APIRouter, FastAPI
app = FastAPI()

router = APIRouter(prefix="/api")

@router.get("/widgets/{widget_id}")
def widget():
    pass
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "flask_app.py").write_text(
        """
from flask import Blueprint, Flask
app = Flask(__name__)
bp = Blueprint("widgets", __name__, url_prefix="/flask-api")

@bp.route("/widgets", methods=["POST", "PUT"])
def widgets():
    pass
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    observed = {
        (
            item.attributes["method"],
            item.attributes["normalized_path"],
            item.source.framework,
        )
        for item in _operation_nodes(project, "backend")
    }

    assert ("GET", "/api/widgets/{}", "fastapi") in observed
    assert ("POST", "/flask-api/widgets", "flask") in observed
    assert ("PUT", "/flask-api/widgets", "flask") in observed
    assert project.evidence["adapters"] == ["fastapi", "flask"]


def test_express_fastify_and_nest_adapters(tmp_path) -> None:
    (tmp_path / "express.ts").write_text(
        """
import express from "express";
const router = express.Router();
app.use("/express-api", router);
router.post("/orders/:orderId", handler);
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "fastify.ts").write_text(
        """
import Fastify from "fastify";
const fastify = Fastify();
fastify.register(routes, { prefix: "/fast-api" });
fastify.route({ method: "PATCH", url: "/orders/:orderId", handler });
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "orders.controller.ts").write_text(
        """
@Controller("orders")
export class OrdersController {
  @Delete(":orderId")
  remove() {}
}
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    observed = {
        (
            item.attributes["method"],
            item.attributes["normalized_path"],
            item.source.framework,
        )
        for item in _operation_nodes(project, "backend")
    }

    assert ("POST", "/express-api/orders/{}", "express") in observed
    assert ("PATCH", "/fast-api/orders/{}", "fastify") in observed
    assert ("DELETE", "/orders/{}", "nest") in observed
    assert project.evidence["adapters"] == ["express", "fastify", "nest"]


def test_unknown_route_syntax_is_unresolved_not_false_match(tmp_path) -> None:
    (tmp_path / "unknown.ts").write_text(
        'mystery.endpoint("/users", handler);',
        encoding="utf-8",
    )
    project = build_project_map(tmp_path, [_frontend_node("/users", "GET")])

    assert _operation_nodes(project, "backend") == ()
    assert project.counts == {"contract_mismatch": 1, "coverage_gap": 0}

    (tmp_path / "unknown.ts").write_text(
        "mystery.route(dynamicPath, handler);",
        encoding="utf-8",
    )
    project = build_project_map(tmp_path, [_frontend_node("/users", "GET")])
    backend = _operation_nodes(project, "backend")
    assert len(backend) == 1
    assert backend[0].attributes["dynamic"] is True
    assert project.counts == {"contract_mismatch": 1, "coverage_gap": 1}


def test_backend_discovery_ignores_route_syntax_in_test_sources(tmp_path) -> None:
    browser_test = tmp_path / "frontend" / "tests" / "app.spec.ts"
    browser_test.parent.mkdir(parents=True)
    browser_test.write_text(
        'test("contract", async ({ page }) => { await page.route("**/api/items", handler); });',
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)

    assert _operation_nodes(project, "backend") == ()
    assert project.evidence["backend_files_scanned"] == 0
    assert project.evidence["unknown_backend_evidence"] == 0


def test_unknown_router_receivers_are_not_guessed_as_supported_frameworks(
    tmp_path,
) -> None:
    (tmp_path / "custom.py").write_text(
        """
from custom_framework import Router
router = Router()

@router.get("/users")
def users():
    pass
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "koa.ts").write_text(
        """
import Router from "koa-router";
const router = new Router();
router.get("/orders", handler);
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)

    assert project.evidence["adapters"] == []
    assert project.evidence["unknown_backend_evidence"] == 2
    backend = _operation_nodes(project, "backend")
    assert all(item.attributes["dynamic"] for item in backend)
    assert all(item.attributes["classification"] == "unknown" for item in backend)
    assert project.counts == {"contract_mismatch": 0, "coverage_gap": 2}


def test_framework_imports_do_not_promote_unrelated_route_receivers(
    tmp_path,
) -> None:
    (tmp_path / "mixed.py").write_text(
        """
from fastapi import FastAPI
app = FastAPI()
cache = Cache()

@app.get("/real-python")
def real():
    pass

@cache.get("/python-cache")
def cached():
    pass
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "mixed.ts").write_text(
        """
import express from "express";
const app = express();
const cache = new Cache();

app.get("/real-js", handler);
cache.get("/js-cache", handler);
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    backend = _operation_nodes(project, "backend")
    comparable = {
        (
            item.attributes["method"],
            item.attributes["normalized_path"],
            item.source.framework,
        )
        for item in backend
        if item.attributes["classification"] != "unknown"
    }
    unresolved = {
        item.attributes["normalized_path"]
        for item in backend
        if item.attributes["classification"] == "unknown"
    }

    assert comparable == {
        ("GET", "/real-js", "express"),
        ("GET", "/real-python", "fastapi"),
    }
    assert unresolved == {"/js-cache", "/python-cache"}
    assert project.evidence["unknown_backend_evidence"] == 2


def test_framework_factory_aliases_require_verified_import_provenance(
    tmp_path,
) -> None:
    (tmp_path / "real.py").write_text(
        """
from fastapi import FastAPI as MakeAPI
api = MakeAPI()

@api.get("/real-python")
def real():
    pass
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "fake.py").write_text(
        """
from custom import FastAPI
api = FastAPI()

@api.get("/fake-python")
def fake():
    pass
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "real.ts").write_text(
        """
import makeExpress, { Router as ExpressRouter } from "express";
const app = makeExpress();
const router = ExpressRouter();
app.get("/real-js", handler);
router.post("/real-router", handler);
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "fake.ts").write_text(
        """
import { Router } from "itty-router";
function express() { return localFramework; }
const router = Router();
const app = express();
router.get("/fake-router", handler);
app.get("/fake-express", handler);
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    backend = _operation_nodes(project, "backend")
    comparable = {
        (
            item.attributes["method"],
            item.attributes["normalized_path"],
            item.source.framework,
        )
        for item in backend
        if item.attributes["classification"] != "unknown"
    }
    unresolved = {
        item.attributes["normalized_path"]
        for item in backend
        if item.attributes["classification"] == "unknown"
    }

    assert comparable == {
        ("GET", "/real-js", "express"),
        ("GET", "/real-python", "fastapi"),
        ("POST", "/real-router", "express"),
    }
    assert unresolved == {"/fake-express", "/fake-python", "/fake-router"}


def test_framework_import_provenance_ignores_comments_and_strings(
    tmp_path,
) -> None:
    (tmp_path / "fake.py").write_text(
        '''
"""
from fastapi import FastAPI
"""
class FastAPI:
    pass
api = FastAPI()

@api.get("/fake-python")
def fake():
    pass
'''.strip(),
        encoding="utf-8",
    )
    (tmp_path / "fake.ts").write_text(
        """
// import express from "express";
const documentation = 'import express from "express"';
function express() { return localFramework; }
const app = express();
app.get("/fake-js", handler);
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    backend = _operation_nodes(project, "backend")

    assert all(item.attributes["classification"] == "unknown" for item in backend)
    assert {item.attributes["normalized_path"] for item in backend} == {
        "/fake-js",
        "/fake-python",
    }
    assert project.evidence["adapters"] == []


def test_project_map_roundtrip_and_serialization_are_deterministic(tmp_path) -> None:
    (tmp_path / "api.ts").write_text(
        'app.get("/b", handler);\napp.get("/a", handler);',
        encoding="utf-8",
    )

    first = build_project_map(
        tmp_path,
        [_frontend_node("/b"), _frontend_node("/a", line=2)],
    )
    second = build_project_map(
        tmp_path,
        [_frontend_node("/b"), _frontend_node("/a", line=2)],
    )

    assert first.to_dict() == second.to_dict()
    assert ProjectMap.from_dict(first.to_dict()) == first
    assert ProjectMap.from_dict(None) == ProjectMap()


def test_frontend_map_redesign_and_prototype_consume_parity_additively(
    tmp_path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "App.tsx").write_text(
        """
export function App() {
  axios.post("/api/users/:userId");
  return <main />;
}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "api.ts").write_text(
        """
import express from "express";
const app = express();
app.get("/api/users/:id", handler);
""".strip(),
        encoding="utf-8",
    )

    frontend_map = map_frontend(tmp_path, "src")
    project = ProjectMap.from_dict(frontend_map.project_map)
    redesign = propose_redesigns(frontend_map, RedesignBrief(variants=1))
    brief = build_prototype_brief(redesign, redesign.proposals[0].id)

    assert project.counts == {"contract_mismatch": 1, "coverage_gap": 0}
    assert redesign.contract_lineage["counts"] == project.counts
    assert "Full-stack contract lineage findings:" in brief
    assert "method_mismatch: /api/users/{}" in brief

    legacy = frontend_map.to_dict()
    legacy.pop("project_map")
    loaded_legacy = FrontendMap.from_dict(legacy)
    assert loaded_legacy.project_map == {}
    assert set(legacy) == {
        "schema_version",
        "generated_at",
        "root",
        "target",
        "nodes",
        "edges",
        "contracts",
        "fingerprint",
        "evidence",
    }


def test_fullstack_fixture_preserves_sources_and_causal_findings() -> None:
    fixture = (
        Path(__file__).parents[1] / "examples" / "fullstack-slop-lab"
    )

    frontend_map = map_frontend(fixture, ".")
    project = ProjectMap.from_dict(frontend_map.project_map)

    assert project.counts == {"contract_mismatch": 0, "coverage_gap": 52}
    assert project.evidence["unknown_backend_evidence"] == 0
    assert len(_operation_nodes(project, "frontend")) == 57
    assert len(_operation_nodes(project, "backend")) == 58
    assert sum(
        finding.detector_id == "contract-evidence-contradictory"
        for finding in project.findings
    ) == 4


def test_frontend_map_preserves_same_path_requests_by_method(tmp_path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "client.ts").write_text(
        """
fetch("/same");
axios.post("/same");
""".strip(),
        encoding="utf-8",
    )
    (source / "api.ts").write_text(
        """
import express from "express";
const app = express();
app.get("/same", getHandler);
app.post("/same", postHandler);
""".strip(),
        encoding="utf-8",
    )

    frontend_map = map_frontend(tmp_path, "src")
    operations = _operation_nodes(
        ProjectMap.from_dict(frontend_map.project_map), "frontend"
    )

    assert [
        (item.attributes["method"], item.attributes["normalized_path"])
        for item in operations
    ] == [
        ("GET", "/same"),
        ("POST", "/same"),
    ]
    assert len({node.id for node in frontend_map.nodes}) == len(frontend_map.nodes)


def test_contract_graph_v2_roundtrip_and_legacy_migration_distinguish_unknown() -> None:
    node = ContractNode(
        id="client:POST:/users",
        kind="client_operation",
        name="POST /users",
        side="frontend",
        capability_status="unknown",
        source=SourceAnchor("src/client.ts", 8, "react", "tree-sitter", 1.0),
        attributes={"method": "POST", "normalized_path": "/users"},
    )
    graph = ProjectMap(nodes=(node,))

    payload = graph.to_dict()
    assert payload["schema_version"] == 2
    assert set(payload) == {"schema_version", "nodes", "edges", "findings", "evidence"}
    assert ProjectMap.from_dict(payload) == graph

    legacy = {
        "schema_version": 1,
        "frontend_operations": [
            {
                "side": "frontend",
                "method": "POST",
                "path": "/users",
                "normalized_path": "/users",
                "parameters": [],
                "schemas": [],
                "dynamic": False,
                "classification": "application",
                "sources": [],
            }
        ],
        "backend_operations": [],
        "findings": [],
        "evidence": {},
    }
    migrated = ProjectMap.from_dict(legacy)
    assert migrated.schema_version == 2
    assert migrated.nodes[0].capability_status == "unknown"
    assert migrated.to_dict()["schema_version"] == 2


def test_contract_reconciliation_reports_one_smallest_field_mismatch() -> None:
    source = SourceAnchor("contract.ts", 1, "test", "test", 1.0)
    common = {
        "method": "POST",
        "normalized_path": "/users",
        "status_codes": ["201"],
        "mutation": True,
        "cache_invalidation": "present",
    }
    frontend = ContractNode(
        "client:POST:/users",
        "client_operation",
        "POST /users",
        "frontend",
        "present",
        source,
        common,
    )
    backend = ContractNode(
        "route:POST:/users",
        "route",
        "POST /users",
        "backend",
        "present",
        source,
        common,
    )
    front_schema = ContractNode(
        "front-request",
        "request_schema",
        "CreateUser",
        "frontend",
        "present",
        source,
        {"type": "object"},
    )
    back_schema = ContractNode(
        "back-request",
        "request_schema",
        "CreateUser",
        "backend",
        "present",
        source,
        {"type": "object"},
    )
    front_email = ContractNode(
        "front-email",
        "schema_field",
        "email",
        "frontend",
        "present",
        source,
        {"type": "string", "required": True},
    )
    back_email = ContractNode(
        "back-email",
        "schema_field",
        "email",
        "backend",
        "present",
        source,
        {"type": "integer", "required": True},
    )
    edges = (
        ContractEdge(frontend.id, front_schema.id, "accepts", "test", 1.0, source),
        ContractEdge(backend.id, back_schema.id, "accepts", "test", 1.0, source),
        ContractEdge(
            front_schema.id, front_email.id, "has_field", "test", 1.0, source
        ),
        ContractEdge(
            back_schema.id, back_email.id, "has_field", "test", 1.0, source
        ),
    )

    findings = reconcile_contract_graph(
        (frontend, backend, front_schema, back_schema, front_email, back_email),
        edges,
    )

    assert [finding.detector_id for finding in findings] == [
        "contract-request-field-type-mismatch"
    ]
    assert findings[0].contract_anchor["field"] == "email"
    assert findings[0].source_anchor["path"] == "contract.ts"


def test_unknown_contract_evidence_never_reports_parity() -> None:
    source = SourceAnchor("client.ts", 1, "test", "test", 1.0)
    frontend = ContractNode(
        "client:GET:/users",
        "client_operation",
        "GET /users",
        "frontend",
        "unknown",
        source,
        {"method": "GET", "normalized_path": "/users"},
    )
    backend = ContractNode(
        "route:GET:/users",
        "route",
        "GET /users",
        "backend",
        "present",
        source,
        {
            "method": "GET",
            "normalized_path": "/users",
            "response_schema": {"type": "array", "items": {"type": "string"}},
        },
    )

    findings = reconcile_contract_graph((frontend, backend), ())

    assert len(findings) == 1
    assert findings[0].detector_id == "contract-evidence-unknown"
    assert findings[0].status == "investigate"


def test_openapi_contract_fields_status_errors_and_auth_are_graph_nodes(tmp_path) -> None:
    document = {
        "openapi": "3.1.0",
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "UserCreate": {
                    "type": "object",
                    "required": ["email", "role"],
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "role": {"type": "string", "enum": ["admin", "member"]},
                    },
                },
                "User": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "nickname": {"type": ["string", "null"]},
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["detail"],
                    "properties": {"detail": {"type": "string"}},
                },
            },
        },
        "paths": {
            "/users": {
                "post": {
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/UserCreate"}
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/User"}
                                }
                            }
                        },
                        "422": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
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
    kinds = {node.kind for node in project.nodes}
    names = {node.name for node in project.nodes}

    assert {"route", "request_schema", "response_schema", "error_schema"} <= kinds
    assert {"email", "role", "id", "nickname", "BearerAuth"} <= names
    route = next(node for node in project.nodes if node.kind == "route")
    assert route.attributes["status_codes"] == ["201", "422"]
    auth = next(node for node in project.nodes if node.kind == "auth_requirement")
    assert auth.capability_status == "present"


def test_fastapi_handler_service_entity_and_column_lineage(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

app = FastAPI()

class Input(BaseModel):
    email: str

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)

def require_user():
    return object()

def create_user(payload: Input):
    return User(email=payload.email)

@app.post("/users", response_model=Input, status_code=201)
def post_user(payload: Input, user=Depends(require_user)):
    return create_user(payload)
""".strip(),
        encoding="utf-8",
    )

    project = build_project_map(tmp_path)
    route = next(node for node in project.nodes if node.kind == "route")
    node_by_id = {node.id: node for node in project.nodes}
    reachable = {
        edge.target
        for edge in project.edges
        if node_by_id[edge.source].kind
        in {"route", "handler", "service_operation", "entity"}
    }

    assert any(node_by_id[node_id].kind == "handler" for node_id in reachable)
    assert any(node_by_id[node_id].kind == "service_operation" for node_id in reachable)
    assert any(node_by_id[node_id].kind == "entity" for node_id in reachable)
    assert {"id", "email"} <= {
        node.name for node in project.nodes if node.kind == "database_field"
    }
    assert any(
        edge.source == route.id
        and edge.kind == "requires"
        and node_by_id[edge.target].capability_status == "unknown"
        for edge in project.edges
    )


def test_repair_preserves_same_route_source_identity_and_action_schema_links(
    tmp_path,
) -> None:
    frontend = [
        {
            "id": "data:create-a",
            "kind": "data",
            "name": "/users",
            "file": "src/a.ts",
            "line": 10,
            "metadata": {
                "transport": "http",
                "method": "POST",
                "request_contracts": {
                    "CreateA": {
                        "type": "object",
                        "properties": {"a": {"type": "string"}},
                        "required": ["a"],
                    }
                },
                "ui_actions": ["Create A"],
                "extractor": "test",
                "confidence": 1.0,
            },
        },
        {
            "id": "data:create-b",
            "kind": "data",
            "name": "/users",
            "file": "src/b.ts",
            "line": 20,
            "metadata": {
                "transport": "http",
                "method": "POST",
                "request_contracts": {
                    "CreateB": {
                        "type": "object",
                        "properties": {"b": {"type": "integer"}},
                        "required": ["b"],
                    }
                },
                "ui_actions": ["Create B"],
                "extractor": "test",
                "confidence": 1.0,
            },
        },
    ]

    graph = build_project_map(tmp_path, frontend)
    clients = _operation_nodes(graph, "frontend")
    node_by_id = {node.id: node for node in graph.nodes}
    outgoing = {
        (edge.source, edge.kind): node_by_id[edge.target] for edge in graph.edges
    }

    assert len(clients) == 2
    by_file = {client.source.file: client for client in clients}
    a_schema = outgoing[(by_file["src/a.ts"].id, "accepts")]
    b_schema = outgoing[(by_file["src/b.ts"].id, "accepts")]
    assert {
        node_by_id[edge.target].name
        for edge in graph.edges
        if edge.source == a_schema.id and edge.kind == "has_field"
    } == {"a"}
    assert {
        node_by_id[edge.target].name
        for edge in graph.edges
        if edge.source == b_schema.id and edge.kind == "has_field"
    } == {"b"}
    triggers = {
        (node_by_id[edge.source].name, node_by_id[edge.target].source.file)
        for edge in graph.edges
        if edge.kind == "triggers"
    }
    assert triggers == {("Create A", "src/a.ts"), ("Create B", "src/b.ts")}


def _repair_contract_graph(
    *,
    front_schema: dict | None = None,
    back_schema: dict | None = None,
    front_evidence: dict[str, str] | None = None,
    back_evidence: dict[str, str] | None = None,
    front_auth: tuple[str, str, str] = ("absent", "absent", "absent"),
    back_auth: tuple[str, str, str] = ("absent", "absent", "absent"),
    front_statuses: tuple[str, ...] = (),
    back_statuses: tuple[str, ...] = (),
    front_states: tuple[str, ...] = ("loading", "error", "empty", "success"),
    front_cache: str = "absent",
    mutation: bool = False,
    front_capability: str = "present",
    back_capability: str = "present",
    front_errors: tuple[tuple[str, dict], ...] = (),
    back_errors: tuple[tuple[str, dict], ...] = (),
) -> tuple[tuple[ContractNode, ...], tuple[ContractEdge, ...]]:
    anchor = SourceAnchor("contract.ts", 1, "test", "test", 1.0)
    default_evidence = {
        "request": "absent",
        "response": "absent",
        "error": "absent",
        "status": "absent",
        "ui_lifecycle": "present",
        "cache": front_cache,
    }
    front_status = {**default_evidence, **(front_evidence or {})}
    back_status = {
        **default_evidence,
        "ui_lifecycle": "absent",
        "cache": "absent",
        **(back_evidence or {}),
    }
    front = ContractNode(
        "front",
        "client_operation",
        "POST /items",
        "frontend",
        front_capability,
        anchor,
        {
            "method": "POST",
            "normalized_path": "/items",
            "status_codes": list(front_statuses),
            "mutation": mutation,
            "cache_invalidation": front_cache,
            "evidence": front_status,
        },
    )
    back = ContractNode(
        "back",
        "route",
        "POST /items",
        "backend",
        back_capability,
        anchor,
        {
            "method": "POST",
            "normalized_path": "/items",
            "status_codes": list(back_statuses),
            "mutation": False,
            "cache_invalidation": "absent",
            "evidence": back_status,
        },
    )
    nodes: list[ContractNode] = [front, back]
    edges: list[ContractEdge] = []

    def link(
        operation: ContractNode,
        node: ContractNode,
        kind: str,
    ) -> None:
        nodes.append(node)
        edges.append(
            ContractEdge(operation.id, node.id, kind, "test", 1.0, anchor)
        )

    for operation, schema, side in (
        (front, front_schema, "frontend"),
        (back, back_schema, "backend"),
    ):
        if schema is not None:
            link(
                operation,
                ContractNode(
                    f"{side}-response",
                    "response_schema",
                    "Response",
                    side,
                    "present",
                    anchor,
                    schema,
                ),
                "returns",
            )
    for operation, auth, side in (
        (front, front_auth, "frontend"),
        (back, back_auth, "backend"),
    ):
        link(
            operation,
            ContractNode(
                f"{side}-auth",
                "auth_requirement",
                "authentication",
                side,
                auth[0],
                anchor,
                {"authorization": auth[1], "tenant": auth[2]},
            ),
            "requires",
        )
    for state in front_states:
        link(
            front,
            ContractNode(
                f"state:{state}",
                "ui_state",
                state,
                "frontend",
                "present",
                anchor,
                {},
            ),
            "renders_state",
        )
    for operation, errors, side in (
        (front, front_errors, "frontend"),
        (back, back_errors, "backend"),
    ):
        for status, schema in errors:
            link(
                operation,
                ContractNode(
                    f"{side}-error:{status}",
                    "error_schema",
                    f"Error{status}",
                    side,
                    "present",
                    anchor,
                    {**schema, "status": status},
                ),
                "returns_error",
            )
    return tuple(nodes), tuple(edges)


@pytest.mark.parametrize(
    ("front_schema", "back_schema", "expected_id", "expected_status"),
    [
        (
            {"type": "object", "properties": {"id": {}}},
            {"type": "object", "properties": {"id": {"type": "string"}}},
            "contract-response-field-type-evidence-unknown",
            "investigate",
        ),
        (
            {"type": "string"},
            {"type": "string", "enum": ["a", "b"]},
            "contract-response-field-enum-mismatch",
            "pending",
        ),
        (
            {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": [],
            },
            {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
            "contract-response-field-required-mismatch",
            "pending",
        ),
        (
            {"type": "string", "nullable": True},
            {"type": "string"},
            "contract-response-field-nullability-mismatch",
            "pending",
        ),
        (
            {"type": "string"},
            {"type": "string", "minLength": 3},
            "contract-response-field-validation-mismatch",
            "pending",
        ),
        (
            {"type": "array"},
            {"type": "array", "items": {"type": "string"}},
            "contract-response-array-items-evidence-unknown",
            "investigate",
        ),
    ],
)
def test_repair_schema_lattice_never_treats_one_sided_evidence_as_clean(
    front_schema,
    back_schema,
    expected_id,
    expected_status,
) -> None:
    nodes, edges = _repair_contract_graph(
        front_schema=front_schema,
        back_schema=back_schema,
        front_evidence={"response": "present"},
        back_evidence={"response": "present"},
    )

    findings = reconcile_contract_graph(nodes, edges)

    assert [finding.detector_id for finding in findings] == [expected_id]
    assert findings[0].status == expected_status


@pytest.mark.parametrize(
    ("kwargs", "expected_id", "expected_status"),
    [
        (
            {
                "front_evidence": {"status": "absent"},
                "back_evidence": {"status": "present"},
                "back_statuses": ("200",),
            },
            "contract-status-mismatch",
            "pending",
        ),
        (
            {
                "front_auth": ("absent", "absent", "absent"),
                "back_auth": ("present", "present", "absent"),
            },
            "contract-auth-mismatch",
            "pending",
        ),
        (
            {
                "front_auth": ("present", "present", "unknown"),
                "back_auth": ("present", "present", "present"),
            },
            "contract-tenant-evidence-unknown",
            "investigate",
        ),
        (
            {
                "front_schema": {"type": "object"},
                "back_schema": {"type": "object"},
                "front_evidence": {
                    "response": "present",
                    "ui_lifecycle": "absent",
                },
                "back_evidence": {"response": "present"},
                "front_states": (),
            },
            "contract-ui-state-missing",
            "pending",
        ),
        (
            {
                "mutation": True,
                "front_cache": "unknown",
                "front_evidence": {"cache": "unknown"},
            },
            "contract-cache-invalidation-evidence-unknown",
            "investigate",
        ),
        (
            {
                "front_capability": "contradictory",
                "back_capability": "present",
            },
            "contract-evidence-contradictory",
            "investigate",
        ),
    ],
)
def test_repair_operation_lattice_never_treats_missing_evidence_as_clean(
    kwargs,
    expected_id,
    expected_status,
) -> None:
    nodes, edges = _repair_contract_graph(**kwargs)

    findings = reconcile_contract_graph(nodes, edges)

    assert [finding.detector_id for finding in findings] == [expected_id]
    assert findings[0].status == expected_status


def test_repair_conflicting_backend_sources_are_investigative_not_first_wins() -> None:
    nodes, edges = _repair_contract_graph()
    backend = next(node for node in nodes if node.id == "back")
    conflicting_backend = ContractNode(
        "back-conflict",
        backend.kind,
        backend.name,
        backend.side,
        backend.capability_status,
        backend.source,
        dict(backend.attributes),
    )
    conflicting_auth = ContractNode(
        "back-conflict-auth",
        "auth_requirement",
        "bearer",
        "backend",
        "present",
        backend.source,
        {"authorization": "absent", "tenant": "absent"},
    )
    conflicting_edge = ContractEdge(
        conflicting_backend.id,
        conflicting_auth.id,
        "requires",
        "test",
        1.0,
        backend.source,
    )

    findings = reconcile_contract_graph(
        (*nodes, conflicting_backend, conflicting_auth),
        (*edges, conflicting_edge),
    )

    assert [finding.detector_id for finding in findings] == [
        "contract-evidence-contradictory"
    ]
    assert findings[0].contract_anchor["field"] == "auth"
    assert findings[0].status == "investigate"


def test_repair_error_envelope_shapes_are_compared() -> None:
    nodes, edges = _repair_contract_graph(
        front_evidence={"error": "present"},
        back_evidence={"error": "present"},
        front_errors=(
            ("422", {"type": "object", "properties": {"detail": {"type": "string"}}}),
        ),
        back_errors=(
            ("422", {"type": "object", "properties": {"detail": {"type": "array"}}}),
        ),
    )

    findings = reconcile_contract_graph(nodes, edges)

    assert [finding.detector_id for finding in findings] == [
        "contract-error-field-type-mismatch"
    ]


def test_repair_generic_fastapi_dependency_is_not_authentication(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import Depends, FastAPI

app = FastAPI()

def get_db():
    return object()

@app.get("/items")
def items(db=Depends(get_db)):
    return []
""".strip(),
        encoding="utf-8",
    )

    graph = build_project_map(tmp_path)
    auth = next(node for node in graph.nodes if node.kind == "auth_requirement")

    assert auth.capability_status == "unknown"
    assert auth.name == "authentication"


def test_repair_fastapi_security_proof_marks_authentication_present(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI, Security
from fastapi.security import HTTPBearer

app = FastAPI()
bearer = HTTPBearer()

@app.get("/items")
def items(credentials=Security(bearer)):
    return []
""".strip(),
        encoding="utf-8",
    )

    graph = build_project_map(tmp_path)
    auth = next(node for node in graph.nodes if node.kind == "auth_requirement")

    assert auth.capability_status == "present"
    assert auth.name == "bearer"


def test_repair_arbitrary_base_class_is_not_persistence(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI

app = FastAPI()

class Base:
    pass

class User(Base):
    id: int

def load_user():
    return User()

@app.get("/users")
def users():
    return load_user()
""".strip(),
        encoding="utf-8",
    )

    graph = build_project_map(tmp_path)

    assert not any(node.kind == "entity" for node in graph.nodes)
    assert not any(node.kind == "database_field" for node in graph.nodes)


def test_repair_lineage_keeps_service_and_entity_siblings(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

app = FastAPI()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)

class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)

def load_user():
    return User()

def load_team():
    return Team()

@app.get("/dashboard")
def dashboard():
    return load_user(), load_team()
""".strip(),
        encoding="utf-8",
    )

    graph = build_project_map(tmp_path)
    nodes = {node.id: node for node in graph.nodes}
    pairs = {
        (nodes[edge.source].name, nodes[edge.target].name)
        for edge in graph.edges
        if nodes[edge.source].kind in {"handler", "service_operation", "entity"}
        and nodes[edge.target].kind in {"service_operation", "entity"}
    }

    assert pairs == {
        ("dashboard", "load_user"),
        ("dashboard", "load_team"),
        ("load_user", "User"),
        ("load_team", "Team"),
    }


def _typed_frontend_operation(
    *,
    request_contracts: dict[str, dict] | None = None,
    response_contracts: dict[str, dict] | None = None,
    method: str = "POST",
) -> dict[str, object]:
    return {
        "id": "data:typed",
        "kind": "data",
        "name": "/items",
        "file": "src/client.ts",
        "line": 7,
        "metadata": {
            "transport": "http",
            "method": method,
            "request_contracts": request_contracts or {},
            "response_contracts": response_contracts or {},
            "auth": "absent",
            "authorization": "absent",
            "tenant": "absent",
            "error_evidence": "absent",
            "ui_required": False,
            "extractor": "test",
            "confidence": 1.0,
        },
    }


def _write_items_openapi(
    root: Path,
    *,
    request_schema: dict | None = None,
    responses: dict[str, dict] | None = None,
    method: str = "post",
) -> None:
    operation: dict[str, object] = {
        "responses": {
            status: {
                "content": {"application/json": {"schema": schema}}
            }
            for status, schema in (responses or {"200": {"type": "string"}}).items()
        }
    }
    if request_schema is not None:
        operation["requestBody"] = {
            "content": {"application/json": {"schema": request_schema}}
        }
    (root / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": {"/items": {method: operation}},
            }
        ),
        encoding="utf-8",
    )


def test_multiple_distinct_dto_references_are_not_first_wins(tmp_path) -> None:
    _write_items_openapi(tmp_path, request_schema={"type": "string"})
    graph = build_project_map(
        tmp_path,
        [
            _typed_frontend_operation(
                request_contracts={
                    "A": {"type": "string"},
                    "B": {"type": "integer"},
                }
            )
        ],
    )
    operation = next(node for node in graph.nodes if node.kind == "client_operation")
    request_nodes = {
        edge.target
        for edge in graph.edges
        if edge.source == operation.id and edge.kind == "accepts"
    }

    assert operation.attributes["evidence"]["request"] == "contradictory"
    assert {
        node.name for node in graph.nodes if node.id in request_nodes
    } == {"A", "B"}
    assert any(
        finding.detector_id == "contract-evidence-contradictory"
        for finding in graph.findings
    )


def test_semantically_duplicate_dto_references_collapse_once(tmp_path) -> None:
    _write_items_openapi(tmp_path, request_schema={"type": "string"})
    graph = build_project_map(
        tmp_path,
        [
            _typed_frontend_operation(
                request_contracts={
                    "A": {"type": "string"},
                    "B": {"type": "string"},
                }
            )
        ],
    )
    operation = next(node for node in graph.nodes if node.kind == "client_operation")
    request_nodes = [
        node
        for edge in graph.edges
        if edge.source == operation.id and edge.kind == "accepts"
        for node in graph.nodes
        if node.id == edge.target
    ]

    assert operation.attributes["evidence"]["request"] == "present"
    assert len(request_nodes) == 1
    assert request_nodes[0].attributes["type_identities"] == ["A", "B"]


@pytest.mark.parametrize(
    ("responses", "expected_types"),
    [
        (
            {"200": {"type": "string"}, "201": {"type": "integer"}},
            {"200": "string", "201": "integer"},
        ),
        (
            {"200": {"type": "string"}, "201": {"type": "string"}},
            {"200": "string", "201": "string"},
        ),
    ],
)
def test_openapi_preserves_every_success_response_variant(
    tmp_path,
    responses,
    expected_types,
) -> None:
    _write_items_openapi(tmp_path, responses=responses)
    graph = build_project_map(tmp_path)
    route = next(node for node in graph.nodes if node.kind == "route")
    response_nodes = [
        node
        for edge in graph.edges
        if edge.source == route.id and edge.kind == "returns"
        for node in graph.nodes
        if node.id == edge.target
    ]
    roundtrip = ProjectMap.from_dict(graph.to_dict())

    assert route.attributes["evidence"]["response"] == "present"
    assert {
        str(node.attributes["status"]): node.attributes["type"]
        for node in response_nodes
    } == expected_types
    assert {
        str(node.attributes["status"])
        for node in roundtrip.nodes
        if node.kind == "response_schema"
    } == {"200", "201"}


def test_ambiguous_statusless_frontend_response_does_not_hide_variants(
    tmp_path,
) -> None:
    _write_items_openapi(
        tmp_path,
        responses={"200": {"type": "string"}, "201": {"type": "integer"}},
        method="get",
    )
    graph = build_project_map(
        tmp_path,
        [
            _typed_frontend_operation(
                response_contracts={"Item": {"type": "string"}},
                method="GET",
            )
        ],
    )

    assert any(
        finding.detector_id == "contract-response-evidence-unknown"
        for finding in graph.findings
    )


def test_same_shape_success_variants_do_not_conflict_with_frontend_shape(
    tmp_path,
) -> None:
    _write_items_openapi(
        tmp_path,
        responses={"200": {"type": "string"}, "201": {"type": "string"}},
        method="get",
    )
    graph = build_project_map(
        tmp_path,
        [
            _typed_frontend_operation(
                response_contracts={"Item": {"type": "string"}},
                method="GET",
            )
        ],
    )

    assert not any(
        finding.detector_id
        in {
            "contract-response-evidence-unknown",
            "contract-response-field-type-mismatch",
            "contract-evidence-contradictory",
        }
        for finding in graph.findings
    )


def test_sqlalchemy_mapped_annotations_preserve_qualified_field_types(
    tmp_path,
) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI
from sqlalchemy.orm import DeclarativeBase as SABase
from sqlalchemy.orm import Mapped as ColumnType
from sqlalchemy.orm import mapped_column

app = FastAPI()

class Base(SABase):
    pass

class Item(Base):
    __tablename__ = "items"
    id: ColumnType[int] = mapped_column(primary_key=True)
    tags: ColumnType[list[str]] = mapped_column()
    note: ColumnType[str | None] = mapped_column()

@app.get("/items")
def items():
    return Item()
""".strip(),
        encoding="utf-8",
    )
    graph = build_project_map(tmp_path)
    fields = {
        node.name: dict(node.attributes)
        for node in graph.nodes
        if node.kind == "database_field"
    }

    assert fields["id"]["type"] == "integer"
    assert fields["tags"] == {"type": "array", "items": {"type": "string"}}
    assert fields["note"] == {"type": "string", "nullable": True}


def test_unqualified_mapped_annotation_remains_unknown(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import FastAPI

app = FastAPI()

class Mapped:
    pass

class Item:
    __tablename__ = "items"
    id: Mapped[int]

@app.get("/items")
def items():
    return Item()
""".strip(),
        encoding="utf-8",
    )
    graph = build_project_map(tmp_path)
    field = next(node for node in graph.nodes if node.kind == "database_field")

    assert field.name == "id"
    assert field.attributes["type"] == "unknown"


def test_qualified_depends_security_binding_marks_auth_present(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import Depends as Inject, FastAPI
from fastapi.security import OAuth2PasswordBearer as OAuth

app = FastAPI()
oauth2_scheme = OAuth(tokenUrl="/token")

@app.get("/items")
def items(token=Inject(oauth2_scheme)):
    return []
""".strip(),
        encoding="utf-8",
    )
    graph = build_project_map(tmp_path)
    auth = next(node for node in graph.nodes if node.kind == "auth_requirement")

    assert auth.capability_status == "present"
    assert auth.name == "oauth2_scheme"


def test_name_only_depends_security_binding_remains_unknown(tmp_path) -> None:
    (tmp_path / "app.py").write_text(
        """
from fastapi import Depends, FastAPI

app = FastAPI()
oauth2_scheme = lambda: "token"

@app.get("/items")
def items(token=Depends(oauth2_scheme)):
    return []
""".strip(),
        encoding="utf-8",
    )
    graph = build_project_map(tmp_path)
    auth = next(node for node in graph.nodes if node.kind == "auth_requirement")

    assert auth.capability_status == "unknown"
    assert auth.name == "authentication"
