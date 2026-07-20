"""Build and persist a semantic map of a frontend codebase.

The public seam is intentionally small: :func:`map_frontend` produces a
serializable :class:`FrontendMap`; save/load helpers persist that artifact.
Framework-specific parsing stays internal so callers do not need to understand
how evidence was extracted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from uidetox.analyzer_ast import ast_capabilities
from uidetox.frontend_semantics import ScriptSemantics, extract_script_semantics
from uidetox.project_map import build_project_map, project_source_manifest
from uidetox.runtime_observer import RuntimeObservation
from uidetox.source_facts import extract_source_facts
from uidetox.state import ensure_uidetox_dir, get_uidetox_dir
from uidetox.utils import now_iso


SCHEMA_VERSION = 1
EXTRACTOR_VERSION = 2
FRONTEND_MAP_FILE = "frontend-map.json"
MAX_SOURCE_BYTES = 1_000_000

SOURCE_EXTENSIONS = {
    ".astro",
    ".css",
    ".htm",
    ".html",
    ".js",
    ".jsx",
    ".less",
    ".sass",
    ".scss",
    ".svelte",
    ".ts",
    ".tsx",
    ".vue",
}

IGNORE_DIRS = {
    ".claude",
    ".cursor",
    ".git",
    ".next",
    ".nuxt",
    ".uidetox",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "vendor",
}

SCRIPT_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".astro"}
STYLE_EXTENSIONS = {".css", ".less", ".sass", ".scss"}

_COMPONENT_PATTERNS = (
    re.compile(
        r"(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Z][A-Za-z0-9_]*)\s*\("
    ),
    re.compile(
        r"(?:export\s+(?:default\s+)?)?const\s+([A-Z][A-Za-z0-9_]*)"
        r"(?:\s*:[^=]+)?\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
    ),
    re.compile(r"(?:export\s+(?:default\s+)?)?class\s+([A-Z][A-Za-z0-9_]*)\b"),
)
_IMPORT_PATTERN = re.compile(
    r"(?:import\s+(?:[\s\S]*?\s+from\s+)?|export\s+[\s\S]*?\s+from\s+|require\s*\()"
    r"[\"']([^\"']+)[\"']",
)
_JSX_TAG_PATTERN = re.compile(r"<([A-Z][A-Za-z0-9_.]*)\b")
_REGION_PATTERN = re.compile(
    r"<(header|nav|main|aside|section|article|footer|form|table|dialog)\b",
    re.IGNORECASE,
)
_ACTION_PATTERN = re.compile(
    r"\bon(Click|Submit|Change|Press|Focus|Blur|KeyDown|KeyUp|MouseEnter|MouseLeave)\s*=",
)
_STATE_PATTERN = re.compile(
    r"(?:const|let)\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*[A-Za-z_$][\w$]*\s*\]"
    r"\s*=\s*(?:React\.)?useState\b",
)
_FETCH_PATTERN = re.compile(r"\bfetch\s*\(\s*[\"'`]([^\"'`]+)[\"'`]")
_AXIOS_PATTERN = re.compile(
    r"\baxios\.(?:get|post|put|patch|delete)\s*\(\s*[\"'`]([^\"'`]+)[\"'`]",
    re.IGNORECASE,
)
_ROUTE_PATTERN = re.compile(
    r"<Route\b[^>]*\bpath\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)
_CONFIG_ROUTE_PATTERN = re.compile(r"\bpath\s*:\s*[\"']([^\"']+)[\"']")
_CSS_TOKEN_PATTERN = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}{]+)")


@dataclass(frozen=True)
class FrontendNode:
    """One mapped frontend concept with a source anchor."""

    id: str
    kind: str
    name: str
    file: str
    line: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrontendNode":
        return cls(
            id=str(value["id"]),
            kind=str(value["kind"]),
            name=str(value["name"]),
            file=str(value.get("file", "")),
            line=int(value.get("line", 0)),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class FrontendEdge:
    """Typed relationship between two frontend nodes."""

    source: str
    target: str
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrontendEdge":
        return cls(
            source=str(value["source"]),
            target=str(value["target"]),
            kind=str(value["kind"]),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class ExperienceContract:
    """Observed invariants and explicitly redesignable choices."""

    must_preserve: tuple[str, ...]
    may_change: tuple[str, ...]
    unknown: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExperienceContract":
        return cls(
            must_preserve=tuple(str(item) for item in value.get("must_preserve", [])),
            may_change=tuple(str(item) for item in value.get("may_change", [])),
            unknown=tuple(str(item) for item in value.get("unknown", [])),
        )


@dataclass(frozen=True)
class FrontendMap:
    """Serializable semantic graph consumed by redesign planning."""

    schema_version: int
    generated_at: str
    root: str
    target: str
    nodes: tuple[FrontendNode, ...]
    edges: tuple[FrontendEdge, ...]
    contracts: ExperienceContract
    fingerprint: dict[str, Any]
    evidence: dict[str, Any]
    project_map: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrontendMap":
        version = int(value.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported frontend map schema {version}; expected {SCHEMA_VERSION}."
            )
        return cls(
            schema_version=version,
            generated_at=str(value.get("generated_at", "")),
            root=str(value["root"]),
            target=str(value.get("target", ".")),
            nodes=tuple(
                FrontendNode.from_dict(item) for item in value.get("nodes", [])
            ),
            edges=tuple(
                FrontendEdge.from_dict(item) for item in value.get("edges", [])
            ),
            contracts=ExperienceContract.from_dict(dict(value.get("contracts", {}))),
            fingerprint=dict(value.get("fingerprint", {})),
            evidence=dict(value.get("evidence", {})),
            project_map=dict(value.get("project_map", {})),
        )


@dataclass
class _SourceRecord:
    path: Path
    relative_path: str
    content: str
    file_node_id: str
    component_ids: list[str] = field(default_factory=list)
    rendered_tags: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    semantics: ScriptSemantics | None = None
    extractor: str = "regex-fallback"
    confidence: float = 0.55


def map_frontend(
    root: str | Path,
    target: str | Path | None = None,
    runtime: RuntimeObservation | None = None,
) -> FrontendMap:
    """Map frontend structure, behavior, contracts, and design evidence.

    ``root`` defines source-anchor relativity. ``target`` may select a file or
    subdirectory but must remain inside ``root``. Optional ``runtime`` evidence
    enriches the same graph without exposing browser implementation details.
    """

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Project root is not a directory: {root_path}")

    scope = _resolve_scope(root_path, target)
    files = _discover_source_files(scope)
    nodes: list[FrontendNode] = []
    edges: list[FrontendEdge] = []
    records: list[_SourceRecord] = []
    unreadable_files: list[str] = []
    frameworks: set[str] = set()
    signal_counts: Counter[str] = Counter()
    extractor_counts: Counter[str] = Counter()
    component_name_ids: defaultdict[str, list[str]] = defaultdict(list)
    source_hashes: dict[str, str] = {}
    parse_error_files: list[str] = []

    for path in files:
        relative_path = path.relative_to(root_path).as_posix()
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                unreadable_files.append(relative_path)
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable_files.append(relative_path)
            continue

        source_hashes[relative_path] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
        source_facts = extract_source_facts(path, content)
        semantics = extract_script_semantics(path, content, facts=source_facts)
        extractor = semantics.extractor if semantics is not None else "regex-fallback"
        confidence = semantics.confidence if semantics is not None else 0.55
        extractor_counts[extractor] += 1
        if semantics is not None and semantics.parse_errors:
            parse_error_files.append(relative_path)
        framework = _detect_framework(path, relative_path, content)
        frameworks.add(framework)
        file_node_id = _node_id("file", relative_path, relative_path)
        nodes.append(
            FrontendNode(
                id=file_node_id,
                kind="file",
                name=path.name,
                file=relative_path,
                line=1,
                metadata={
                    "extension": path.suffix.lower(),
                    "framework": framework,
                    "extractor": extractor,
                    "confidence": confidence,
                },
            )
        )
        record = _SourceRecord(
            path=path,
            relative_path=relative_path,
            content=content,
            file_node_id=file_node_id,
            semantics=semantics,
            extractor=extractor,
            confidence=confidence,
        )
        records.append(record)

        components = (
            [(item.name, item.line) for item in semantics.components]
            if semantics is not None
            else _extract_components(path, relative_path, content)
        )
        for name, line in components:
            component_id = _node_id("component", relative_path, name)
            record.component_ids.append(component_id)
            component_name_ids[name].append(component_id)
            nodes.append(
                FrontendNode(
                    id=component_id,
                    kind="component",
                    name=name,
                    file=relative_path,
                    line=line,
                    metadata={
                        "framework": framework,
                        "extractor": extractor,
                        "confidence": confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(
                    file_node_id,
                    component_id,
                    "defines",
                    {"extractor": extractor, "confidence": confidence},
                )
            )

        owner_id = _primary_owner(record, nodes)
        record.rendered_tags = (
            list(semantics.rendered_tags)
            if semantics is not None
            else _unique(match.group(1) for match in _JSX_TAG_PATTERN.finditer(content))
        )
        source_imports = (
            list(semantics.imports)
            if semantics is not None
            else _unique(match.group(1) for match in _IMPORT_PATTERN.finditer(content))
        )
        if path.suffix.lower() in {".htm", ".html"}:
            source_imports.extend(_extract_html_asset_imports(content))
        record.imports = _unique(source_imports)

        regions = (
            [(item.name, item.line) for item in semantics.regions]
            if semantics is not None
            else [
                (match.group(1).lower(), _line_number(content, match.start()))
                for match in _REGION_PATTERN.finditer(content)
            ]
        )
        for index, (name, line) in enumerate(regions):
            region_id = _node_id("region", relative_path, name, index)
            nodes.append(
                FrontendNode(
                    id=region_id,
                    kind="region",
                    name=name,
                    file=relative_path,
                    line=line,
                    metadata={
                        "order": index,
                        "extractor": extractor,
                        "confidence": confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(owner_id, region_id, "contains", {"order": index})
            )
            signal_counts[name] += 1

        action_occurrences = (
            [(item.name, item.line) for item in semantics.actions]
            if semantics is not None
            else [
                (match.group(1), _line_number(content, match.start()))
                for match in _ACTION_PATTERN.finditer(content)
            ]
        )
        actions = Counter(name for name, _line in action_occurrences)
        for name, count in sorted(actions.items()):
            action_id = _node_id("action", relative_path, name)
            first_line = next(
                line for action_name, line in action_occurrences if action_name == name
            )
            nodes.append(
                FrontendNode(
                    id=action_id,
                    kind="action",
                    name=f"on{name}",
                    file=relative_path,
                    line=first_line,
                    metadata={
                        "occurrences": count,
                        "extractor": extractor,
                        "confidence": confidence,
                    },
                )
            )
            edges.append(FrontendEdge(owner_id, action_id, "exposes"))

        states = (
            [(item.name, item.line) for item in semantics.states]
            if semantics is not None
            else [
                (match.group(1), _line_number(content, match.start()))
                for match in _STATE_PATTERN.finditer(content)
            ]
        )
        for name, line in states:
            state_id = _node_id("state", relative_path, name)
            nodes.append(
                FrontendNode(
                    id=state_id,
                    kind="state",
                    name=name,
                    file=relative_path,
                    line=line,
                    metadata={"extractor": extractor, "confidence": confidence},
                )
            )
            edges.append(FrontendEdge(owner_id, state_id, "owns"))

        endpoint_occurrences = (
            [(item.name, item.line, item.method) for item in semantics.endpoints]
            if semantics is not None
            else [
                *(
                    (match.group(1), _line_number(content, match.start()), "GET")
                    for match in _FETCH_PATTERN.finditer(content)
                ),
                *(
                    (match.group(1), _line_number(content, match.start()), None)
                    for match in _AXIOS_PATTERN.finditer(content)
                ),
            ]
        )
        endpoints = {
            (endpoint, method): line for endpoint, line, method in endpoint_occurrences
        }
        endpoint_path_counts = Counter(endpoint for endpoint, _method in endpoints)
        for (endpoint, method), line in endpoints.items():
            identity = (
                endpoint
                if endpoint_path_counts[endpoint] == 1
                else f"{method or '?'}:{endpoint}"
            )
            data_id = _node_id("data", relative_path, identity)
            metadata = {
                "transport": "http",
                "extractor": extractor,
                "confidence": confidence,
            }
            if method is not None:
                metadata["method"] = method
            nodes.append(
                FrontendNode(
                    id=data_id,
                    kind="data",
                    name=endpoint,
                    file=relative_path,
                    line=line,
                    metadata=metadata,
                )
            )
            edges.append(FrontendEdge(owner_id, data_id, "reads"))

        routes = _extract_routes(
            path,
            relative_path,
            content,
            [item.name for item in semantics.routes] if semantics is not None else None,
        )
        for route in routes:
            route_id = _node_id("route", relative_path, route)
            nodes.append(
                FrontendNode(
                    id=route_id,
                    kind="route",
                    name=route,
                    file=relative_path,
                    line=(
                        next(
                            (
                                item.line
                                for item in semantics.routes
                                if item.name == route
                            ),
                            1,
                        )
                        if semantics is not None
                        else _first_endpoint_line(content, route)
                    ),
                    metadata={"extractor": extractor, "confidence": confidence},
                )
            )
            edges.append(FrontendEdge(route_id, owner_id, "renders"))

        if path.suffix.lower() in STYLE_EXTENSIONS:
            for match in _CSS_TOKEN_PATTERN.finditer(content):
                token_name = match.group(1)
                token_id = _node_id("token", relative_path, token_name)
                nodes.append(
                    FrontendNode(
                        id=token_id,
                        kind="token",
                        name=token_name,
                        file=relative_path,
                        line=_line_number(content, match.start()),
                        metadata={"value": match.group(2).strip()},
                    )
                )
                edges.append(FrontendEdge(file_node_id, token_id, "defines"))

        lowered = content.lower()
        for signal in (
            "card",
            "chart",
            "drawer",
            "grid",
            "hero",
            "modal",
            "sidebar",
            "table",
        ):
            signal_counts[signal] += lowered.count(signal)
        signal_counts["responsive"] += len(
            re.findall(r"(?:@media\b|\b(?:sm|md|lg|xl|2xl):)", content)
        )

    file_node_ids = {record.relative_path: record.file_node_id for record in records}
    external_nodes: dict[str, str] = {}
    edge_keys = {(edge.source, edge.target, edge.kind) for edge in edges}

    for record in records:
        owner_id = _primary_owner(record, nodes)
        for source in record.imports:
            resolved = _resolve_local_import(
                record.path,
                source,
                root_path,
                scope,
            )
            if resolved and resolved in file_node_ids:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(
                        record.file_node_id, file_node_ids[resolved], "imports"
                    ),
                )

        for tag in record.rendered_tags:
            candidates = component_name_ids.get(tag, [])
            if len(candidates) == 1:
                target_id = candidates[0]
            else:
                target_id = external_nodes.get(tag, "")
                if not target_id:
                    target_id = _node_id("external_component", "", tag)
                    external_nodes[tag] = target_id
                    nodes.append(
                        FrontendNode(
                            id=target_id,
                            kind="external_component",
                            name=tag,
                            file="",
                            line=0,
                            metadata={"confidence": 0.5},
                        )
                    )
            if target_id != owner_id:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(owner_id, target_id, "renders", {"confidence": 0.7}),
                )

    _merge_runtime_evidence(nodes, edges, edge_keys, runtime, signal_counts)
    nodes.sort(key=lambda node: (node.file, node.line, node.kind, node.name, node.id))
    edges.sort(key=lambda edge: (edge.source, edge.kind, edge.target))
    contracts = _build_contract(nodes)
    fingerprint = _build_fingerprint(nodes, signal_counts, len(records))
    target_label = (
        "." if scope == root_path else scope.relative_to(root_path).as_posix()
    )
    runtime_pages = tuple(runtime.pages) if runtime is not None else ()
    runtime_viewports = sorted({page.viewport.name for page in runtime_pages})
    runtime_urls = list(dict.fromkeys(page.url for page in runtime_pages))
    runtime_screenshots = [
        page.screenshot for page in runtime_pages if page.screenshot is not None
    ]
    runtime_findings = [
        {
            "url": page.url,
            "viewport": page.viewport.name,
            "selector": element.selector,
            "element": element.name or element.role or element.tag,
            **asdict(finding),
        }
        for page in runtime_pages
        for element in page.elements
        for finding in element.findings
    ]
    runtime_finding_counts = Counter(finding["code"] for finding in runtime_findings)
    project_map = build_project_map(root_path, nodes)

    return FrontendMap(
        schema_version=SCHEMA_VERSION,
        generated_at=now_iso(),
        root=str(root_path),
        target=target_label,
        nodes=tuple(nodes),
        edges=tuple(edges),
        contracts=contracts,
        fingerprint=fingerprint,
        evidence={
            "mode": "static+runtime" if runtime_pages else "static",
            "frameworks": sorted(frameworks),
            "files_mapped": len(records),
            "files_skipped": unreadable_files,
            "extractor_version": EXTRACTOR_VERSION,
            "extractors": dict(sorted(extractor_counts.items())),
            "parse_error_files": parse_error_files,
            "ast_capabilities": ast_capabilities(),
            "source_manifest": {
                "target": target_label,
                "files": dict(sorted(source_hashes.items())),
                "project_files": project_map.evidence.get("source_manifest", {}),
            },
            "source_status": "current",
            "runtime_observed": bool(runtime_pages),
            "runtime_status": "current" if runtime_pages else "absent",
            "runtime_generated_at": runtime.generated_at
            if runtime is not None
            else None,
            "runtime_pages": len(runtime_pages),
            "runtime_urls": runtime_urls,
            "runtime_viewports": runtime_viewports,
            "runtime_screenshots": runtime_screenshots,
            "runtime_finding_count": len(runtime_findings),
            "runtime_finding_counts": dict(sorted(runtime_finding_counts.items())),
            "runtime_findings": runtime_findings,
            "runtime_errors": list(runtime.errors) if runtime is not None else [],
        },
        project_map=project_map.to_dict(),
    )


def save_frontend_map(
    frontend_map: FrontendMap, path: str | Path | None = None
) -> Path:
    """Atomically persist ``frontend_map`` and return its path."""

    if path is None:
        ensure_uidetox_dir()
        output_path = get_uidetox_dir() / FRONTEND_MAP_FILE
    else:
        output_path = Path(path).expanduser().resolve()
    _atomic_write_json(output_path, frontend_map.to_dict())
    return output_path


def load_frontend_map(path: str | Path | None = None) -> FrontendMap:
    """Load a persisted frontend map, validating its schema."""

    input_path = (
        get_uidetox_dir() / FRONTEND_MAP_FILE
        if path is None
        else Path(path).expanduser().resolve()
    )
    try:
        value = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Frontend map not found: {input_path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Frontend map is unreadable: {input_path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Frontend map must contain a JSON object: {input_path}")
    return FrontendMap.from_dict(value)


def retain_runtime_evidence(
    previous: FrontendMap,
    refreshed: FrontendMap,
) -> FrontendMap:
    """Retain prior runtime provenance and label it stale after source changes."""

    if (
        previous.root != refreshed.root
        or previous.target != refreshed.target
        or not previous.evidence.get("runtime_observed")
    ):
        return refreshed
    previous_manifest = previous.evidence.get("source_manifest", {})
    refreshed_manifest = refreshed.evidence.get("source_manifest", {})
    previous_status = str(previous.evidence.get("runtime_status", "current"))
    same_source = previous_manifest == refreshed_manifest
    runtime_status = (
        "current" if same_source and previous_status == "current" else "stale"
    )
    evidence = dict(refreshed.evidence)
    for key, value in previous.evidence.items():
        if key.startswith("runtime_"):
            evidence[key] = value
    evidence["runtime_status"] = runtime_status
    evidence["runtime_observed"] = True
    evidence["runtime_stale_reason"] = (
        None
        if runtime_status == "current"
        else "Source manifest changed after the recorded runtime observation."
    )
    runtime_nodes = tuple(
        node for node in previous.nodes if node.kind.startswith("runtime_")
    )
    runtime_node_ids = {node.id for node in runtime_nodes}
    refreshed_node_ids = {node.id for node in refreshed.nodes}
    merged_nodes = refreshed.nodes + tuple(
        node for node in runtime_nodes if node.id not in refreshed_node_ids
    )

    refreshed_edge_keys = {
        (edge.source, edge.target, edge.kind) for edge in refreshed.edges
    }
    runtime_edges = tuple(
        edge
        for edge in previous.edges
        if edge.source in runtime_node_ids or edge.target in runtime_node_ids
    )
    merged_edges = refreshed.edges + tuple(
        edge
        for edge in runtime_edges
        if (edge.source, edge.target, edge.kind) not in refreshed_edge_keys
    )

    return replace(
        refreshed,
        nodes=merged_nodes,
        edges=merged_edges,
        evidence=evidence,
    )


def frontend_map_is_fresh(
    frontend_map: FrontendMap,
    root: str | Path | None = None,
    target: str | Path | None = None,
) -> bool:
    """Check extractor version and content hashes for every mapped source file."""
    if frontend_map.evidence.get("extractor_version") != EXTRACTOR_VERSION:
        return False
    expected = frontend_map.evidence.get("source_manifest")
    if (
        not isinstance(expected, dict)
        or not isinstance(expected.get("files"), dict)
        or not isinstance(expected.get("project_files"), dict)
    ):
        return False

    root_path = Path(root or frontend_map.root).expanduser().resolve()
    requested_target = frontend_map.target if target is None else target
    try:
        scope = _resolve_scope(root_path, requested_target)
    except ValueError:
        return False
    target_label = (
        "." if scope == root_path else scope.relative_to(root_path).as_posix()
    )
    if expected.get("target") != target_label:
        return False
    return expected["files"] == _build_source_manifest(root_path, scope) and expected[
        "project_files"
    ] == project_source_manifest(root_path)


def _resolve_scope(root: Path, target: str | Path | None) -> Path:
    if target is None or str(target).strip() in {"", "."}:
        return root
    candidate = Path(target).expanduser()
    scope = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        scope.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Target must be inside project root: {scope}") from exc
    if not scope.exists():
        raise ValueError(f"Frontend target does not exist: {scope}")
    return scope


def _discover_source_files(scope: Path) -> list[Path]:
    if scope.is_file():
        return [scope] if scope.suffix.lower() in SOURCE_EXTENSIONS else []

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in IGNORE_DIRS and not name.startswith(".")
        )
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                files.append(path.resolve())
    return files


def _build_source_manifest(root: Path, scope: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in _discover_source_files(scope):
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        manifest[path.relative_to(root).as_posix()] = hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()
    return dict(sorted(manifest.items()))


def _extract_components(
    path: Path, relative_path: str, content: str
) -> list[tuple[str, int]]:
    matches: list[tuple[int, str]] = []
    if path.suffix.lower() in SCRIPT_EXTENSIONS:
        for pattern in _COMPONENT_PATTERNS:
            matches.extend(
                (match.start(), match.group(1)) for match in pattern.finditer(content)
            )

    if not matches and path.suffix.lower() in {
        ".vue",
        ".svelte",
        ".astro",
        ".html",
        ".htm",
    }:
        matches.append((0, _component_name_from_path(path, relative_path)))
    elif (
        not matches
        and path.suffix.lower() in {".jsx", ".tsx"}
        and _JSX_TAG_PATTERN.search(content)
    ):
        matches.append((0, _component_name_from_path(path, relative_path)))

    components: list[tuple[str, int]] = []
    seen: set[str] = set()
    for start, name in sorted(matches):
        if name not in seen:
            seen.add(name)
            components.append((name, _line_number(content, start)))
    return components


def _component_name_from_path(path: Path, relative_path: str) -> str:
    stem = path.stem
    if stem.lower() in {"index", "page", "layout"}:
        parent = Path(relative_path).parent.name
        stem = f"{parent or 'Root'}-{stem}"
    parts = re.findall(r"[A-Za-z0-9]+", stem)
    return "".join(part[:1].upper() + part[1:] for part in parts) or "FrontendView"


def _detect_framework(path: Path, relative_path: str, content: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".vue":
        return "vue"
    if suffix == ".svelte":
        return "svelte"
    if suffix == ".astro":
        return "astro"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in STYLE_EXTENSIONS:
        return "styles"
    normalized = f"/{relative_path.lower()}"
    if re.search(r"/(?:app|pages)/", normalized) and path.stem in {
        "page",
        "layout",
        "index",
    }:
        return "next"
    if (
        "from 'react'" in content
        or 'from "react"' in content
        or suffix in {".jsx", ".tsx"}
    ):
        return "react"
    return "javascript"


def _extract_routes(
    path: Path,
    relative_path: str,
    content: str,
    syntax_routes: Iterable[str] | None = None,
) -> list[str]:
    routes = (
        list(syntax_routes)
        if syntax_routes is not None
        else [match.group(1) for match in _ROUTE_PATTERN.finditer(content)]
    )
    if syntax_routes is None and re.search(
        r"\b(?:createBrowserRouter|routes?|router)\b",
        content,
        re.IGNORECASE,
    ):
        routes.extend(
            match.group(1) for match in _CONFIG_ROUTE_PATTERN.finditer(content)
        )

    parts = Path(relative_path).parts
    suffix = path.suffix.lower()
    if suffix in SCRIPT_EXTENSIONS and "app" in parts and path.stem == "page":
        app_index = parts.index("app")
        route_parts = [
            _normalize_route_segment(part)
            for part in parts[app_index + 1 : -1]
            if not part.startswith("(") and not part.startswith("@")
        ]
        routes.append("/" + "/".join(part for part in route_parts if part))
    elif suffix in SCRIPT_EXTENSIONS and "pages" in parts:
        pages_index = parts.index("pages")
        page_parts = list(parts[pages_index + 1 :])
        if page_parts:
            page_parts[-1] = path.stem
            if page_parts[-1] == "index":
                page_parts.pop()
            routes.append(
                "/" + "/".join(_normalize_route_segment(part) for part in page_parts)
            )

    return _unique(route or "/" for route in routes)


def _normalize_route_segment(segment: str) -> str:
    if segment.startswith("[[...") and segment.endswith("]]"):
        return f":{segment[5:-2]}*"
    if segment.startswith("[...") and segment.endswith("]"):
        return f":{segment[4:-1]}*"
    if segment.startswith("[") and segment.endswith("]"):
        return f":{segment[1:-1]}"
    return segment


def _resolve_local_import(
    source_file: Path,
    import_path: str,
    root: Path,
    scope: Path,
) -> str | None:
    if import_path.startswith("/"):
        bases = [
            (scope / import_path.lstrip("/")).resolve(),
            (source_file.parent / import_path.lstrip("/")).resolve(),
        ]
    elif import_path.startswith("."):
        bases = [(source_file.parent / import_path).resolve()]
    else:
        return None
    candidates: list[Path] = []
    for base in dict.fromkeys(bases):
        candidates.append(base)
        if not base.suffix:
            candidates.extend(
                base.with_suffix(extension) for extension in sorted(SOURCE_EXTENSIONS)
            )
            candidates.extend(
                base / f"index{extension}" for extension in sorted(SOURCE_EXTENSIONS)
            )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.relative_to(root).as_posix()
            except ValueError:
                return None
    return None


def _extract_html_asset_imports(content: str) -> list[str]:
    imports: list[str] = []
    for match in re.finditer(r"<(script|link)\b[^>]*>", content, re.IGNORECASE):
        tag_name = match.group(1).lower()
        tag = match.group(0)
        if tag_name == "script":
            attribute = re.search(
                r"\bsrc\s*=\s*([\"'])([^\"']+)\1",
                tag,
                re.IGNORECASE,
            )
        else:
            relation = re.search(
                r"\brel\s*=\s*([\"'])([^\"']+)\1",
                tag,
                re.IGNORECASE,
            )
            if relation is None or not {
                "stylesheet",
                "modulepreload",
                "preload",
            }.intersection(relation.group(2).lower().split()):
                continue
            attribute = re.search(
                r"\bhref\s*=\s*([\"'])([^\"']+)\1",
                tag,
                re.IGNORECASE,
            )
        if attribute is None:
            continue
        source = attribute.group(2).split("?", 1)[0].split("#", 1)[0]
        if not source or source.startswith(("data:", "http://", "https://", "//")):
            continue
        if not source.startswith((".", "/")):
            source = f"./{source}"
        imports.append(source)
    return _unique(imports)


def _primary_owner(record: _SourceRecord, nodes: Iterable[FrontendNode]) -> str:
    if not record.component_ids:
        return record.file_node_id
    expected = _component_name_from_path(record.path, record.relative_path).lower()
    node_names = {
        node.id: node.name.lower() for node in nodes if node.id in record.component_ids
    }
    for component_id in record.component_ids:
        if node_names.get(component_id) == expected:
            return component_id
    return record.component_ids[0]


def _merge_runtime_evidence(
    nodes: list[FrontendNode],
    edges: list[FrontendEdge],
    edge_keys: set[tuple[str, str, str]],
    runtime: RuntimeObservation | None,
    signal_counts: Counter[str],
) -> None:
    if runtime is None:
        return

    for page in runtime.pages:
        page_key = f"{page.url}@{page.viewport.name}"
        page_id = _node_id("runtime_page", "", page_key)
        page_finding_count = sum(len(element.findings) for element in page.elements)
        nodes.append(
            FrontendNode(
                id=page_id,
                kind="runtime_page",
                name=page.url,
                file="",
                line=0,
                metadata={
                    "title": page.title,
                    "viewport": {
                        "name": page.viewport.name,
                        "width": page.viewport.width,
                        "height": page.viewport.height,
                    },
                    "screenshot": page.screenshot,
                    "finding_count": page_finding_count,
                },
            )
        )
        for element in page.elements:
            if element.kind == "action":
                node_kind = "runtime_action"
            elif element.kind == "text":
                node_kind = "runtime_text"
            else:
                node_kind = "runtime_region"
            element_key = element.selector or f"{element.tag}:{element.order}"
            element_id = _node_id(
                node_kind,
                page_key,
                element_key,
                element.order,
            )
            nodes.append(
                FrontendNode(
                    id=element_id,
                    kind=node_kind,
                    name=element.name or element.role or element.tag,
                    file="",
                    line=0,
                    metadata={
                        "runtime_url": page.url,
                        "viewport": page.viewport.name,
                        "selector": element.selector,
                        "tag": element.tag,
                        "role": element.role,
                        "order": element.order,
                        "bounds": element.bounds,
                        "styles": element.styles,
                        "states": element.states,
                        "measurements": element.measurements,
                        "findings": [asdict(finding) for finding in element.findings],
                    },
                )
            )
            _append_edge_once(
                edges,
                edge_keys,
                FrontendEdge(
                    page_id,
                    element_id,
                    "contains",
                    {"order": element.order, "viewport": page.viewport.name},
                ),
            )
            tag = element.tag.lower()
            role = element.role.lower()
            if tag in {"nav", "aside", "form", "table", "section", "article"}:
                signal_counts[tag] += 1
            if role == "navigation":
                signal_counts["nav"] += 1
            if role == "complementary":
                signal_counts["sidebar"] += 1
            if node_kind == "runtime_action":
                signal_counts["runtime_action"] += 1


def _build_contract(nodes: list[FrontendNode]) -> ExperienceContract:
    routes = sorted({node.name for node in nodes if node.kind == "route"})
    data_sources = sorted({node.name for node in nodes if node.kind == "data"})
    actions = sorted({node.name for node in nodes if node.kind == "action"})
    runtime_pages = [node for node in nodes if node.kind == "runtime_page"]
    runtime_routes = sorted({_runtime_route(node.name) for node in runtime_pages})
    runtime_actions = sorted(
        {
            (
                str(node.metadata.get("role", "action")) or "action",
                node.name,
            )
            for node in nodes
            if node.kind == "runtime_action" and node.name
        }
    )
    states = sorted(
        {
            node.name
            for node in nodes
            if node.kind == "state"
            and re.search(
                r"loading|error|empty|open|selected|success|pending",
                node.name,
                re.IGNORECASE,
            )
        }
    )
    regions = {node.name for node in nodes if node.kind == "region"}
    runtime_region_tags = {
        str(node.metadata.get("tag", ""))
        for node in nodes
        if node.kind == "runtime_region"
    }

    must_preserve = [f"Route remains reachable: {route}" for route in routes]
    must_preserve.extend(
        f"Observed runtime route remains reachable: {route}" for route in runtime_routes
    )
    must_preserve.extend(
        f"Data contract remains functional: {source}" for source in data_sources
    )
    must_preserve.extend(
        f"Interaction capability remains available: {action}" for action in actions
    )
    must_preserve.extend(
        f'Accessible runtime action remains available: {role} "{name}"'
        for role, name in runtime_actions[:40]
    )
    must_preserve.extend(
        f"User-visible state remains represented: {state}" for state in states
    )
    if "form" in regions or "form" in runtime_region_tags:
        must_preserve.append(
            "Form semantics, validation, and submission behavior remain functional."
        )

    if runtime_pages:
        unknown = [
            "Only initial runtime state was observed; triggered, authenticated, and failure states remain unknown.",
            "Source-to-runtime ownership remains inferred without source maps.",
            "Focus order and computed contrast still require dedicated runtime assertions.",
        ]
    else:
        unknown = [
            "Runtime-only states, overlays, and responsive transitions were not observed.",
            "Accessibility names, focus order, and computed contrast require runtime verification.",
        ]
    if not routes:
        if runtime_routes:
            unknown.append(
                "Runtime routes were observed, but their static route declarations were not resolved."
            )
        else:
            unknown.append(
                "No explicit route declarations were resolved from static source."
            )
    if not data_sources:
        unknown.append(
            "Dynamic or abstracted data dependencies may exist outside mapped call sites."
        )

    return ExperienceContract(
        must_preserve=tuple(_unique(must_preserve)),
        may_change=(
            "Information hierarchy and region order.",
            "Navigation archetype and page topology.",
            "Component partitioning and ownership.",
            "Visual language, density, spacing, and motion.",
            "Responsive composition while preserving capability parity.",
        ),
        unknown=tuple(unknown),
    )


def _build_fingerprint(
    nodes: list[FrontendNode], signal_counts: Counter[str], file_count: int
) -> dict[str, Any]:
    kinds = Counter(node.kind for node in nodes)
    regions = [node.name for node in nodes if node.kind == "region"]
    runtime_regions = [node for node in nodes if node.kind == "runtime_region"]
    observed_region_tags = [
        str(node.metadata.get("tag", "")) for node in runtime_regions
    ]
    observed_region_roles = [
        str(node.metadata.get("role", "")) for node in runtime_regions
    ]
    component_count = kinds["component"]
    runtime_action_keys = {
        (
            node.metadata.get("runtime_url", ""),
            node.metadata.get("selector", ""),
        )
        for node in nodes
        if node.kind == "runtime_action"
    }
    action_count = max(kinds["action"], len(runtime_action_keys))

    if (
        signal_counts["sidebar"]
        or "aside" in regions
        or "complementary" in observed_region_roles
    ):
        navigation = "sidebar"
    elif "nav" in regions or "navigation" in observed_region_roles:
        navigation = "top-nav"
    else:
        navigation = "none"

    if "form" in regions or "form" in observed_region_tags:
        archetype = "form-flow"
        interaction = "form-driven"
    elif (
        "table" in regions or "table" in observed_region_tags or signal_counts["chart"]
    ):
        archetype = "data-workspace"
        interaction = "data-exploration"
    elif signal_counts["hero"] or regions.count("section") >= 3:
        archetype = "sectioned-landing"
        interaction = "navigation"
    elif "article" in regions:
        archetype = "editorial"
        interaction = "reading"
    else:
        archetype = "generic-page"
        interaction = "direct-manipulation" if action_count >= 3 else "navigation"

    if component_count >= 12:
        partition = "many-small"
    elif component_count >= 4:
        partition = "modular"
    else:
        partition = "monolith"

    if action_count == 0:
        primary_action = "passive"
    elif action_count <= 3:
        primary_action = "focused"
    else:
        primary_action = "distributed"

    runtime_pages = [node for node in nodes if node.kind == "runtime_page"]
    runtime_element_count = kinds["runtime_region"] + kinds["runtime_action"]
    density_ratio = (
        runtime_element_count / len(runtime_pages)
        if runtime_pages
        else len(nodes) / max(1, file_count)
    )
    density = (
        "dense"
        if density_ratio >= 12
        else "balanced"
        if density_ratio >= 6
        else "sparse"
    )
    runtime_viewports = {
        str(node.metadata.get("viewport", {}).get("name", "")) for node in runtime_pages
    }
    runtime_layouts: defaultdict[str, list[str]] = defaultdict(list)
    for node in runtime_regions:
        key = f"{node.metadata.get('runtime_url', '')}@{node.metadata.get('viewport', '')}"
        runtime_layouts[key].append(
            str(node.metadata.get("role") or node.metadata.get("tag") or node.name)
        )

    return {
        "topology": archetype,
        "navigation": navigation,
        "component_partition": partition,
        "primary_action": primary_action,
        "interaction": interaction,
        "responsive": (
            "observed-responsive"
            if len(runtime_viewports - {""}) >= 2
            else "breakpoint-driven"
            if signal_counts["responsive"]
            else "unknown"
        ),
        "density": density,
        "layout_sequence": regions,
        "runtime_layout_sequences": dict(sorted(runtime_layouts.items())),
        "node_counts": dict(sorted(kinds.items())),
        "signals": dict(sorted(signal_counts.items())),
    }


def _runtime_route(url: str) -> str:
    parsed = urlsplit(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _node_id(kind: str, file_path: str, name: str, ordinal: int = 0) -> str:
    raw = f"{kind}\0{file_path}\0{name}\0{ordinal}".encode("utf-8")
    return f"{kind}:{hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:12]}"


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, max(0, offset)) + 1


def _first_endpoint_line(content: str, value: str) -> int:
    offset = content.find(value)
    return _line_number(content, offset) if offset >= 0 else 1


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _append_edge_once(
    edges: list[FrontendEdge],
    edge_keys: set[tuple[str, str, str]],
    edge: FrontendEdge,
) -> None:
    key = (edge.source, edge.target, edge.kind)
    if key not in edge_keys:
        edge_keys.add(key)
        edges.append(edge)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.stem}_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
