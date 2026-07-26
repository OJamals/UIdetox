"""Shared source-fact extraction and consumer-reuse contracts."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest

from uidetox.analyzer import analyze_file
from uidetox.analyzer_ast import _analyze_ast
from uidetox.frontend_semantics import extract_script_semantics
from uidetox.semantic_adapters import (
    AdapterCapability,
    ApplicationSemantics,
    ModuleSemantics,
    SourceDocument,
    build_application_semantics,
)
from uidetox.source_facts import (
    EndpointFact,
    ImportAlias,
    SelectorFact,
    SourceFacts,
    SourceOccurrence,
    extract_source_facts,
    get_parser,
    has_ast_for,
)


def _tsx_facts(content: str):
    if not has_ast_for(".tsx"):
        pytest.skip("TSX grammar unavailable")
    facts = extract_source_facts(Path("Shell.tsx"), content)
    assert facts is not None
    return facts


def test_source_facts_cover_semantic_alias_http_and_route_contracts():
    facts = _tsx_facts(
        """
import { useState as useLocalState } from "react";
import { Dashboard as Dash } from "./Dashboard";
import { Route, createBrowserRouter } from "react-router-dom";
export const Shell = () => {
  const [ready, setReady] = useLocalState(false);
  fetch("/api/items", { method: "POST" });
  axios.patch("/api/items/1");
  fetch(dynamicUrl, { method: "DELETE" });
  fetch(`/api/items/${ready}`);
  return <main onClick={() => setReady(true)}><Dash /><Route path="/settings" /></main>;
};
const routes = [{ path: "/config" }];
createBrowserRouter(routes);
""".strip()
    )

    assert facts.imports == ("react", "./Dashboard", "react-router-dom")
    assert facts.react_aliases == (ImportAlias("react", "useState", "useLocalState"),)
    assert facts.rendered_modules == ("Dashboard", "Route")
    assert facts.declared_ui_modules == (SourceOccurrence("Shell", 4),)
    assert facts.regions == (SourceOccurrence("main", 10),)
    assert facts.actions == (SourceOccurrence("Click", 10),)
    assert facts.states == (SourceOccurrence("ready", 5),)
    assert facts.endpoints == (
        EndpointFact("/api/items", 6, "POST", False),
        EndpointFact("/api/items/1", 7, "PATCH", False),
        EndpointFact(None, 8, "DELETE", True),
        EndpointFact("/api/items/${ready}", 9, "GET", True),
    )
    assert facts.routes == (
        SourceOccurrence("/settings", 10),
        SourceOccurrence("/config", 12),
    )
    assert facts.extractor == "tree-sitter"
    assert facts.confidence == 1.0
    assert facts.parse_errors is False


def test_source_facts_extract_local_fetch_wrapper_calls_without_probe_duplicates():
    facts = _tsx_facts(
        """
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  return response.json() as Promise<T>;
}
function localRequest(path: string) {
  return path;
}
export const api = {
  list: () => request<Item[]>("/api/items"),
  create: () => request<Item>("/api/items", { method: "POST" }),
  ignore: () => localRequest("/not-http"),
};
""".strip()
    )

    assert facts.endpoints == (
        EndpointFact("/api/items", 9, "GET", False),
        EndpointFact("/api/items", 10, "POST", False),
    )


def test_source_facts_resolve_wrapper_guards_options_and_template_paths():
    facts = _tsx_facts(
        """
async function request(path: string, guard: unknown): Promise<unknown>;
async function request(path: string, guard: unknown, options: RequestInit): Promise<unknown>;
async function request(path: string, guard: unknown, options?: RequestInit) {
  return fetch(path, { headers: { Accept: "application/json" }, ...options });
}
export const api = {
  list: () => request("/api/items", isItem),
  create: () => request("/api/items", isItem, { method: "POST" }),
  update: (itemId: number) =>
    request(`/api/items/${itemId}`, isItem, { method: "PATCH" }),
};
""".strip()
    )

    assert facts.endpoints == (
        EndpointFact("/api/items", 7, "GET", False),
        EndpointFact("/api/items", 8, "POST", False),
        EndpointFact("/api/items/${itemId}", 10, "PATCH", True),
    )


def test_fullstack_fixture_client_is_canonical_operation_evidence():
    client = (
        Path(__file__).parents[1]
        / "examples"
        / "fullstack-slop-lab"
        / "frontend"
        / "src"
        / "api"
        / "client.ts"
    )
    facts = extract_source_facts(client, client.read_text(encoding="utf-8"))
    assert facts is not None
    assert len(facts.endpoints) == 28
    assert all(endpoint.method is not None for endpoint in facts.endpoints)
    assert (
        EndpointFact("/api/projects/${projectId}", 70, "GET", True) in facts.endpoints
    )
    assert (
        EndpointFact(
            "/api/governance/approvals/${approvalId}/decision",
            132,
            "POST",
            True,
        )
        in facts.endpoints
    )
    assert "api.getProjects" in {item.name for item in facts.callables}
    assert any(
        call.target == "request"
        and call.owner == "api.getProjects"
        and call.arguments[0] == '"/api/projects"'
        for call in facts.calls
    )


def test_fullstack_fixture_source_anchors_stay_within_file_bounds():
    contracts = (
        Path(__file__).parents[1]
        / "examples"
        / "fullstack-slop-lab"
        / "frontend"
        / "src"
        / "api"
        / "contracts.ts"
    )
    content = contracts.read_text(encoding="utf-8")
    facts = extract_source_facts(contracts, content)

    assert facts is not None
    source_line_count = len(content.splitlines())
    anchors = (
        *(item.line for item in facts.calls),
        *(item.line for item in facts.callables),
        *(item.line for item in facts.declared_ui_modules),
        *(item.line for item in facts.endpoints),
        *(item.line for item in facts.regions),
        *(item.line for item in facts.selectors),
    )
    assert anchors
    assert all(1 <= line <= source_line_count for line in anchors)


def test_source_facts_report_semantic_parse_errors_without_leaking_tree_nodes():
    facts = _tsx_facts("export function Broken( { return <main>")

    assert facts.parse_errors is True
    assert facts.confidence == 0.85

    def values(value):
        yield value
        if is_dataclass(value):
            for field in fields(value):
                yield from values(getattr(value, field.name))
        elif isinstance(value, dict):
            for item in value.items():
                yield from values(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                yield from values(item)

    assert not any(
        hasattr(value, "type") and hasattr(value, "children") for value in values(facts)
    )


def test_analyzer_and_semantic_consumers_reuse_one_source_fact_parse(tmp_path):
    if not has_ast_for(".tsx"):
        pytest.skip("TSX grammar unavailable")
    real_parser = get_parser(".tsx")
    assert real_parser is not None
    parse_calls = 0

    class CountingParser:
        def parse(self, content: bytes):
            nonlocal parse_calls
            parse_calls += 1
            return real_parser.parse(content)

    source = tmp_path / "Shell.tsx"
    content = (
        "import { useState } from 'react';\n"
        "export function Shell() {\n"
        "  const [opacity, setOpacity] = useState(0);\n"
        "  return <main />;\n"
        "}\n"
    )
    source.write_text(content, encoding="utf-8")
    facts = extract_source_facts(
        source,
        content,
        parser_factory=lambda _extension: CountingParser(),
    )

    assert facts is not None
    assert parse_calls == 1
    semantics = extract_script_semantics(source, content, facts=facts)
    ast_issues = _analyze_ast(source, content, ".tsx", facts=facts)
    file_issues = analyze_file(source, facts=facts)

    assert semantics is not None
    assert semantics.components[0].name == "Shell"
    assert [issue["id"] for issue in ast_issues] == ["ANIMATE_STATE_SLOP"]
    canonical = next(
        issue
        for issue in file_issues
        if issue["detector_id"] == "ANIMATE_STATE_SLOP"
    )
    assert ast_issues[0]["issue"] == canonical["issue"]
    assert ast_issues[0]["file"] == canonical["file"]
    assert parse_calls == 1


def test_semantic_consumer_does_not_retry_a_failed_shared_parse():
    parse_calls = 0

    class FailingParser:
        def parse(self, _content: bytes):
            nonlocal parse_calls
            parse_calls += 1
            raise RuntimeError("synthetic parse failure")

    path = Path("Broken.tsx")
    content = "export const Broken = () => <main />;"
    facts = extract_source_facts(
        path,
        content,
        parser_factory=lambda _extension: FailingParser(),
    )

    assert facts is None
    assert extract_script_semantics(path, content, facts=facts) is None
    assert parse_calls == 1


def test_application_semantics_resolve_reexported_http_wrappers(tmp_path):
    sources = {
        "api.ts": """
import axios from "axios";
const client = axios.create();
export const request = (path: string) => client.get(path);
""".strip(),
        "barrel.ts": 'export { request as fetchItems } from "./api";',
        "wildcard.ts": 'export * from "./api";',
        "App.tsx": """
import { fetchItems } from "./barrel";
import { request as wildcardRequest } from "./wildcard";
import { useQuery } from "@tanstack/react-query";
export function App() {
  useQuery({ queryKey: ["items"], queryFn: () => fetchItems("/api/items") });
  wildcardRequest("/api/wildcard");
  return <main />;
}
""".strip(),
    }
    documents = []
    for relative_path, content in sources.items():
        path = tmp_path / relative_path
        path.write_text(content, encoding="utf-8")
        documents.append(SourceDocument(path, relative_path, content))

    application = build_application_semantics(tmp_path, tmp_path, documents)
    app = application.module("App.tsx")

    assert app is not None
    assert any(
        call.target == "fetchItems"
        and call.client_family == "axios"
        and call.method == "GET"
        and call.url == "/api/items"
        and call.resolution == "resolved"
        for call in app.facts.network_calls
    )
    assert any(
        call.target == "useQuery"
        and call.client_family == "tanstack-query"
        and call.url is None
        and call.unresolved_evidence
        for call in app.facts.network_calls
    )
    assert any(
        call.target == "wildcardRequest"
        and call.client_family == "axios"
        and call.url == "/api/wildcard"
        and call.resolution == "resolved"
        for call in app.facts.network_calls
    )


def test_application_semantics_resolve_exported_client_object_methods(tmp_path):
    sources = {
        "api.ts": """
import axios from "axios";
const client = axios.create();
export const api = {
  list: () => client.get("/api/items"),
  update: (id: string) => client.patch(`/api/items/${id}`),
};
""".strip(),
        "App.tsx": """
import { api } from "./api";
export function App({ id }: { id: string }) {
  api.list();
  api.update(id);
  return <main />;
}
""".strip(),
    }
    documents = []
    for relative_path, content in sources.items():
        path = tmp_path / relative_path
        path.write_text(content, encoding="utf-8")
        documents.append(SourceDocument(path, relative_path, content))

    application = build_application_semantics(tmp_path, tmp_path, documents)
    app = application.module("App.tsx")

    assert app is not None
    calls = {call.target: call for call in app.facts.network_calls}
    assert calls["api.list"].client_family == "axios"
    assert calls["api.list"].method == "GET"
    assert calls["api.list"].url == "/api/items"
    assert calls["api.list"].dynamic is False
    assert calls["api.list"].resolution == "resolved"
    assert calls["api.update"].client_family == "axios"
    assert calls["api.update"].method == "PATCH"
    assert calls["api.update"].url == "/api/items/${id}"
    assert calls["api.update"].dynamic is True
    assert calls["api.update"].resolution == "resolved"


def test_application_semantics_bound_cyclic_reexports(tmp_path):
    sources = {
        "a.ts": 'export { request } from "./b";',
        "b.ts": 'export { request } from "./a";',
        "App.tsx": """
import { request } from "./a";
export function App() {
  request("/api/items");
  return <main />;
}
""".strip(),
    }
    documents = []
    for relative_path, content in sources.items():
        path = tmp_path / relative_path
        path.write_text(content, encoding="utf-8")
        documents.append(SourceDocument(path, relative_path, content))

    first = build_application_semantics(tmp_path, tmp_path, documents)
    second = build_application_semantics(tmp_path, tmp_path, reversed(documents))
    call = next(
        item
        for item in first.module("App.tsx").facts.network_calls
        if item.target == "request"
    )

    assert call.resolution == "unresolved"
    assert "unresolved import chain" in call.unresolved_evidence
    assert first.resolution_issues == second.resolution_issues


def test_application_semantics_preindexes_scale_sensitive_lookups(tmp_path):
    capability = AdapterCapability("native", "test fixture", 1.0, "test")
    modules = tuple(
        ModuleSemantics(
            relative_path=f"Component{index}.tsx",
            framework="react",
            capability=capability,
            facts=SourceFacts(
                path=tmp_path / f"Component{index}.tsx",
                extension=".tsx",
                selectors=(
                    SelectorFact(
                        f'[data-testid="component-{index}"]',
                        1,
                        "exact",
                    ),
                ),
            ),
        )
        for index in range(96)
    )
    application = ApplicationSemantics(tmp_path, tmp_path, modules)
    last = application.module("Component95.tsx")
    assert last is not None
    rebuilt = replace(application, modules=(last,))
    assert rebuilt.module("Component95.tsx") is last
    assert rebuilt.module("Component0.tsx") is None
    assert rebuilt.source_ownership(
        selector='[data-testid="component-95"]',
        tag="section",
    ).source_targets == ("Component95.tsx",)

    class IterationGuard(tuple):
        def __iter__(self):
            raise AssertionError("lookup scanned application.modules")

    object.__setattr__(application, "modules", IterationGuard(application.modules))
    assert application.module("Component95.tsx") is not None
    assert application.source_ownership(
        selector='[data-testid="component-95"]',
        tag="section",
    ).source_targets == ("Component95.tsx",)


@pytest.mark.parametrize(
    ("filename", "content", "framework"),
    [
        (
            "Panel.vue",
            """
<script setup lang="ts">
import { ref } from "vue";
const open = ref(false);
</script>
<template><section data-testid="panel"><button @click="open = true">Open</button></section></template>
""".strip(),
            "vue",
        ),
        (
            "Panel.svelte",
            """
<script lang="ts">let open = false;</script>
<section data-testid="panel"><button on:click={() => open = true}>Open</button></section>
""".strip(),
            "svelte",
        ),
        (
            "Panel.astro",
            """
---
const open = false;
---
<section data-testid="panel"><button>Open</button></section>
""".strip(),
            "astro",
        ),
    ],
)
def test_framework_adapters_report_degraded_capability_truth(
    tmp_path, filename, content, framework
):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")

    application = build_application_semantics(
        tmp_path,
        tmp_path,
        [SourceDocument(path, filename, content)],
    )
    module = application.module(filename)

    assert module is not None
    assert module.framework == framework
    assert module.capability.status == "degraded"
    assert module.capability.reason
    assert module.capability.confidence < 1.0
    assert {region.name for region in module.facts.regions} == {"section"}
    assert {action.name for action in module.facts.actions} >= (
        {"Click"} if framework != "astro" else set()
    )
    if framework in {"vue", "svelte"}:
        assert {state.name for state in module.facts.states} == {"open"}
    assert '[data-testid="panel"]' in {
        selector.selector for selector in module.facts.selectors
    }
