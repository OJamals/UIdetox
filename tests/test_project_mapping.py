from __future__ import annotations

import json
from pathlib import Path

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


def test_openapi_json_yaml_extract_schema_refs_and_dedupe_provenance(tmp_path) -> None:
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
    assert len(backend) == 1
    assert backend[0].attributes["normalized_path"] == "/users/{}"
    assert backend[0].attributes["parameters"] == ["id", "userId"]
    assert [source["framework"] for source in backend[0].attributes["sources"]] == [
        "openapi",
        "openapi",
    ]
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


def test_fullstack_fixture_reconciles_without_duplicate_probe_manifest() -> None:
    fixture = (
        Path(__file__).parents[1] / "examples" / "fullstack-slop-lab"
    )

    frontend_map = map_frontend(fixture, ".")
    project = ProjectMap.from_dict(frontend_map.project_map)

    assert project.counts == {"contract_mismatch": 2, "coverage_gap": 26}
    assert project.evidence["unknown_backend_evidence"] == 0
    assert len(_operation_nodes(project, "frontend")) == 28


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
    reachable = {
        edge.target
        for edge in project.edges
        if edge.source == route.id or edge.source.startswith(("handler:", "service:", "entity:"))
    }
    node_by_id = {node.id: node for node in project.nodes}

    assert any(node_by_id[node_id].kind == "handler" for node_id in reachable)
    assert any(node_by_id[node_id].kind == "service_operation" for node_id in reachable)
    assert any(node_by_id[node_id].kind == "entity" for node_id in reachable)
    assert {"id", "email"} <= {
        node.name for node in project.nodes if node.kind == "database_field"
    }
    assert any(
        edge.source == route.id
        and edge.kind == "requires"
        and node_by_id[edge.target].capability_status == "present"
        for edge in project.edges
    )
