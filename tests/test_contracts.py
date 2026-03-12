"""Tests for contract validation (OpenAPI/GraphQL/Prisma parsing + frontend DTO validation)."""

import json
from pathlib import Path

import pytest

from uidetox import state as state_module
from uidetox.state import ensure_uidetox_dir
from uidetox.contracts import (
    ContractViolation,
    EndpointDef,
    FieldDef,
    ModelDef,
    SchemaArtifact,
    _extract_api_calls,
    _extract_frontend_types,
    _parse_graphql,
    _parse_prisma,
    discover_schemas,
    parse_all_schemas,
    parse_schema,
    save_contract_artifacts,
    load_contract_artifacts,
    validate_frontend_contracts,
)


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None


# ── Data-class basics ────────────────────────────────────────────


class TestFieldDef:
    def test_to_dict(self):
        f = FieldDef(name="id", type="string")
        d = f.to_dict()
        assert d == {"name": "id", "type": "string", "optional": False, "is_list": False}

    def test_optional_field(self):
        f = FieldDef(name="bio", type="string", optional=True)
        assert f.to_dict()["optional"] is True


class TestModelDef:
    def test_field_names(self):
        m = ModelDef(name="User", fields=[
            FieldDef(name="id", type="string"),
            FieldDef(name="name", type="string"),
        ])
        assert m.field_names() == {"id", "name"}

    def test_to_dict_roundtrip(self):
        m = ModelDef(name="Post", source="prisma", fields=[
            FieldDef(name="title", type="String"),
        ])
        d = m.to_dict()
        assert d["name"] == "Post"
        assert len(d["fields"]) == 1


class TestContractViolation:
    def test_to_issue(self):
        v = ContractViolation(
            file="src/User.tsx",
            line=10,
            violation_type="missing_field",
            detail="Missing 'email' from User",
            model_name="User",
            severity="T1",
        )
        issue = v.to_issue()
        assert issue["file"] == "src/User.tsx"
        assert issue["tier"] == "T1"
        assert "missing_field" in issue["issue"]
        assert "User" in issue["command"]


# ── OpenAPI parsing ──────────────────────────────────────────────


class TestOpenAPIParsing:
    def test_parse_openapi_json(self, tmp_path):
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/User"}
                                    }
                                }
                            },
                            "404": {},
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "required": ["id", "name"],
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "email": {"type": "string"},
                        },
                    }
                }
            },
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")

        art = parse_schema(spec_file)
        assert art is not None
        assert art.source == "openapi"
        assert "User" in art.models
        assert art.models["User"].field_names() == {"id", "name", "email"}
        assert len(art.endpoints) == 1
        assert art.endpoints[0].method == "GET"


# ── GraphQL parsing ──────────────────────────────────────────────


class TestGraphQLParsing:
    def test_parse_graphql_schema(self, tmp_path):
        schema = (
            "type User {\n"
            "  id: ID!\n"
            "  name: String!\n"
            "  posts: [Post!]!\n"
            "}\n\n"
            "type Post {\n"
            "  title: String!\n"
            "  body: String\n"
            "}\n\n"
            "type Query {\n"
            "  users: [User!]!\n"
            "  post(id: ID!): Post\n"
            "}\n"
        )
        gql_file = tmp_path / "schema.graphql"
        gql_file.write_text(schema, encoding="utf-8")

        art = _parse_graphql(gql_file)
        assert "User" in art.models
        assert "Post" in art.models
        assert art.models["User"].field_names() == {"id", "name", "posts"}
        assert len(art.endpoints) >= 2  # users + post queries


# ── Prisma parsing ───────────────────────────────────────────────


class TestPrismaParsing:
    def test_parse_prisma_schema(self, tmp_path):
        schema = (
            "model User {\n"
            "  id    String @id @default(uuid())\n"
            "  name  String\n"
            "  email String?\n"
            "  posts Post[]\n"
            "}\n\n"
            "model Post {\n"
            "  id     String @id\n"
            "  title  String\n"
            "  author User   @relation(fields: [authorId], references: [id])\n"
            "}\n"
        )
        prisma_file = tmp_path / "schema.prisma"
        prisma_file.write_text(schema, encoding="utf-8")

        art = _parse_prisma(prisma_file)
        assert "User" in art.models
        assert "Post" in art.models
        assert "email" in art.models["User"].field_names()


# ── Schema discovery ─────────────────────────────────────────────


class TestSchemaDiscovery:
    def test_discovers_openapi_and_prisma(self, tmp_path):
        (tmp_path / "openapi.json").write_text('{"openapi":"3.0.0","paths":{},"components":{"schemas":{}}}')
        (tmp_path / "prisma").mkdir()
        (tmp_path / "prisma" / "schema.prisma").write_text("model X { id String @id }")

        found = discover_schemas(tmp_path)
        names = {f.name for f in found}
        assert "openapi.json" in names
        assert "schema.prisma" in names


# ── Frontend DTO extraction ──────────────────────────────────────


class TestFrontendExtraction:
    def test_extract_interface_fields(self, tmp_path):
        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            "interface UserDto {\n"
            "  id: string;\n"
            "  name: string;\n"
            "  age: number;\n"
            "}\n",
            encoding="utf-8",
        )
        types = _extract_frontend_types(ts_file)
        assert "UserDto" in types
        assert types["UserDto"] == {"id", "name", "age"}

    def test_extract_api_calls(self, tmp_path):
        tsx_file = tmp_path / "api.tsx"
        tsx_file.write_text(
            'const res = fetch("/api/users");\n'
            'const data = axios.get("/api/posts");\n',
            encoding="utf-8",
        )
        calls = _extract_api_calls(tsx_file)
        assert "/api/users" in calls
        assert "/api/posts" in calls


# ── End-to-end validation ────────────────────────────────────────


class TestFrontendContractValidation:
    def test_detects_missing_required_field(self, tmp_path):
        # Backend model: User { id (required), name (required), email }
        model = ModelDef(name="User", fields=[
            FieldDef(name="id", type="string", optional=False),
            FieldDef(name="name", type="string", optional=False),
            FieldDef(name="email", type="string", optional=True),
        ])
        artifact = SchemaArtifact(
            source="openapi",
            source_file="openapi.json",
            models={"User": model},
        )

        # Frontend: UserDto missing 'name'
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tsx_file = src_dir / "User.tsx"
        tsx_file.write_text(
            "interface UserDto {\n"
            "  id: string;\n"
            "  email: string;\n"
            "}\n"
            "export function User() { return <div /> }\n",
            encoding="utf-8",
        )

        violations = validate_frontend_contracts(
            tmp_path, [artifact], frontend_files=[tsx_file]
        )
        types = [v.violation_type for v in violations]
        assert "missing_field" in types

    def test_detects_extra_field(self, tmp_path):
        model = ModelDef(name="User", fields=[
            FieldDef(name="id", type="string"),
        ])
        artifact = SchemaArtifact(
            source="openapi",
            source_file="openapi.json",
            models={"User": model},
        )

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tsx_file = src_dir / "Profile.tsx"
        tsx_file.write_text(
            "interface UserDto {\n"
            "  id: string;\n"
            "  avatar: string;\n"
            "}\n",
            encoding="utf-8",
        )

        violations = validate_frontend_contracts(
            tmp_path, [artifact], frontend_files=[tsx_file]
        )
        types = [v.violation_type for v in violations]
        assert "extra_field" in types


# ── Cache persistence ────────────────────────────────────────────


class TestContractCache:
    def test_save_and_load_artifacts(self, tmp_path):
        art = SchemaArtifact(
            source="prisma",
            source_file="schema.prisma",
            models={"User": ModelDef(name="User", fields=[
                FieldDef(name="id", type="String"),
            ])},
        )
        save_contract_artifacts(tmp_path, [art])
        loaded = load_contract_artifacts(tmp_path)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["source"] == "prisma"
