"""Shared source-fact extraction and consumer-reuse contracts."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from uidetox.analyzer import analyze_file
from uidetox.analyzer_ast import _analyze_ast
from uidetox.frontend_semantics import extract_script_semantics
from uidetox.source_facts import (
    EndpointFact,
    ImportAlias,
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
    assert EndpointFact(
        "/api/projects/${projectId}", 70, "GET", True
    ) in facts.endpoints
    assert EndpointFact(
        "/api/governance/approvals/${approvalId}/decision",
        132,
        "POST",
        True,
    ) in facts.endpoints


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
    assert ast_issues == [
        issue for issue in file_issues if issue["id"] == "ANIMATE_STATE_SLOP"
    ]
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
