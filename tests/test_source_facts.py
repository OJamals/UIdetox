"""Shared source-fact extraction and consumer-reuse contracts."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest

import uidetox.source_facts as source_facts_module
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


def test_route_sources_bind_same_line_routes_to_their_own_elements(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "App.tsx",
            "src/App.tsx",
            'import { Route, Routes } from "react-router-dom"; '
            'import { ProjectsPage } from "./ProjectsPage"; '
            'import { SupportPage } from "./SupportPage"; '
            "export function App() { return <Routes>"
            '<Route path="/projects" element={<ProjectsPage />} />'
            '<Route path="/support" element={<SupportPage />} />'
            "</Routes>; }",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function SupportPage() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/App.tsx",
        "src/ProjectsPage.tsx",
    )


def test_route_sources_preserve_nested_route_element_lineage(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "App.tsx",
            "src/App.tsx",
            'import { Route } from "react-router-dom"; '
            'import { AuthBoundary } from "./AuthBoundary"; '
            'import { ProjectsPage } from "./ProjectsPage"; '
            "export function App() { return "
            '<Route path="/projects" element={<AuthBoundary><ProjectsPage /></AuthBoundary>} />; '
            "}",
        ),
        SourceDocument(
            src / "AuthBoundary.tsx",
            "src/AuthBoundary.tsx",
            "export function AuthBoundary({ children }) { return <>{children}</>; }",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/App.tsx",
        "src/AuthBoundary.tsx",
        "src/ProjectsPage.tsx",
    )


def test_route_sources_resolve_component_prop_routes_independently(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "App.tsx",
            "src/App.tsx",
            'import { Route, Routes } from "react-router-dom"; '
            'import { ProjectsPage as Projects } from "./ProjectsPage"; '
            'import { SupportPage as Support } from "./SupportPage"; '
            "export function App() { return <Routes>"
            '<Route path="/projects" Component={Projects} />'
            '<Route path="/support" Component={Support} />'
            "</Routes>; }",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function SupportPage() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/App.tsx",
        "src/ProjectsPage.tsx",
    )


def test_route_sources_resolve_route_object_components_independently(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            'import { ProjectsPage as Projects } from "./ProjectsPage"; '
            'import { SupportPage as Support } from "./SupportPage"; '
            "export const router = createBrowserRouter(["
            '{ path: "/projects", Component: Projects },'
            '{ path: "/support", Component: Support }'
            "]);",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function SupportPage() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/ProjectsPage.tsx",
        "src/router.tsx",
    )


def test_route_sources_resolve_namespace_component_routes_independently(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            'import * as Pages from "./pages"; '
            "export const router = createBrowserRouter(["
            '{ path: "/projects", Component: Pages.ProjectsPage },'
            '{ path: "/support", Component: Pages.SupportPage }'
            "]);",
        ),
        SourceDocument(
            src / "pages.ts",
            "src/pages.ts",
            'export { ProjectsPage } from "./ProjectsPage"; '
            'export { SupportPage } from "./SupportPage";',
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function SupportPage() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/ProjectsPage.tsx",
        "src/router.tsx",
    )


def test_route_sources_preserve_unicode_namespace_component_identity(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            'import * as Écrans from "./pages"; '
            "export const router = createBrowserRouter(["
            '{ path: "/projects", Component: Écrans.Proyectos },'
            '{ path: "/support", Component: Écrans.Soporte },'
            '{ path: "/computed", Component: Écrans["Soporte"] }'
            "]);",
        ),
        SourceDocument(
            src / "pages.ts",
            "src/pages.ts",
            'export { Proyectos } from "./ProjectsPage"; '
            'export { Soporte } from "./SupportPage";',
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function Proyectos() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function Soporte() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/ProjectsPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/computed") == ("src/router.tsx",)


def test_route_sources_match_optional_segments_without_cross_linking(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            'import { CategoriesPage } from "./CategoriesPage"; '
            'import { ProjectsPage } from "./ProjectsPage"; '
            'import { SettingsPage } from "./SettingsPage"; '
            'import { SupportPage } from "./SupportPage"; '
            "export const router = createBrowserRouter(["
            '{ path: "/:lang?/categories", Component: CategoriesPage },'
            '{ path: "/projects/:projectId?", Component: ProjectsPage },'
            '{ path: "/account/preferences?", Component: SettingsPage },'
            '{ path: "/support", Component: SupportPage }'
            "]);",
        ),
        SourceDocument(
            src / "CategoriesPage.tsx",
            "src/CategoriesPage.tsx",
            "export function CategoriesPage() { return <main>Categories</main>; }",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SettingsPage.tsx",
            "src/SettingsPage.tsx",
            "export function SettingsPage() { return <main>Settings</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export function SupportPage() { return <main>Support</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    expected_categories = ("src/CategoriesPage.tsx", "src/router.tsx")
    assert semantics.route_sources("http://localhost/categories") == expected_categories
    assert (
        semantics.route_sources("http://localhost/en/categories") == expected_categories
    )
    expected = ("src/ProjectsPage.tsx", "src/router.tsx")
    assert semantics.route_sources("http://localhost/projects") == expected
    assert semantics.route_sources("http://localhost/projects?tab=recent") == expected
    assert semantics.route_sources("http://localhost/projects/42") == expected
    expected_settings = ("src/SettingsPage.tsx", "src/router.tsx")
    assert semantics.route_sources("http://localhost/account") == expected_settings
    assert (
        semantics.route_sources("http://localhost/account/preferences")
        == expected_settings
    )
    assert semantics.route_sources("http://localhost/support") == (
        "src/SupportPage.tsx",
        "src/router.tsx",
    )


def test_route_sources_narrow_only_strictly_more_specific_dynamic_matches(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            'import { CategoryReportPage } from "./CategoryReportPage"; '
            'import { FileBrowserPage } from "./FileBrowserPage"; '
            'import { FileDetailPage } from "./FileDetailPage"; '
            'import { GenericTeamPage } from "./GenericTeamPage"; '
            'import { MonthlyReportPage } from "./MonthlyReportPage"; '
            'import { OptionalCatalogPage } from "./OptionalCatalogPage"; '
            'import { RequiredCatalogPage } from "./RequiredCatalogPage"; '
            'import { TeamEditPage } from "./TeamEditPage"; '
            "export const router = createBrowserRouter(["
            '{ path: "/catalog/:section?", Component: OptionalCatalogPage },'
            '{ path: "/catalog/:section", Component: RequiredCatalogPage },'
            '{ path: "/files/*", Component: FileBrowserPage },'
            '{ path: "/files/:fileId", Component: FileDetailPage },'
            '{ path: "/teams/:teamId/edit", Component: TeamEditPage },'
            '{ path: "/teams/:section/:action", Component: GenericTeamPage },'
            '{ path: "/reports/:category/:slug", Component: CategoryReportPage },'
            '{ path: "/reports/:year/:month", Component: MonthlyReportPage }'
            "]);",
        ),
        SourceDocument(
            src / "CategoryReportPage.tsx",
            "src/CategoryReportPage.tsx",
            "export function CategoryReportPage() { return <main>Category</main>; }",
        ),
        SourceDocument(
            src / "FileBrowserPage.tsx",
            "src/FileBrowserPage.tsx",
            "export function FileBrowserPage() { return <main>Files</main>; }",
        ),
        SourceDocument(
            src / "FileDetailPage.tsx",
            "src/FileDetailPage.tsx",
            "export function FileDetailPage() { return <main>File</main>; }",
        ),
        SourceDocument(
            src / "GenericTeamPage.tsx",
            "src/GenericTeamPage.tsx",
            "export function GenericTeamPage() { return <main>Team</main>; }",
        ),
        SourceDocument(
            src / "MonthlyReportPage.tsx",
            "src/MonthlyReportPage.tsx",
            "export function MonthlyReportPage() { return <main>Month</main>; }",
        ),
        SourceDocument(
            src / "OptionalCatalogPage.tsx",
            "src/OptionalCatalogPage.tsx",
            "export function OptionalCatalogPage() { return <main>Catalog</main>; }",
        ),
        SourceDocument(
            src / "RequiredCatalogPage.tsx",
            "src/RequiredCatalogPage.tsx",
            "export function RequiredCatalogPage() { return <main>Section</main>; }",
        ),
        SourceDocument(
            src / "TeamEditPage.tsx",
            "src/TeamEditPage.tsx",
            "export function TeamEditPage() { return <main>Edit</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/catalog") == (
        "src/OptionalCatalogPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/catalog/featured") == (
        "src/RequiredCatalogPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/files/42") == (
        "src/FileDetailPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/files/archive/42") == (
        "src/FileBrowserPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/teams/42/edit") == (
        "src/TeamEditPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/reports/2026/08") == (
        "src/CategoryReportPage.tsx",
        "src/MonthlyReportPage.tsx",
        "src/router.tsx",
    )


def test_route_sources_fail_closed_above_specificity_vector_budget(tmp_path):
    src = tmp_path / "src"
    vector_budget = 64
    runtime_parts = tuple(f"segment-{index}" for index in range(vector_budget + 1))
    documents = []
    expected_sources = []
    for static_count in range(vector_budget + 1):
        relative_path = f"src/route-{static_count:03}.ts"
        pattern = "/" + "/".join(
            runtime_part if index < static_count else f":param{index}"
            for index, runtime_part in enumerate(runtime_parts)
        )
        documents.append(
            SourceDocument(
                src / f"route-{static_count:03}.ts",
                relative_path,
                'import { createBrowserRouter } from "react-router-dom"; '
                "export const router = createBrowserRouter(["
                f'{{ path: "{pattern}" }}'
                "]);",
            )
        )
        expected_sources.append(relative_path)

    runtime_url = "http://localhost/" + "/".join(runtime_parts)
    within_budget = build_application_semantics(tmp_path, src, tuple(documents[:-1]))
    assert within_budget.route_sources(runtime_url) == ("src/route-063.ts",)

    semantics = build_application_semantics(tmp_path, src, tuple(documents))
    assert semantics.route_sources(runtime_url) == tuple(expected_sources)


def test_route_sources_resolve_direct_lazy_component_imports_only(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import React, { lazy as loadComponent } from "react"; '
            'import { createBrowserRouter } from "react-router-dom"; '
            'const ProjectsPage = loadComponent(() => import("./ProjectsPage")); '
            'const SupportPage = React.lazy(() => import("./SupportPage")); '
            'const GlobalPage = lazy(() => import("./GlobalPage")); '
            "const UnsafePage = loadComponent(() => import(routeModule)); "
            "export const router = createBrowserRouter(["
            '{ path: "/projects", Component: ProjectsPage },'
            '{ path: "/support", Component: SupportPage },'
            '{ path: "/global", Component: GlobalPage },'
            '{ path: "/unsafe", Component: UnsafePage },'
            '{ path: "/inline", Component: loadComponent(() => import("./InlinePage")) }'
            "]);",
        ),
        SourceDocument(
            src / "GlobalPage.tsx",
            "src/GlobalPage.tsx",
            "export default function GlobalPage() { return <main>Global</main>; }",
        ),
        SourceDocument(
            src / "ProjectsPage.tsx",
            "src/ProjectsPage.tsx",
            "export default function ProjectsPage() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportPage.tsx",
            "src/SupportPage.tsx",
            "export default function SupportPage() { return <main>Support</main>; }",
        ),
        SourceDocument(
            src / "UnsafePage.tsx",
            "src/UnsafePage.tsx",
            "export default function UnsafePage() { return <main>Unsafe</main>; }",
        ),
        SourceDocument(
            src / "InlinePage.tsx",
            "src/InlinePage.tsx",
            "export default function InlinePage() { return <main>Inline</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/ProjectsPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/support") == (
        "src/SupportPage.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/global") == ("src/router.tsx",)
    assert semantics.route_sources("http://localhost/unsafe") == ("src/router.tsx",)
    assert semantics.route_sources("http://localhost/inline") == ("src/router.tsx",)
    router = semantics.module("src/router.tsx")
    assert router is not None
    assert router.facts.imports == (
        "react",
        "react-router-dom",
        "./ProjectsPage",
        "./SupportPage",
    )
    assert (
        ImportAlias("./ProjectsPage", "default", "ProjectsPage", "default")
        in router.facts.import_aliases
    )
    assert (
        ImportAlias("./SupportPage", "default", "SupportPage", "default")
        in router.facts.import_aliases
    )
    assert all(
        item.local not in {"GlobalPage", "UnsafePage", "InlinePage"}
        for item in router.facts.import_aliases
    )


def test_route_sources_resolve_direct_inline_lazy_route_modules_only(tmp_path):
    src = tmp_path / "src"
    documents = (
        SourceDocument(
            src / "router.tsx",
            "src/router.tsx",
            'import { createBrowserRouter } from "react-router-dom"; '
            "export const router = createBrowserRouter(["
            '{ path: "/projects", lazy: () => import("./ProjectsRoute") },'
            '{ path: "/support", lazy: () => import("./SupportRoute") },'
            '{ path: "/computed", lazy: () => import(routeModule) },'
            '{ path: "/mapped", lazy: () => import("./MappedRoute").then('
            "(module) => ({ Component: module.Page })) },"
            '{ path: "/block", lazy: async () => { '
            'return import("./BlockRoute"); } }'
            "]);",
        ),
        SourceDocument(
            src / "ProjectsRoute.tsx",
            "src/ProjectsRoute.tsx",
            "export function Component() { return <main>Projects</main>; }",
        ),
        SourceDocument(
            src / "SupportRoute.tsx",
            "src/SupportRoute.tsx",
            "export function Component() { return <main>Support</main>; }",
        ),
        SourceDocument(
            src / "MappedRoute.tsx",
            "src/MappedRoute.tsx",
            "export function Page() { return <main>Mapped</main>; }",
        ),
        SourceDocument(
            src / "BlockRoute.tsx",
            "src/BlockRoute.tsx",
            "export function Component() { return <main>Block</main>; }",
        ),
    )

    semantics = build_application_semantics(tmp_path, src, documents)

    assert semantics.route_sources("http://localhost/projects") == (
        "src/ProjectsRoute.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/support") == (
        "src/SupportRoute.tsx",
        "src/router.tsx",
    )
    assert semantics.route_sources("http://localhost/computed") == ("src/router.tsx",)
    assert semantics.route_sources("http://localhost/mapped") == ("src/router.tsx",)
    assert semantics.route_sources("http://localhost/block") == ("src/router.tsx",)
    router = semantics.module("src/router.tsx")
    assert router is not None
    assert router.facts.imports == (
        "react-router-dom",
        "./ProjectsRoute",
        "./SupportRoute",
    )
    assert {route.name: route.target for route in router.facts.routes} == {
        "/block": "",
        "/computed": "",
        "/mapped": "",
        "/projects": "./ProjectsRoute",
        "/support": "./SupportRoute",
    }


@pytest.mark.parametrize(
    "source",
    [
        "export default function () { return <button>Hi</button>; }",
        "export default class extends React.Component { render() { return <main />; } }",
        "export default () => <section />;",
    ],
)
def test_source_facts_name_anonymous_default_components_from_module(source):
    facts = extract_source_facts(Path("my-widget.tsx"), source)

    assert facts is not None
    assert any(
        item.exported == "default" and item.local == "MyWidget"
        for item in facts.exports
    )
    assert SourceOccurrence("MyWidget", 1) in facts.declared_ui_modules


def test_source_facts_do_not_name_anonymous_non_ui_defaults():
    facts = extract_source_facts(
        Path("plain.ts"),
        "export default function () { return 42; }",
    )

    assert facts is not None
    assert facts.declared_ui_modules == ()
    assert all(item.local != "Plain" for item in facts.exports)


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
    assert len(facts.endpoints) == 73
    assert all(endpoint.method is not None for endpoint in facts.endpoints)
    assert (
        EndpointFact("/api/projects/${projectId}", 98, "GET", True) in facts.endpoints
    )
    assert (
        EndpointFact(
            "/api/governance/approvals/${approvalId}/decision",
            160,
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
        issue for issue in file_issues if issue["detector_id"] == "ANIMATE_STATE_SLOP"
    )
    assert ast_issues[0]["issue"] == canonical["issue"]
    assert ast_issues[0]["file"] == canonical["file"]
    assert parse_calls == 1


def test_extract_source_facts_materializes_root_walk_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not has_ast_for(".tsx"):
        pytest.skip("TSX grammar unavailable")
    path = Path("Shell.tsx")
    content = (
        "import { useState } from 'react';\n"
        "export function Shell() {\n"
        "  const [ready, setReady] = useState(false);\n"
        "  return <main onClick={() => setReady(true)} />;\n"
        "}\n"
    )
    expected = extract_source_facts(path, content)
    original_walk = source_facts_module._walk
    root_node: object | None = None
    root_walks = 0

    def count_walk(node: object):
        nonlocal root_node, root_walks
        if root_node is None:
            root_node = node
        if node is root_node:
            root_walks += 1
        yield from original_walk(node)

    received_nodes: list[object] = []
    for name in (
        "_extract_imports",
        "_extract_exports",
        "_extract_bindings",
        "_extract_callables",
        "_extract_calls",
    ):
        original = getattr(source_facts_module, name)

        def receive(nodes: object, *args: object, _original=original):
            received_nodes.append(nodes)
            return _original(nodes, *args)

        monkeypatch.setattr(source_facts_module, name, receive)
    monkeypatch.setattr(source_facts_module, "_walk", count_walk)

    actual = extract_source_facts(path, content)

    assert actual == expected
    assert root_walks == 1
    assert len(received_nodes) == 5
    assert all(nodes is received_nodes[0] for nodes in received_nodes)


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


def test_network_type_references_survive_reexported_wrapper_resolution(tmp_path):
    sources = {
        "api.ts": """
import axios, { type AxiosResponse } from "axios";
const client = axios.create();
export function save<TRequest, TResponse>(path: string, body: TRequest) {
  return client.post<TResponse, AxiosResponse<TResponse>, TRequest>(path, body);
}
""".strip(),
        "barrel.ts": 'export { save as saveItem } from "./api";',
        "App.tsx": """
import { useMutation } from "@tanstack/react-query";
import { useQuery as useApolloQuery } from "@apollo/client";
import { saveItem } from "./barrel";
declare const payload: SaveItemRequest;
export function App() {
  saveItem<SaveItemRequest, SaveItemResponse>("/api/items", payload);
  useMutation<SaveItemResponse, Error, SaveItemRequest>({ mutationFn: saveItem });
  useApolloQuery<ItemsResponse, ItemsVariables>(GET_ITEMS);
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
    assert calls["saveItem"].request_type_refs == ("SaveItemRequest",)
    assert calls["saveItem"].response_type_refs == ("SaveItemResponse",)
    assert calls["useMutation"].request_type_refs == ("SaveItemRequest",)
    assert calls["useMutation"].response_type_refs == ("SaveItemResponse",)
    assert calls["useApolloQuery"].request_type_refs == ("ItemsVariables",)
    assert calls["useApolloQuery"].response_type_refs == ("ItemsResponse",)


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
