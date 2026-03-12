"""Tests for route-level UX-state validation (loading/error/empty/success coverage)."""

from pathlib import Path

import pytest

from uidetox import state as state_module
from uidetox.state import ensure_uidetox_dir
from uidetox.ux_states import (
    DataSurface,
    StateCoverage,
    find_data_surfaces,
    generate_coverage_report,
    validate_against_response_taxonomy,
    validate_state_coverage,
)


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None


# ── StateCoverage unit tests ─────────────────────────────────────


class TestStateCoverage:
    def test_complete_coverage(self):
        cov = StateCoverage(
            surface=DataSurface(file="test.tsx"),
            has_loading=True,
            has_error=True,
            has_empty=True,
            has_success=True,
        )
        assert cov.is_complete
        assert cov.missing_states == []
        assert cov.coverage_ratio == 1.0
        assert cov.to_issue() is None

    def test_missing_states(self):
        cov = StateCoverage(
            surface=DataSurface(file="test.tsx"),
            has_loading=True,
            has_error=False,
            has_empty=False,
            has_success=True,
        )
        assert not cov.is_complete
        assert set(cov.missing_states) == {"error", "empty"}
        assert cov.coverage_ratio == 0.5

    def test_to_issue_includes_missing_states(self):
        cov = StateCoverage(
            surface=DataSurface(file="src/Users.tsx", pattern="useQuery"),
            has_loading=False,
            has_error=False,
            has_empty=False,
            has_success=True,
        )
        issue = cov.to_issue()
        assert issue is not None
        assert issue["tier"] == "T1"  # 3 missing = T1
        assert "loading" in issue["issue"]
        assert "error" in issue["issue"]
        assert "empty" in issue["issue"]

    def test_to_dict_roundtrip(self):
        cov = StateCoverage(
            surface=DataSurface(file="x.tsx", line=42, pattern="fetch"),
            has_loading=True,
            has_error=True,
            has_empty=False,
            has_success=True,
        )
        d = cov.to_dict()
        assert d["has_loading"] is True
        assert d["has_empty"] is False
        assert "empty" in d["missing"]
        assert d["coverage"] == 0.75


# ── Data surface detection ───────────────────────────────────────


class TestFindDataSurfaces:
    def test_detects_fetch_calls(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "Users.tsx").write_text(
            'export function Users() {\n'
            '  const res = fetch("/api/users");\n'
            '  return <div>{res}</div>;\n'
            '}\n',
            encoding="utf-8",
        )
        surfaces = find_data_surfaces(tmp_path)
        assert len(surfaces) == 1
        assert surfaces[0].file.endswith("Users.tsx")

    def test_detects_use_query(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "Posts.tsx").write_text(
            'import { useQuery } from "@tanstack/react-query";\n'
            'export function Posts() {\n'
            '  const { data } = useQuery({ queryKey: ["posts"] });\n'
            '  return <div />;\n'
            '}\n',
            encoding="utf-8",
        )
        surfaces = find_data_surfaces(tmp_path)
        assert len(surfaces) >= 1

    def test_ignores_non_frontend_files(self, tmp_path):
        (tmp_path / "server.py").write_text("import requests\nrequests.get('/')\n")
        surfaces = find_data_surfaces(tmp_path)
        assert len(surfaces) == 0

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.tsx").write_text('fetch("/api")', encoding="utf-8")
        surfaces = find_data_surfaces(tmp_path)
        assert len(surfaces) == 0


# ── State coverage validation ────────────────────────────────────


class TestValidateStateCoverage:
    def test_full_coverage_component(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "FullComponent.tsx").write_text(
            'import { useQuery } from "react-query";\n'
            'export function Full() {\n'
            '  const { data, isLoading, isError } = useQuery("key");\n'
            '  if (isLoading) return <Skeleton />;\n'
            '  if (isError) return <ErrorFallback />;\n'
            '  if (!data || data.length === 0) return <EmptyState />;\n'
            '  return <div>{data.map(x => <span>{x}</span>)}</div>;\n'
            '}\n',
            encoding="utf-8",
        )
        coverages = validate_state_coverage(tmp_path)
        assert len(coverages) == 1
        assert coverages[0].is_complete

    def test_missing_loading_and_empty(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "Partial.tsx").write_text(
            'export function Partial() {\n'
            '  const data = fetch("/api/items");\n'
            '  try {\n'
            '    return <div>{data.map(x => <p>{x}</p>)}</div>;\n'
            '  } catch (e) {\n'
            '    return <p>Error</p>;\n'
            '  }\n'
            '}\n',
            encoding="utf-8",
        )
        coverages = validate_state_coverage(tmp_path)
        assert len(coverages) == 1
        cov = coverages[0]
        assert cov.has_error is True
        assert cov.has_success is True
        # loading and empty are missing
        assert "loading" in cov.missing_states
        assert "empty" in cov.missing_states


# ── Coverage report ──────────────────────────────────────────────


class TestGenerateCoverageReport:
    def test_empty_surfaces(self):
        report = generate_coverage_report([])
        assert report["total_surfaces"] == 0
        assert report["coverage_percentage"] == 100

    def test_mixed_coverage(self):
        complete = StateCoverage(
            surface=DataSurface(file="a.tsx"),
            has_loading=True, has_error=True, has_empty=True, has_success=True,
        )
        partial = StateCoverage(
            surface=DataSurface(file="b.tsx"),
            has_loading=True, has_error=False, has_empty=False, has_success=True,
        )
        report = generate_coverage_report([complete, partial])
        assert report["total_surfaces"] == 2
        assert report["complete"] == 1
        assert report["incomplete"] == 1
        assert report["missing_breakdown"]["error"] == 1
        assert report["missing_breakdown"]["empty"] == 1


# ── Response taxonomy validation  ────────────────────────────────


class TestResponseTaxonomy:
    def test_backend_requires_error_handling(self):
        coverages = [
            StateCoverage(
                surface=DataSurface(file="Users.tsx"),
                has_loading=True,
                has_error=False,
                has_empty=True,
                has_success=True,
            )
        ]
        violations = validate_against_response_taxonomy(
            coverages,
            endpoint_status_codes={"/users": [200, 404, 500]},
        )
        assert len(violations) >= 1
        error_violations = [v for v in violations if "error" in v["issue"]]
        assert len(error_violations) >= 1

    def test_no_violations_when_fully_covered(self):
        coverages = [
            StateCoverage(
                surface=DataSurface(file="Full.tsx"),
                has_loading=True,
                has_error=True,
                has_empty=True,
                has_success=True,
            )
        ]
        violations = validate_against_response_taxonomy(
            coverages,
            endpoint_status_codes={"/users": [200, 404, 500]},
        )
        assert len(violations) == 0
