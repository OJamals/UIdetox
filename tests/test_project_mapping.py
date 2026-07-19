from __future__ import annotations

import json

from uidetox.project_map import (
    OperationEvidence,
    ProjectMap,
    SourceAnchor,
    build_project_map,
    normalize_route_path,
    reconcile_operations,
)
from uidetox.frontend_map import FrontendMap, map_frontend
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


def _operation(
    side: str,
    method: str | None,
    path: str | None,
    *,
    dynamic: bool = False,
    classification: str = "application",
) -> OperationEvidence:
    normalized, parameters, unresolved = normalize_route_path(path)
    return OperationEvidence(
        side=side,
        method=method,
        path=path,
        normalized_path=normalized,
        parameters=parameters,
        dynamic=dynamic or unresolved,
        classification=classification,
        sources=(SourceAnchor(f"{side}.ts", 1, "test", "test", 1.0),),
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

    backend = project.backend_operations
    assert len(backend) == 1
    assert backend[0].normalized_path == "/users/{}"
    assert backend[0].parameters == ("id", "userId")
    assert backend[0].schemas == ("User",)
    assert [source.framework for source in backend[0].sources] == [
        "openapi",
        "openapi",
    ]
    assert project.counts == {
        "frontend_only": 0,
        "backend_only": 0,
        "method_mismatch": 0,
        "unresolved": 0,
    }


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
        (item.method, item.normalized_path, item.sources[0].framework)
        for item in project.backend_operations
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
        (item.method, item.normalized_path, item.sources[0].framework)
        for item in project.backend_operations
    }

    assert ("POST", "/express-api/orders/{}", "express") in observed
    assert ("PATCH", "/fast-api/orders/{}", "fastify") in observed
    assert ("DELETE", "/orders/{}", "nest") in observed
    assert project.evidence["adapters"] == ["express", "fastify", "nest"]


def test_reconciliation_reports_each_parity_class_and_suppresses_internal() -> None:
    frontend = (
        _operation("frontend", "GET", "/matched"),
        _operation("frontend", "POST", "/method"),
        _operation("frontend", "GET", "/frontend-only"),
        _operation("frontend", None, None, dynamic=True),
    )
    backend = (
        _operation("backend", "GET", "/matched"),
        _operation("backend", "PUT", "/method"),
        _operation("backend", "GET", "/backend-only"),
        _operation(
            "backend",
            "GET",
            "/health",
            classification="internal",
        ),
    )

    findings, suppressed = reconcile_operations(frontend, backend)
    kinds = [finding.kind for finding in findings]

    assert kinds.count("frontend_only") == 1
    assert kinds.count("backend_only") == 1
    assert kinds.count("method_mismatch") == 1
    assert kinds.count("unresolved") == 1
    assert suppressed == ["backend:GET:/health"]


def test_partial_method_overlap_reports_only_unmatched_methods() -> None:
    frontend = (
        _operation("frontend", "GET", "/items"),
        _operation("frontend", "POST", "/items"),
    )
    backend = (
        _operation("backend", "GET", "/items"),
        _operation("backend", "PUT", "/items"),
    )

    findings, _ = reconcile_operations(frontend, backend)

    assert len(findings) == 1
    assert findings[0].kind == "method_mismatch"
    assert findings[0].frontend == ("frontend:POST:/items",)
    assert findings[0].backend == ("backend:PUT:/items",)


def test_unknown_route_syntax_is_unresolved_not_false_match(tmp_path) -> None:
    (tmp_path / "unknown.ts").write_text(
        'mystery.endpoint("/users", handler);',
        encoding="utf-8",
    )
    project = build_project_map(tmp_path, [_frontend_node("/users", "GET")])

    assert project.backend_operations == ()
    assert project.counts["frontend_only"] == 1

    (tmp_path / "unknown.ts").write_text(
        "mystery.route(dynamicPath, handler);",
        encoding="utf-8",
    )
    project = build_project_map(tmp_path, [_frontend_node("/users", "GET")])
    assert len(project.backend_operations) == 1
    assert project.backend_operations[0].dynamic is True
    assert project.counts["unresolved"] == 1
    assert project.counts["frontend_only"] == 1


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
    assert all(item.dynamic for item in project.backend_operations)
    assert all(item.classification == "unknown" for item in project.backend_operations)
    assert project.counts["unresolved"] == 2


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
    comparable = {
        (item.method, item.normalized_path, item.sources[0].framework)
        for item in project.backend_operations
        if item.classification != "unknown"
    }
    unresolved = {
        item.normalized_path
        for item in project.backend_operations
        if item.classification == "unknown"
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
    comparable = {
        (item.method, item.normalized_path, item.sources[0].framework)
        for item in project.backend_operations
        if item.classification != "unknown"
    }
    unresolved = {
        item.normalized_path
        for item in project.backend_operations
        if item.classification == "unknown"
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

    assert all(item.classification == "unknown" for item in project.backend_operations)
    assert {item.normalized_path for item in project.backend_operations} == {
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
    (source / "api.ts").write_text(
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

    assert project.counts["method_mismatch"] == 1
    assert redesign.parity["counts"]["method_mismatch"] == 1
    assert "Cross-stack parity findings:" in brief
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
    operations = ProjectMap.from_dict(frontend_map.project_map).frontend_operations

    assert [(item.method, item.normalized_path) for item in operations] == [
        ("GET", "/same"),
        ("POST", "/same"),
    ]
    assert len({node.id for node in frontend_map.nodes}) == len(frontend_map.nodes)
