"""Build and persist a semantic map of a frontend codebase.

The public seam is intentionally small: :func:`map_frontend` produces a
serializable :class:`FrontendMap`; save/load helpers persist that artifact.
Framework-specific parsing stays internal so callers do not need to understand
how evidence was extracted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from uidetox.analyzer_ast import ast_capabilities
from uidetox.design_semantics import (
    detect_design_findings,
    detect_navigation_continuity_findings,
)
from uidetox.experience_states import normalize_experience_state
from uidetox.fileset import ProjectFileSet
from uidetox.findings import Finding
from uidetox.persistence import atomic_replace_text
from uidetox.project_map import build_project_map, project_source_manifest
from uidetox.runtime_observer import RuntimeObservation, RuntimePage
from uidetox.runtime_scenarios import RuntimeCaptureRecord, RuntimeDiagnostic
from uidetox.semantic_adapters import (
    ApplicationSemantics,
    ModuleSemantics,
    SourceDocument,
    build_application_semantics,
)
from uidetox.source_facts import literal_nested_object_strings
from uidetox.state import _load_json_object, ensure_uidetox_dir, get_uidetox_dir
from uidetox.utils import now_iso

SCHEMA_VERSION = 1
EXTRACTOR_VERSION = 3
FRONTEND_MAP_FILE = "frontend-map.json"
MAX_SOURCE_BYTES = 1_000_000

STYLE_EXTENSIONS = {".css", ".less", ".sass", ".scss"}

_CSS_TOKEN_PATTERN = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}{]+)")

_HTTP_LITERAL_HEADERS = (
    "Accept",
    "Content-Type",
    "Idempotency-Key",
    "If-Match",
    "If-None-Match",
)
_DIAGNOSTIC_CATEGORIES = {
    "action": "interaction",
    "console": "runtime",
    "coverage": "coverage",
    "network": "integration",
    "page": "runtime",
}


def _network_call_scope(content: str, facts: Any, call: Any) -> str:
    lines = content.splitlines(keepends=True)
    owner_starts = [
        item.line
        for item in facts.callables
        if item.name == call.owner and item.line <= call.line
    ]
    if not owner_starts:
        return ""
    start = max(owner_starts) - 1
    later_starts = [item.line - 1 for item in facts.callables if item.line > call.line]
    end = min(later_starts, default=len(lines))
    return "".join(lines[start:end])


def _fetch_response_binding(scope: str, call: Any) -> str | None:
    if call.target != "fetch" or not isinstance(call.url, str):
        return None
    pattern = re.compile(
        rf"\b(?:const|let|var)\s+(?P<binding>[A-Za-z_$][\w$]*)\s*=\s*"
        rf"(?:await\s+)?fetch\s*\(\s*([\"']){re.escape(call.url)}\2",
        re.DOTALL,
    )
    bindings = {match.group("binding") for match in pattern.finditer(scope)}
    return next(iter(bindings)) if len(bindings) == 1 else None


def _frontend_http_lineage(
    facts: Any,
    call: Any,
    content: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    source_calls = tuple(
        source_call
        for source_call in facts.calls
        if source_call.target == call.target and source_call.line == call.line
    )
    if len(source_calls) != 1 or len(source_calls[0].arguments) < 2:
        return (), ()
    options = source_calls[0].arguments[1]
    if not options.lstrip().startswith("{") or not options.rstrip().endswith("}"):
        return (), ()

    lineage: list[dict[str, Any]] = []
    headers = literal_nested_object_strings(
        options,
        facts.extension,
        "headers",
        _HTTP_LITERAL_HEADERS,
    )
    content_type = headers.get("Content-Type")
    if content_type:
        lineage.append(
            {
                "kind": "request_media_type",
                "name": content_type,
                "ref": f"request_media_type:{content_type}",
                "provenance": "frontend-source:literal-header",
                "edge": "accepts_media_type",
            }
        )
    for name in sorted(headers):
        if name in {"Accept", "Content-Type"}:
            continue
        lineage.append(
            {
                "kind": "api_parameter",
                "name": name,
                "ref": f"api_parameter:header:{name}",
                "location": "header",
                "provenance": "frontend-source:literal-header",
                "edge": "declares_parameter",
            }
        )

    response_scope = _network_call_scope(content, facts, call)
    response_binding = _fetch_response_binding(response_scope, call)
    statuses = ()
    if response_binding is not None:
        status_pattern = re.compile(
            rf"\b{re.escape(response_binding)}\.status\s*"
            r"(?:===?|!==?)\s*([1-5][0-9]{2})\b"
        )
        statuses = tuple(sorted(set(status_pattern.findall(response_scope))))
    accept = headers.get("Accept")
    response_parsers = {
        parser
        for parser in ("json", "text")
        if response_binding is not None
        and re.search(
            rf"\b{re.escape(response_binding)}\.{parser}\s*\(",
            response_scope,
        )
    }
    parser_matches_accept = (
        len(response_parsers) == 1
        and accept is not None
        and "," not in accept
        and (
            (response_parsers == {"json"} and "json" in accept.lower())
            or (response_parsers == {"text"} and accept.lower().startswith("text/"))
        )
    )
    if parser_matches_accept:
        for status in statuses:
            lineage.append(
                {
                    "kind": "response_media_type",
                    "name": accept,
                    "ref": f"response_media_type:{status}:{accept}",
                    "status": status,
                    "provenance": "frontend-source:literal-header",
                    "edge": "returns_media_type",
                }
            )

    obligation_names = set()
    if "Idempotency-Key" in headers:
        obligation_names.add("idempotency")
    if re.search(r"(?:^|[,\s{])signal\s*(?::|[,}])", options):
        obligation_names.add("cancellation")
    if set(statuses) & {"409", "412"}:
        obligation_names.add("conflict")
    for name in sorted(obligation_names):
        lineage.append(
            {
                "kind": "operation_obligation",
                "name": name,
                "ref": f"operation_obligation:{name}",
                "applicable": None,
                "capability_status": "unknown",
                "evidence_status": "transport-token-only",
                "provenance": "frontend-source:transport-token",
                "edge": "requires_behavior",
            }
        )
    return tuple(lineage), statuses


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
    def from_dict(cls, value: dict[str, Any]) -> FrontendNode:
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
    def from_dict(cls, value: dict[str, Any]) -> FrontendEdge:
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
    def from_dict(cls, value: dict[str, Any]) -> ExperienceContract:
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
    def from_dict(cls, value: dict[str, Any]) -> FrontendMap:
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
    module: ModuleSemantics
    component_ids: dict[str, str] = field(default_factory=dict)


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
    file_set = ProjectFileSet(
        root_path,
        explicit_targets=(scope,) if scope.is_file() else None,
        scope_root=root_path if scope.is_file() else scope,
    )
    files = file_set.discover()
    nodes: list[FrontendNode] = []
    edges: list[FrontendEdge] = []
    unreadable_files: list[str] = []
    signal_counts: Counter[str] = Counter()
    source_hashes: dict[str, str] = {}
    documents: list[SourceDocument] = []

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
        documents.append(SourceDocument(path, relative_path, content))

    application = build_application_semantics(root_path, scope, documents)
    records: list[_SourceRecord] = []
    extractor_counts: Counter[str] = Counter()
    parse_error_files: list[str] = []

    for document in documents:
        path = document.path
        relative_path = document.relative_path
        content = document.content
        module = application.module(relative_path)
        if module is None:
            continue
        facts = module.facts
        extractor_counts[facts.extractor] += 1
        if facts.parse_errors:
            parse_error_files.append(relative_path)
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
                    "framework": module.framework,
                    "extractor": facts.extractor,
                    "confidence": facts.confidence,
                    "adapter": module.capability.adapter,
                    "capability": module.capability.to_dict(),
                },
            )
        )
        record = _SourceRecord(
            path=path,
            relative_path=relative_path,
            content=content,
            file_node_id=file_node_id,
            module=module,
        )
        records.append(record)

        for component in facts.declared_ui_modules:
            component_id = _node_id(
                "component",
                relative_path,
                component.name,
            )
            record.component_ids[component.name] = component_id
            nodes.append(
                FrontendNode(
                    id=component_id,
                    kind="component",
                    name=component.name,
                    file=relative_path,
                    line=component.line,
                    metadata={
                        "framework": module.framework,
                        "exports": [
                            item.exported
                            for item in facts.exports
                            if item.local == component.name and item.source is None
                        ],
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(
                    file_node_id,
                    component_id,
                    "defines",
                    {
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
                )
            )

        owner_id = _primary_owner(record)
        for index, region in enumerate(facts.regions):
            region_id = _node_id("region", relative_path, region.name, index)
            nodes.append(
                FrontendNode(
                    id=region_id,
                    kind="region",
                    name=region.name,
                    file=relative_path,
                    line=region.line,
                    metadata={
                        "order": index,
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(owner_id, region_id, "contains", {"order": index})
            )
            signal_counts[region.name] += 1

        ui_owners = set(record.component_ids)
        actions: dict[tuple[str, str, str], list[int]] = {}
        ui_actions_by_call_owner: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for action in facts.actions:
            key = (action.owner, action.name, action.target)
            summary = actions.setdefault(key, [action.line, 0])
            summary[1] += 1
            ui_actions_by_call_owner[action.owner][action.owner].add(action.name)
            # Empty targets collapse onto the already-indexed direct owner.
            ui_actions_by_call_owner[action.target or action.owner][action.owner].add(
                action.name
            )

        for (
            action_owner,
            name,
            action_target,
        ), (first_line, count) in sorted(actions.items()):
            action_id = _node_id(
                "action",
                relative_path,
                f"{action_owner}:{name}:{action_target}",
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
                        "owner": action_owner,
                        "target": action_target,
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(
                    record.component_ids.get(action_owner, owner_id),
                    action_id,
                    "exposes",
                )
            )

        ui_states_by_owner: dict[str, set[str]] = defaultdict(set)
        for state in facts.states:
            ui_states_by_owner[state.owner].update(
                filter(None, (normalize_experience_state(state.name),))
            )
            state_id = _node_id("state", relative_path, state.owner, state.name)
            nodes.append(
                FrontendNode(
                    id=state_id,
                    kind="state",
                    name=state.name,
                    file=relative_path,
                    line=state.line,
                    metadata={
                        "owner": state.owner,
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
                )
            )
            edges.append(
                FrontendEdge(
                    record.component_ids.get(state.owner, owner_id),
                    state_id,
                    "owns",
                )
            )

        call_count = len(facts.network_calls)

        def ui_owner_for_call(
            call_owner: str,
            ui_owners: set[str] = ui_owners,
            ui_actions_by_call_owner: dict[
                str, dict[str, set[str]]
            ] = ui_actions_by_call_owner,
        ) -> str:
            if call_owner in ui_owners:
                return call_owner
            owners = ui_actions_by_call_owner.get(call_owner, {}).keys() & ui_owners
            return next(iter(owners)) if len(owners) == 1 else ""

        call_ui_owners = {
            index: ui_owner_for_call(call.owner)
            for index, call in enumerate(facts.network_calls)
        }
        call_counts_by_ui_owner = Counter(
            owner for owner in call_ui_owners.values() if owner
        )
        mutation_count = sum(
            call.method not in {None, "GET", "HEAD", "OPTIONS"}
            for call in facts.network_calls
        )
        cache_evidence = bool(
            re.search(
                r"\b(?:invalidateQueries|invalidateTags|mutate|refetch)\s*\(",
                content,
            )
        )
        auth_evidence = bool(
            re.search(r"\b(?:Authorization|credentials)\b\s*[:=]", content)
        )
        for index, call in enumerate(facts.network_calls):
            name = call.url or call.url_expression or call.target
            identity = f"{call.target}:{call.method or '?'}:{name}:{call.line}:{index}"
            data_id = _node_id("data", relative_path, identity)
            call_ui_owner = call_ui_owners[index]
            attributable_ui = bool(
                call_ui_owner and call_counts_by_ui_owner[call_ui_owner] == 1
            )
            state_names = ui_states_by_owner.get(call_ui_owner, set())
            action_names = ui_actions_by_call_owner.get(call.owner, {}).get(
                call_ui_owner, set()
            )
            request_contracts = {
                reference: module.contracts[reference]
                for reference in call.request_type_refs
                if reference in module.contracts
            }
            response_contracts = {
                reference: module.contracts[reference]
                for reference in call.response_type_refs
                if reference in module.contracts
            }
            operation_lineage, handled_statuses = _frontend_http_lineage(
                facts,
                call,
                content,
            )
            metadata = {
                "transport": (
                    "graphql"
                    if call.client_family == "apollo"
                    else (
                        "query"
                        if call.client_family in {"rtk-query", "tanstack-query"}
                        else "http"
                    )
                ),
                "client_family": call.client_family,
                "dynamic": call.dynamic and call.url is None,
                "value_dynamic": call.dynamic,
                "resolution": call.resolution,
                "url_expression": call.url_expression,
                "unresolved_evidence": call.unresolved_evidence,
                "request_type_refs": list(call.request_type_refs),
                "response_type_refs": list(call.response_type_refs),
                "request_contracts": request_contracts,
                "response_contracts": response_contracts,
                "lineage": list(operation_lineage),
                "status_codes": list(handled_statuses),
                "ui_actions": (sorted(action_names) if attributable_ui else []),
                "ui_states": sorted(state_names) if attributable_ui else [],
                "ui_lifecycle_evidence": (
                    "present"
                    if attributable_ui and state_names
                    else "absent"
                    if attributable_ui or not call_ui_owner
                    else "unknown"
                ),
                "mutation": call.method not in {None, "GET", "HEAD", "OPTIONS"},
                "cache_invalidation": (
                    "present"
                    if cache_evidence and mutation_count == 1
                    else (
                        "absent"
                        if call.method not in {None, "GET", "HEAD", "OPTIONS"}
                        and not cache_evidence
                        else "unknown"
                    )
                ),
                "auth": (
                    "present"
                    if auth_evidence and call_count == 1
                    else "absent"
                    if call_count == 1
                    else "unknown"
                ),
                "authorization": (
                    "absent" if not auth_evidence and call_count == 1 else "unknown"
                ),
                "tenant": (
                    "absent" if not auth_evidence and call_count == 1 else "unknown"
                ),
                "ui_required": bool(call_ui_owner),
                "owner": call.owner,
                "ui_owner": call_ui_owner,
                "extractor": facts.extractor,
                "confidence": facts.confidence,
            }
            if call.method is not None:
                metadata["method"] = call.method
            nodes.append(
                FrontendNode(
                    id=data_id,
                    kind="data",
                    name=name,
                    file=relative_path,
                    line=call.line,
                    metadata=metadata,
                )
            )
            edges.append(
                FrontendEdge(
                    record.component_ids.get(call_ui_owner, owner_id),
                    data_id,
                    "reads",
                )
            )

        for route in facts.routes:
            route_id = _node_id("route", relative_path, route.name)
            nodes.append(
                FrontendNode(
                    id=route_id,
                    kind="route",
                    name=route.name,
                    file=relative_path,
                    line=route.line,
                    metadata={
                        "extractor": facts.extractor,
                        "confidence": facts.confidence,
                    },
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
    component_ids = {
        (record.relative_path, local_name): component_id
        for record in records
        for local_name, component_id in record.component_ids.items()
    }
    external_nodes: dict[str, str] = {}
    unresolved_nodes: dict[tuple[str, str], str] = {}
    edge_keys = {(edge.source, edge.target, edge.kind) for edge in edges}

    for record in records:
        owner_id = _primary_owner(record)
        for source in record.module.facts.imports:
            resolved = application.resolve_import(record.relative_path, source)
            if resolved and resolved in file_node_ids:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(
                        record.file_node_id, file_node_ids[resolved], "imports"
                    ),
                )

        for rendered in record.module.facts.rendered_bindings:
            resolved = application.resolve_render(
                record.relative_path,
                rendered.binding,
            )
            if (
                resolved.status == "resolved"
                and resolved.module_path is not None
                and resolved.local_name is not None
            ):
                target_id = component_ids.get(
                    (resolved.module_path, resolved.local_name),
                    "",
                )
                if not target_id:
                    continue
            elif resolved.status == "external" and resolved.package:
                external_key = f"{resolved.package}:{resolved.export_name}"
                target_id = external_nodes.get(external_key, "")
                if not target_id:
                    target_id = _node_id("external_component", "", external_key)
                    external_nodes[external_key] = target_id
                    nodes.append(
                        FrontendNode(
                            id=target_id,
                            kind="external_component",
                            name=rendered.binding,
                            file="",
                            line=0,
                            metadata={
                                "package": resolved.package,
                                "export": resolved.export_name,
                                "confidence": resolved.confidence,
                                "provenance": resolved.provenance,
                            },
                        )
                    )
            else:
                unresolved_key = (record.relative_path, rendered.binding)
                target_id = unresolved_nodes.get(unresolved_key, "")
                if not target_id:
                    target_id = _node_id(
                        "unresolved_component",
                        record.relative_path,
                        rendered.binding,
                    )
                    unresolved_nodes[unresolved_key] = target_id
                    nodes.append(
                        FrontendNode(
                            id=target_id,
                            kind="unresolved_component",
                            name=rendered.binding,
                            file=record.relative_path,
                            line=rendered.line,
                            metadata={
                                "confidence": 0.0,
                                "provenance": resolved.provenance,
                            },
                        )
                    )
            if target_id != owner_id:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(
                        owner_id,
                        target_id,
                        "renders",
                        {
                            "confidence": resolved.confidence,
                            "provenance": resolved.provenance,
                        },
                    ),
                )

    runtime_pages = _merge_runtime_evidence(
        nodes,
        edges,
        edge_keys,
        runtime,
        signal_counts,
        application,
    )
    nodes.sort(key=lambda node: (node.file, node.line, node.kind, node.name, node.id))
    edges.sort(key=lambda edge: (edge.source, edge.kind, edge.target))
    contracts = _build_contract(nodes)
    fingerprint = _build_fingerprint(nodes, signal_counts, len(records))
    target_label = (
        "." if scope == root_path else scope.relative_to(root_path).as_posix()
    )
    runtime_viewports = sorted({page.viewport.name for page in runtime_pages})
    runtime_urls = list(runtime.requested_urls) if runtime is not None else []
    runtime_screenshots = [
        page.screenshot for page in runtime_pages if page.screenshot is not None
    ]
    runtime_captures = tuple(runtime.captures) if runtime is not None else ()
    element_runtime_findings = [
        {
            "url": page.url,
            "viewport": page.viewport.name,
            "scenario": page.scenario,
            "state": page.state,
            "capture_id": page.capture_id,
            "selector": element.selector,
            "element": element.name or element.role or element.tag,
            **finding.with_runtime_anchor(
                url=page.url,
                viewport=page.viewport.name,
                selector=element.selector,
                scenario=page.scenario,
                state=page.state,
                capture_id=page.capture_id,
            ).to_dict(),
        }
        for page in runtime_pages
        for element in page.elements
        for finding in element.findings
    ]
    diagnostic_runtime_findings = [
        {
            **dict(finding.runtime_anchor),
            "selector": "",
            "element": finding.evidence.get("kind", "browser"),
            **finding.to_dict(),
        }
        for finding in _runtime_diagnostic_findings(runtime_captures)
    ]
    runtime_findings = [*element_runtime_findings, *diagnostic_runtime_findings]
    runtime_finding_counts = Counter(finding["code"] for finding in runtime_findings)
    runtime_diagnostics = [
        asdict(diagnostic)
        for capture in runtime_captures
        for diagnostic in capture.diagnostics
    ]
    runtime_status_counts = Counter(capture.status for capture in runtime_captures)
    runtime_coverage = {
        "requested": len(runtime_captures),
        "completed": runtime_status_counts["completed"],
        "failed": runtime_status_counts["failed"],
        "truncated": sum(capture.coverage.truncated for capture in runtime_captures),
        "total": sum(capture.coverage.total for capture in runtime_captures),
        "candidates": sum(capture.coverage.candidates for capture in runtime_captures),
        "eligible": sum(capture.coverage.eligible for capture in runtime_captures),
        "emitted": sum(capture.coverage.emitted for capture in runtime_captures),
    }
    runtime_semantic_coverage = _runtime_semantic_coverage(runtime_pages)
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
            "mode": "static+runtime" if runtime is not None else "static",
            "frameworks": sorted({module.framework for module in application.modules}),
            "files_mapped": len(records),
            "files_skipped": unreadable_files,
            "extractor_version": EXTRACTOR_VERSION,
            "extractors": dict(sorted(extractor_counts.items())),
            "parse_error_files": parse_error_files,
            "adapter_capabilities": _adapter_capability_summary(application.modules),
            "adapter_status_counts": dict(
                sorted(
                    Counter(
                        module.capability.status for module in application.modules
                    ).items()
                )
            ),
            "semantic_counts": {
                "modules": len(application.modules),
                "components": sum(
                    len(module.facts.declared_ui_modules)
                    for module in application.modules
                ),
                "network_calls": sum(
                    len(module.facts.network_calls) for module in application.modules
                ),
                "selectors": sum(
                    len(module.facts.selectors) for module in application.modules
                ),
            },
            "resolution_issues": list(application.resolution_issues),
            "ast_capabilities": ast_capabilities(),
            "source_manifest": {
                "target": target_label,
                "files": dict(sorted(source_hashes.items())),
                "project_files": project_map.evidence.get("source_manifest", {}),
            },
            "source_status": "current",
            "runtime_observed": bool(runtime_pages),
            "runtime_status": runtime.status if runtime is not None else "absent",
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
            "runtime_capture_matrix": [asdict(capture) for capture in runtime_captures],
            "runtime_diagnostics": runtime_diagnostics,
            "runtime_coverage": runtime_coverage,
            "runtime_semantic_coverage": runtime_semantic_coverage,
            "runtime_viewport_discovery": (
                asdict(runtime.viewport_discovery)
                if runtime is not None and runtime.viewport_discovery is not None
                else None
            ),
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
    return FrontendMap.from_dict(_load_json_object(input_path, "Frontend map"))


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
    runtime_status = previous_status if same_source else "stale"
    evidence = dict(refreshed.evidence)
    for key, value in previous.evidence.items():
        if key.startswith("runtime_"):
            evidence[key] = value
    evidence["runtime_status"] = runtime_status
    evidence["runtime_observed"] = True
    evidence["runtime_stale_reason"] = (
        None if same_source else "Source manifest changed after runtime observation."
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


def _build_source_manifest(root: Path, scope: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    files = ProjectFileSet(
        root,
        explicit_targets=(scope,) if scope.is_file() else None,
        scope_root=root if scope.is_file() else scope,
    ).discover()
    for path in files:
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


def _primary_owner(record: _SourceRecord) -> str:
    if not record.component_ids:
        return record.file_node_id
    default_component = next(
        (
            item.local
            for item in record.module.facts.exports
            if item.exported == "default" and item.local in record.component_ids
        ),
        None,
    )
    if default_component is not None:
        return record.component_ids[default_component]
    return next(iter(record.component_ids.values()))


def _adapter_capability_summary(
    modules: tuple[ModuleSemantics, ...],
) -> dict[str, dict[str, Any]]:
    rank = {"native": 0, "degraded": 1, "unsupported": 2}
    grouped: dict[str, list[ModuleSemantics]] = {}
    for module in modules:
        grouped.setdefault(module.framework, []).append(module)
    summary: dict[str, dict[str, Any]] = {}
    for framework, items in sorted(grouped.items()):
        status = max(
            (item.capability.status for item in items),
            key=rank.__getitem__,
        )
        summary[framework] = {
            "status": status,
            "files": len(items),
            "adapters": sorted({item.capability.adapter for item in items}),
            "reasons": sorted({item.capability.reason for item in items}),
            "confidence": min(item.capability.confidence for item in items),
        }
    return summary


def _runtime_diagnostic_finding(
    diagnostic: RuntimeDiagnostic,
    capture: RuntimeCaptureRecord,
) -> Finding:
    anchor = {
        "url": diagnostic.url,
        "viewport": diagnostic.viewport,
        "scenario": diagnostic.scenario,
        "state": diagnostic.state,
        "source": diagnostic.source,
        "capture_id": capture.capture_id,
    }
    return Finding.create(
        detector_id=diagnostic.code,
        category=_DIAGNOSTIC_CATEGORIES.get(diagnostic.kind, "runtime"),
        severity=diagnostic.severity,
        confidence=1.0,
        message=diagnostic.message,
        provenance="runtime",
        evidence={
            "kind": diagnostic.kind,
            "source": diagnostic.source,
        },
        runtime_anchor=anchor,
        suppression_key=(
            f"{diagnostic.code}:{diagnostic.scenario}:{diagnostic.state}:"
            f"{diagnostic.url}:{diagnostic.viewport}:{diagnostic.source}"
        ),
        verifier={
            "kind": "runtime",
            "detector_id": diagnostic.code,
            **anchor,
        },
    )


def _runtime_diagnostic_findings(
    captures: Iterable[RuntimeCaptureRecord],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    seen: set[tuple[str, ...]] = set()
    for capture in captures:
        for diagnostic in capture.diagnostics:
            key = (
                diagnostic.code,
                diagnostic.kind,
                diagnostic.message,
                diagnostic.scenario,
                diagnostic.state,
                diagnostic.url,
                diagnostic.viewport,
                diagnostic.source,
            )
            if key in seen:
                continue
            seen.add(key)
            findings.append(_runtime_diagnostic_finding(diagnostic, capture))
    return tuple(findings)


def _runtime_semantic_coverage(pages: Iterable[Any]) -> dict[str, int]:
    coverage = Counter(
        {
            "elements": 0,
            "equivalence_grouped": 0,
            "paint_resolved": 0,
            "paint_unresolved": 0,
            "paint_unobserved": 0,
        }
    )
    for page in pages:
        for element in page.elements:
            coverage["elements"] += 1
            measurements = element.measurements
            if measurements.get("equivalenceGroup"):
                coverage["equivalence_grouped"] += 1
            paint = measurements.get("paint")
            if not isinstance(paint, dict):
                coverage["paint_unobserved"] += 1
                continue
            foreground = paint.get("foreground")
            layers = paint.get("background_layers")
            unresolved = paint.get("unresolved")
            resolved = (
                isinstance(foreground, dict)
                and isinstance(foreground.get("rgba"), list)
                and isinstance(layers, list)
                and bool(layers)
                and all(
                    isinstance(layer, dict) and isinstance(layer.get("rgba"), list)
                    for layer in layers
                )
                and not unresolved
            )
            coverage["paint_resolved" if resolved else "paint_unresolved"] += 1
    return dict(coverage)


def _merge_runtime_evidence(
    nodes: list[FrontendNode],
    edges: list[FrontendEdge],
    edge_keys: set[tuple[str, str, str]],
    runtime: RuntimeObservation | None,
    signal_counts: Counter[str],
    application: ApplicationSemantics,
) -> tuple[RuntimePage, ...]:
    if runtime is None:
        return ()

    enriched_pages: list[RuntimePage] = []
    navigation_findings = (
        detect_navigation_continuity_findings(runtime.pages)
        if runtime.status == "current"
        else tuple(tuple(() for _element in page.elements) for page in runtime.pages)
    )
    for page_index, page in enumerate(runtime.pages):
        route_sources = application.route_sources(page.url)
        ownerships = tuple(
            application.source_ownership(
                selector=element.selector,
                tag=element.tag,
                source_hint=element.source_hint,
                source_selectors=element.source_selectors,
                runtime_url=page.url,
                route_sources=route_sources,
            )
            for element in page.elements
        )
        ownership_groups: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
        for index, (element, ownership) in enumerate(
            zip(page.elements, ownerships, strict=True)
        ):
            raw_group = str(element.measurements.get("equivalenceGroup", "")).strip()
            source_key = "|".join(ownership.source_targets)
            if (
                raw_group
                and source_key
                and ownership.provenance in {"selector:exact", "selector:exact+route"}
            ):
                ownership_groups[(raw_group, source_key)].append(index)
        canonical_groups = {
            index: (raw_group, source_key)
            for (raw_group, source_key), indexes in ownership_groups.items()
            if len(indexes) >= 3
            for index in indexes
        }
        owned_elements = []
        for index, element in enumerate(page.elements):
            canonical = canonical_groups.get(index)
            measurements = dict(element.measurements)
            if canonical is not None:
                raw_group, source_key = canonical
                measurements.update(
                    {
                        "equivalenceGroup": raw_group,
                        "equivalenceEvidence": "source-ownership",
                        "sourceOwnershipKey": source_key,
                    }
                )
            owned_elements.append(replace(element, measurements=measurements))
        owned_page = replace(page, elements=tuple(owned_elements))
        aligned_findings = detect_design_findings(owned_page)
        owned_elements = [
            replace(
                element,
                findings=tuple(
                    {
                        finding.fingerprint: finding
                        for finding in (
                            *element.findings,
                            *aligned_findings[index],
                            *navigation_findings[page_index][index],
                        )
                    }.values()
                ),
            )
            for index, element in enumerate(owned_page.elements)
        ]
        page = replace(owned_page, elements=tuple(owned_elements))
        enriched_pages.append(page)
        capture_identity = page.capture_id
        page_id = _node_id("runtime_page", "", capture_identity)
        page_finding_count = sum(len(element.findings) for element in page.elements)
        page_semantic_coverage = _runtime_semantic_coverage((page,))
        nodes.append(
            FrontendNode(
                id=page_id,
                kind="runtime_page",
                name=page.url,
                file="",
                line=0,
                metadata={
                    "title": page.title,
                    "runtime_url": page.url,
                    "viewport": {
                        "name": page.viewport.name,
                        "width": page.viewport.width,
                        "height": page.viewport.height,
                    },
                    "capture_id": page.capture_id,
                    "scenario": page.scenario,
                    "state": page.state,
                    "screenshot": page.screenshot,
                    "finding_count": page_finding_count,
                    "semantic_coverage": page_semantic_coverage,
                },
            )
        )
        runtime_elements: list[tuple[str, Any]] = []
        for element, ownership in zip(page.elements, ownerships, strict=True):
            if element.kind == "action":
                node_kind = "runtime_action"
            elif element.kind == "text":
                node_kind = "runtime_text"
            else:
                node_kind = "runtime_region"
            element_key = element.selector or f"{element.tag}:{element.order}"
            element_id = _node_id(
                node_kind,
                capture_identity,
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
                        "source_hint": element.source_hint,
                        "source_selectors": list(element.source_selectors),
                        "tag": element.tag,
                        "role": element.role,
                        "order": element.order,
                        "bounds": element.bounds,
                        "styles": element.styles,
                        "states": element.states,
                        "capture_id": page.capture_id,
                        "scenario": page.scenario,
                        "state": page.state,
                        "measurements": element.measurements,
                        "findings": [
                            finding.with_runtime_anchor(
                                url=page.url,
                                viewport=page.viewport.name,
                                selector=element.selector,
                                scenario=page.scenario,
                                state=page.state,
                                capture_id=page.capture_id,
                            ).to_dict()
                            for finding in element.findings
                        ],
                        "source_targets": list(ownership.source_targets),
                        "source_ownership": ownership.to_dict(),
                    },
                )
            )
            runtime_elements.append((element_id, element))
            _append_edge_once(
                edges,
                edge_keys,
                FrontendEdge(
                    page_id,
                    element_id,
                    "contains",
                    {
                        "order": element.order,
                        "viewport": page.viewport.name,
                        "capture_id": page.capture_id,
                        "scenario": page.scenario,
                        "state": page.state,
                    },
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

        selector_to_id = {
            element.selector: element_id
            for element_id, element in runtime_elements
            if element.selector
        }
        equivalence_groups: defaultdict[str, list[tuple[str, Any]]] = defaultdict(list)
        for element_id, element in runtime_elements:
            parent_selector = str(element.measurements.get("layoutParentSelector", ""))
            parent_id = selector_to_id.get(parent_selector)
            if parent_id is not None and parent_id != element_id:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(
                        parent_id,
                        element_id,
                        "runtime_contains",
                        {
                            "selector": parent_selector,
                            "capture_id": page.capture_id,
                        },
                    ),
                )
            equivalence_group = str(element.measurements.get("equivalenceGroup", ""))
            if equivalence_group:
                equivalence_groups[equivalence_group].append((element_id, element))
        for group, members in sorted(equivalence_groups.items()):
            ordered = sorted(members, key=lambda item: item[1].order)
            if len(ordered) < 2:
                continue
            representative_id, representative = ordered[0]
            for member_id, member in ordered[1:]:
                _append_edge_once(
                    edges,
                    edge_keys,
                    FrontendEdge(
                        representative_id,
                        member_id,
                        "runtime_equivalent",
                        {
                            "group": group,
                            "evidence": (
                                member.measurements.get("equivalenceEvidence")
                                or representative.measurements.get(
                                    "equivalenceEvidence"
                                )
                            ),
                            "capture_id": page.capture_id,
                        },
                    ),
                )

    return tuple(enriched_pages)


def _build_contract(nodes: list[FrontendNode]) -> ExperienceContract:
    routes = sorted({node.name for node in nodes if node.kind == "route"})
    data_sources = sorted({node.name for node in nodes if node.kind == "data"})
    runtime_pages = [node for node in nodes if node.kind == "runtime_page"]
    runtime_capture_states = {
        (
            str(node.metadata.get("scenario", "default")),
            str(node.metadata.get("state", "initial")),
        )
        for node in runtime_pages
    }
    runtime_routes = sorted({_runtime_route(node.name) for node in runtime_pages})
    contracts_by_kind: defaultdict[str, set[str]] = defaultdict(set)
    for node in nodes:
        if node.kind == "runtime_action" and not node.name:
            continue
        if node.kind == "state" and not re.search(
            r"loading|error|empty|open|selected|success|pending",
            node.name,
            re.IGNORECASE,
        ):
            continue
        contract = preservation_contract(node)
        if contract:
            contracts_by_kind[node.kind].add(contract)

    must_preserve: list[str] = []
    for kind in ("route", "runtime_page", "data", "action"):
        must_preserve.extend(sorted(contracts_by_kind[kind]))
    must_preserve.extend(sorted(contracts_by_kind["runtime_action"])[:40])
    must_preserve.extend(sorted(contracts_by_kind["state"]))
    must_preserve.extend(
        sorted(contracts_by_kind["region"] | contracts_by_kind["runtime_region"])
    )

    if runtime_pages:
        unknown = [
            "Source-to-runtime ownership remains inferred without source maps.",
            "Focus order and computed contrast still require dedicated runtime assertions.",
        ]
        if runtime_capture_states == {("default", "initial")}:
            unknown.insert(
                0,
                "Only initial runtime state was observed; triggered, authenticated, "
                "and failure states remain unknown.",
            )
        else:
            unknown.insert(
                0,
                "Only declared scenario states were observed; undeclared runtime "
                "states remain unknown.",
            )
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


def preservation_contract(node: FrontendNode) -> str | None:
    """Return the canonical preserved-contract identity for a frontend node."""

    if node.kind == "route":
        return f"Route remains reachable: {node.name}"
    if node.kind == "runtime_page":
        return f"Observed runtime route remains reachable: {_runtime_route(node.name)}"
    if node.kind == "data":
        return f"Data contract remains functional: {node.name}"
    if node.kind == "action":
        return f"Interaction capability remains available: {node.name}"
    if node.kind == "runtime_action":
        role = str(node.metadata.get("role", "action")) or "action"
        return f'Accessible runtime action remains available: {role} "{node.name}"'
    if node.kind == "state":
        return f"User-visible state remains represented: {node.name}"
    if (node.kind == "region" and node.name == "form") or (
        node.kind == "runtime_region" and str(node.metadata.get("tag", "")) == "form"
    ):
        return "Form semantics, validation, and submission behavior remain functional."
    return None


def _runtime_route(url: str) -> str:
    parsed = urlsplit(url)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _node_id(kind: str, file_path: str, name: str, ordinal: int = 0) -> str:
    raw = f"{kind}\0{file_path}\0{name}\0{ordinal}".encode()
    return f"{kind}:{hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:12]}"


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, max(0, offset)) + 1


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
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    atomic_replace_text(path, content, temp_prefix=f"{path.stem}_")
