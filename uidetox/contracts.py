"""Contract validation: parse OpenAPI/GraphQL/Prisma into normalized schema artifacts.

Validates that frontend DTO usage conforms to backend API contracts before
issues are resolved.  This prevents the agent from generating or fixing code
that drifts from the actual backend surface.

Normalized artifact format (``SchemaArtifact``):
    {
        "source": "openapi" | "graphql" | "prisma",
        "source_file": "path/to/schema",
        "endpoints": [
            {
                "name": "GET /users",
                "method": "GET" | "POST" | "QUERY" | "MUTATION" | ...,
                "path": "/users",
                "request_dto": {"fields": {"id": "string", ...}},
                "response_dto": {"fields": {"id": "string", ...}},
                "status_codes": [200, 400, 404, 500],
            }
        ],
        "models": {
            "User": {"fields": {"id": "string", "name": "string", ...}},
        },
    }
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Normalized schema types ──────────────────────────────────────

@dataclass
class FieldDef:
    """A single field in a DTO/model."""
    name: str
    type: str
    optional: bool = False
    is_list: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "optional": self.optional,
            "is_list": self.is_list,
        }


@dataclass
class ModelDef:
    """A normalized model/DTO definition."""
    name: str
    fields: list[FieldDef] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fields": [f.to_dict() for f in self.fields],
            "source": self.source,
        }

    def field_names(self) -> set[str]:
        return {f.name for f in self.fields}


@dataclass
class EndpointDef:
    """A normalized API endpoint."""
    name: str
    method: str
    path: str
    request_dto: ModelDef | None = None
    response_dto: ModelDef | None = None
    status_codes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "request_dto": self.request_dto.to_dict() if self.request_dto else None,
            "response_dto": self.response_dto.to_dict() if self.response_dto else None,
            "status_codes": self.status_codes,
        }


@dataclass
class SchemaArtifact:
    """Top-level normalized schema from any backend source."""
    source: str  # "openapi" | "graphql" | "prisma"
    source_file: str
    endpoints: list[EndpointDef] = field(default_factory=list)
    models: dict[str, ModelDef] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_file": self.source_file,
            "endpoints": [e.to_dict() for e in self.endpoints],
            "models": {k: v.to_dict() for k, v in self.models.items()},
        }


# ── Validation result ────────────────────────────────────────────

@dataclass
class ContractViolation:
    """A mismatch between frontend DTO usage and backend contract."""
    file: str
    line: int
    violation_type: str  # "missing_field" | "extra_field" | "type_mismatch" | "unhandled_status"
    detail: str
    model_name: str = ""
    endpoint: str = ""
    severity: str = "T2"  # T1=critical, T2=important, T3=moderate

    def to_issue(self) -> dict:
        return {
            "file": self.file,
            "tier": self.severity,
            "issue": f"Contract violation ({self.violation_type}): {self.detail}",
            "command": f"Align frontend DTO with backend contract for {self.model_name or self.endpoint}. "
                       f"Check the schema definition and ensure all fields match.",
        }


# ── OpenAPI Parser ───────────────────────────────────────────────

def _parse_openapi(filepath: Path) -> SchemaArtifact:
    """Parse an OpenAPI/Swagger YAML or JSON spec into normalized artifacts."""
    content = filepath.read_text(encoding="utf-8")
    data: dict[str, Any] = {}

    if filepath.suffix in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(content) or {}
        except Exception:
            return SchemaArtifact(source="openapi", source_file=str(filepath))
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return SchemaArtifact(source="openapi", source_file=str(filepath))

    artifact = SchemaArtifact(source="openapi", source_file=str(filepath))

    # Parse component schemas (OpenAPI 3.x)
    schemas = data.get("components", {}).get("schemas", {})
    # Fallback: Swagger 2.x definitions
    if not schemas:
        schemas = data.get("definitions", {})

    for name, schema in schemas.items():
        model = _openapi_schema_to_model(name, schema)
        artifact.models[name] = model

    # Parse paths → endpoints
    paths = data.get("paths", {})
    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete", "options", "head"):
            operation = path_item.get(method)
            if not operation:
                continue

            endpoint_name = f"{method.upper()} {path_str}"

            # Extract status codes
            responses = operation.get("responses", {})
            status_codes = []
            response_dto = None
            for status_str, resp_obj in responses.items():
                try:
                    status_codes.append(int(status_str))
                except (ValueError, TypeError):
                    pass
                # Extract response schema
                if response_dto is None and isinstance(resp_obj, dict):
                    resp_content = resp_obj.get("content", {})
                    json_content = resp_content.get("application/json", {})
                    resp_schema = json_content.get("schema", {})
                    if resp_schema:
                        ref = resp_schema.get("$ref", "")
                        ref_name = ref.split("/")[-1] if ref else ""
                        if ref_name and ref_name in artifact.models:
                            response_dto = artifact.models[ref_name]
                        elif resp_schema.get("properties"):
                            response_dto = _openapi_schema_to_model(
                                f"{endpoint_name}_response", resp_schema
                            )

            # Extract request body schema
            request_dto = None
            req_body = operation.get("requestBody", {})
            if isinstance(req_body, dict):
                req_content = req_body.get("content", {})
                json_content = req_content.get("application/json", {})
                req_schema = json_content.get("schema", {})
                if req_schema:
                    ref = req_schema.get("$ref", "")
                    ref_name = ref.split("/")[-1] if ref else ""
                    if ref_name and ref_name in artifact.models:
                        request_dto = artifact.models[ref_name]
                    elif req_schema.get("properties"):
                        request_dto = _openapi_schema_to_model(
                            f"{endpoint_name}_request", req_schema
                        )

            artifact.endpoints.append(EndpointDef(
                name=endpoint_name,
                method=method.upper(),
                path=path_str,
                request_dto=request_dto,
                response_dto=response_dto,
                status_codes=sorted(status_codes),
            ))

    return artifact


def _openapi_schema_to_model(name: str, schema: dict) -> ModelDef:
    """Convert an OpenAPI schema object to a normalized ModelDef."""
    model = ModelDef(name=name, source="openapi")
    required_fields = set(schema.get("required", []))
    properties = schema.get("properties", {})

    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        field_type = prop_schema.get("type", "any")
        is_list = field_type == "array"
        if is_list:
            items = prop_schema.get("items", {})
            item_type = items.get("type", "any") if isinstance(items, dict) else "any"
            ref = items.get("$ref", "") if isinstance(items, dict) else ""
            if ref:
                field_type = ref.split("/")[-1]
            else:
                field_type = item_type
        elif "$ref" in prop_schema:
            field_type = prop_schema["$ref"].split("/")[-1]

        model.fields.append(FieldDef(
            name=prop_name,
            type=field_type,
            optional=prop_name not in required_fields,
            is_list=is_list,
        ))

    return model


# ── GraphQL Parser ───────────────────────────────────────────────

_GQL_TYPE_RE = re.compile(
    r'type\s+(\w+)\s*(?:@\w+(?:\([^)]*\))?)*\s*\{([^}]+)\}',
    re.DOTALL,
)
_GQL_FIELD_RE = re.compile(
    r'(\w+)\s*(?:\([^)]*\))?\s*:\s*(\[?\w+!?\]?!?)',
)
_GQL_QUERY_RE = re.compile(
    r'(query|mutation|subscription)\s*\{([^}]+)\}',
    re.DOTALL | re.IGNORECASE,
)


def _parse_graphql(filepath: Path) -> SchemaArtifact:
    """Parse a GraphQL schema file into normalized artifacts."""
    content = filepath.read_text(encoding="utf-8")
    artifact = SchemaArtifact(source="graphql", source_file=str(filepath))

    # Parse type definitions
    for match in _GQL_TYPE_RE.finditer(content):
        type_name = match.group(1)
        body = match.group(2)

        # Skip special root types (they become endpoints)
        if type_name in ("Query", "Mutation", "Subscription"):
            for field_match in _GQL_FIELD_RE.finditer(body):
                field_name = field_match.group(1)
                return_type = field_match.group(2)
                method = "QUERY" if type_name == "Query" else (
                    "MUTATION" if type_name == "Mutation" else "SUBSCRIPTION"
                )
                clean_type = return_type.strip("[]!")
                response_dto = artifact.models.get(clean_type)
                artifact.endpoints.append(EndpointDef(
                    name=f"{method} {field_name}",
                    method=method,
                    path=field_name,
                    response_dto=response_dto,
                    status_codes=[200],
                ))
            continue

        model = ModelDef(name=type_name, source="graphql")
        for field_match in _GQL_FIELD_RE.finditer(body):
            fname = field_match.group(1)
            ftype_raw = field_match.group(2)
            is_list = ftype_raw.startswith("[")
            optional = not ftype_raw.endswith("!")
            clean_type = ftype_raw.strip("[]!")
            model.fields.append(FieldDef(
                name=fname,
                type=clean_type,
                optional=optional,
                is_list=is_list,
            ))
        artifact.models[type_name] = model

    return artifact


# ── Prisma Parser ────────────────────────────────────────────────

_PRISMA_MODEL_RE = re.compile(
    r'model\s+(\w+)\s*\{([^}]+)\}',
    re.DOTALL,
)
_PRISMA_FIELD_RE = re.compile(
    r'(\w+)\s+([\w\[\]]+)(\?)?',
)


def _parse_prisma(filepath: Path) -> SchemaArtifact:
    """Parse a Prisma schema file into normalized artifacts."""
    content = filepath.read_text(encoding="utf-8")
    artifact = SchemaArtifact(source="prisma", source_file=str(filepath))

    for match in _PRISMA_MODEL_RE.finditer(content):
        model_name = match.group(1)
        body = match.group(2)

        model = ModelDef(name=model_name, source="prisma")
        for line in body.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("@@"):
                continue
            field_match = _PRISMA_FIELD_RE.match(line)
            if not field_match:
                continue
            fname = field_match.group(1)
            ftype = field_match.group(2)
            optional = bool(field_match.group(3))
            is_list = ftype.endswith("[]")
            clean_type = ftype.rstrip("[]")

            # Skip Prisma annotations/directives
            if fname.startswith("@"):
                continue

            model.fields.append(FieldDef(
                name=fname,
                type=clean_type,
                optional=optional,
                is_list=is_list,
            ))
        artifact.models[model_name] = model

    return artifact


# ── Schema discovery and parsing ─────────────────────────────────

_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "vendor",
              "__pycache__", ".tox", "coverage", ".turbo", "out"}

_OPENAPI_NAMES = [
    "openapi.json", "openapi.yaml", "openapi.yml",
    "swagger.json", "swagger.yaml", "swagger.yml",
    "api-spec.json", "api-spec.yaml", "api-spec.yml",
    "api.json", "api.yaml", "api.yml",
]

_GRAPHQL_SUFFIXES = (".graphql", ".gql")
_GRAPHQL_NAMES = ["schema.graphql", "schema.gql", "typeDefs.graphql", "typeDefs.gql"]

_PRISMA_NAMES = ["schema.prisma"]


def discover_schemas(root: Path) -> list[Path]:
    """Find all parseable schema files in the project."""
    found: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fname in _OPENAPI_NAMES:
                found.append(fpath)
            elif fname in _PRISMA_NAMES or fname.endswith(".prisma"):
                found.append(fpath)
            elif fname in _GRAPHQL_NAMES or fname.endswith(tuple(_GRAPHQL_SUFFIXES)):
                found.append(fpath)
        if len(found) >= 20:
            break

    return found


def parse_schema(filepath: Path) -> SchemaArtifact | None:
    """Parse a schema file into a normalized SchemaArtifact."""
    if not filepath.exists():
        return None

    name = filepath.name.lower()
    try:
        if name.endswith(".prisma"):
            return _parse_prisma(filepath)
        elif name.endswith((".graphql", ".gql")):
            return _parse_graphql(filepath)
        elif name.endswith((".json", ".yaml", ".yml")):
            # Check if it's an OpenAPI spec
            content = filepath.read_text(encoding="utf-8")
            if '"openapi"' in content or '"swagger"' in content or "openapi:" in content or "swagger:" in content:
                return _parse_openapi(filepath)
    except Exception:
        return None

    return None


def parse_all_schemas(root: Path) -> list[SchemaArtifact]:
    """Discover and parse all schema files in the project."""
    files = discover_schemas(root)
    artifacts: list[SchemaArtifact] = []
    for f in files:
        art = parse_schema(f)
        if art and (art.endpoints or art.models):
            artifacts.append(art)
    return artifacts


# ── Frontend DTO validation ──────────────────────────────────────

_TS_INTERFACE_RE = re.compile(
    r'(?:interface|type)\s+(\w+)\s*(?:extends\s+[\w,\s]+)?\s*[={]\s*\{?([^}]+)\}',
    re.DOTALL,
)
_TS_FIELD_RE = re.compile(r'(\w+)(\?)?:\s*([\w\[\]<>,\s|]+)')

_FETCH_PATTERN = re.compile(
    r'(?:fetch|axios\.(?:get|post|put|patch|delete)|api\.(?:get|post|put|patch|delete))\s*[(<]\s*[\'"`]([^\'"`]+)[\'"`]',
    re.IGNORECASE,
)


def _extract_frontend_types(filepath: Path) -> dict[str, set[str]]:
    """Extract TypeScript interface/type field names from a frontend file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    types: dict[str, set[str]] = {}
    for match in _TS_INTERFACE_RE.finditer(content):
        type_name = match.group(1)
        body = match.group(2)
        fields: set[str] = set()
        for field_match in _TS_FIELD_RE.finditer(body):
            fields.add(field_match.group(1))
        if fields:
            types[type_name] = fields

    return types


def _extract_api_calls(filepath: Path) -> list[str]:
    """Extract API endpoint paths called by a frontend file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    paths: list[str] = []
    for m in _FETCH_PATTERN.finditer(content):
        paths.append(m.group(1))
    return paths


def validate_frontend_contracts(
    root: Path,
    artifacts: list[SchemaArtifact],
    frontend_files: list[Path] | None = None,
) -> list[ContractViolation]:
    """Validate frontend DTO usage against backend schema artifacts.

    Checks:
    1. Frontend types that reference backend models have matching fields
    2. API calls target known endpoints
    3. Response DTOs cover all status codes
    """
    if not artifacts:
        return []

    # Build combined model map across all artifacts
    all_models: dict[str, ModelDef] = {}
    all_endpoints: dict[str, EndpointDef] = {}
    for art in artifacts:
        for name, model in art.models.items():
            all_models[name] = model
        for ep in art.endpoints:
            all_endpoints[ep.path] = ep

    if not all_models and not all_endpoints:
        return []

    # Discover frontend files if not provided
    if frontend_files is None:
        frontend_exts = {".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"}
        frontend_files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]
            for fname in filenames:
                if Path(fname).suffix in frontend_exts:
                    frontend_files.append(Path(dirpath) / fname)
            if len(frontend_files) >= 200:
                break

    violations: list[ContractViolation] = []
    model_names_lower = {k.lower(): k for k in all_models}

    for fpath in frontend_files:
        frontend_types = _extract_frontend_types(fpath)
        rel_path = str(fpath)

        for type_name, frontend_fields in frontend_types.items():
            # Fuzzy match: frontend CreateUserDto → backend User
            # or UserResponse → User
            matched_model: ModelDef | None = None
            lower_name = type_name.lower()

            # Direct match
            if type_name in all_models:
                matched_model = all_models[type_name]
            else:
                # Strip common suffixes: Dto, Response, Request, Input, Output, Type
                for suffix in ("dto", "response", "request", "input", "output", "type", "data",
                               "props", "params", "payload"):
                    stripped = lower_name.removesuffix(suffix)
                    for prefix in ("create", "update", "get", "list", "delete", ""):
                        candidate = stripped.removeprefix(prefix)
                        if candidate and candidate in model_names_lower:
                            matched_model = all_models[model_names_lower[candidate]]
                            break
                    if matched_model:
                        break

            if not matched_model:
                continue

            backend_fields = matched_model.field_names()

            # Check for extra fields (frontend has fields not in backend)
            extra = frontend_fields - backend_fields
            if extra:
                violations.append(ContractViolation(
                    file=rel_path,
                    line=0,
                    violation_type="extra_field",
                    detail=f"Frontend type '{type_name}' has fields not in backend model "
                           f"'{matched_model.name}': {', '.join(sorted(extra))}",
                    model_name=matched_model.name,
                    severity="T2",
                ))

            # Check for missing required fields
            required_backend = {
                f.name for f in matched_model.fields if not f.optional
            }
            missing = required_backend - frontend_fields
            if missing:
                violations.append(ContractViolation(
                    file=rel_path,
                    line=0,
                    violation_type="missing_field",
                    detail=f"Frontend type '{type_name}' is missing required fields from "
                           f"backend model '{matched_model.name}': {', '.join(sorted(missing))}",
                    model_name=matched_model.name,
                    severity="T1",
                ))

        # Validate API calls target known endpoints
        api_calls = _extract_api_calls(fpath)
        for call_path in api_calls:
            # Normalize path (strip query params, leading slash)
            clean_path = call_path.split("?")[0].split("#")[0]
            if not clean_path:
                continue

            # Check if any endpoint matches this path pattern
            matched = False
            for ep_path in all_endpoints:
                # Simple pattern matching: /users/:id ↔ /users/123
                ep_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', ep_path)
                ep_pattern = re.sub(r':[^/]+', r'[^/]+', ep_pattern)
                if re.fullmatch(ep_pattern, clean_path):
                    matched = True
                    break
                # Also check plain prefix match
                if clean_path.rstrip("/") == ep_path.rstrip("/"):
                    matched = True
                    break

            if not matched and all_endpoints:
                violations.append(ContractViolation(
                    file=rel_path,
                    line=0,
                    violation_type="unknown_endpoint",
                    detail=f"API call to '{call_path}' does not match any known backend endpoint. "
                           f"Known: {', '.join(sorted(all_endpoints.keys())[:5])}",
                    endpoint=call_path,
                    severity="T3",
                ))

    return violations


# ── Cache ────────────────────────────────────────────────────────

def save_contract_artifacts(root: Path, artifacts: list[SchemaArtifact]) -> Path:
    """Persist parsed contract artifacts to .uidetox/contracts.json."""
    from uidetox.state import ensure_uidetox_dir, _atomic_write_json
    uidetox_dir = ensure_uidetox_dir()
    out_path = uidetox_dir / "contracts.json"
    data = {
        "artifacts": [a.to_dict() for a in artifacts],
        "timestamp": __import__("uidetox.utils", fromlist=["now_iso"]).now_iso(),
    }
    _atomic_write_json(out_path, data, dir=uidetox_dir)
    return out_path


def load_contract_artifacts(root: Path) -> list[dict] | None:
    """Load cached contract artifacts if available."""
    from uidetox.state import get_uidetox_dir
    contracts_path = get_uidetox_dir() / "contracts.json"
    if not contracts_path.exists():
        return None
    try:
        data = json.loads(contracts_path.read_text(encoding="utf-8"))
        return data.get("artifacts", [])
    except (json.JSONDecodeError, OSError):
        return None
