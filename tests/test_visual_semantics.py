"""Semantic-region and intent/source provenance tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import uidetox.visual_semantics as visual_semantics
from uidetox.design_context import DesignIntent
from uidetox.frontend_map import (
    SCHEMA_VERSION,
    ExperienceContract,
    FrontendMap,
    FrontendNode,
)
from uidetox.runtime_observer import (
    RuntimeElement,
    RuntimePage,
    RuntimeViewport,
)
from uidetox.visual_semantics import (
    build_visual_context,
    explicit_ignore_regions,
    load_project_visual_context,
    project_visual_evidence_status,
    semantic_regions_from_runtime,
)
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceRequest,
    build_visual_evidence,
)


def _page() -> RuntimePage:
    return RuntimePage(
        url="http://127.0.0.1:4173/projects",
        title="Projects",
        viewport=RuntimeViewport("desktop", 1280, 800),
        elements=(
            RuntimeElement(
                kind="region",
                tag="nav",
                role="navigation",
                name="Project navigation",
                selector='[data-testid="sidebar"]',
                order=0,
                bounds={"x": 0, "y": 0, "width": 240, "height": 800},
                styles={},
            ),
        ),
        screenshot="/tmp/after_desktop.png",
    )


def _frontend_map() -> FrontendMap:
    return FrontendMap(
        schema_version=SCHEMA_VERSION,
        generated_at="2026-07-19T00:00:00Z",
        root="/tmp/project",
        target="frontend",
        nodes=(
            FrontendNode(
                id="runtime-sidebar",
                kind="runtime_region",
                name="Project navigation",
                file="",
                line=0,
                metadata={
                    "runtime_url": "http://127.0.0.1:4173/projects",
                    "viewport": "desktop",
                    "selector": '[data-testid="sidebar"]',
                    "source_targets": [
                        "frontend/src/components/Sidebar.tsx",
                    ],
                },
            ),
        ),
        edges=(),
        contracts=ExperienceContract(
            must_preserve=(
                "Route remains reachable: /projects",
                "Interaction capability remains available: create project",
            ),
            may_change=("Navigation archetype and page topology.",),
            unknown=("Source maps unavailable.",),
        ),
        fingerprint={"topology": "sidebar"},
        evidence={
            "source_manifest": {
                "files": {
                    "frontend/src/components/Sidebar.tsx": "source-hash",
                }
            }
        },
    )


def test_runtime_regions_link_only_evidenced_sources_intent_and_contracts() -> None:
    intent = DesignIntent.from_dict(
        {
            "product_goal": "Coordinate projects",
            "audience": "Operations teams",
            "primary_job": "Review project health",
            "provenance": {
                "product_goal": "explicit",
                "audience": "explicit",
                "primary_job": "mapped",
            },
            "preserve": ["Keep project routes and API contracts"],
        }
    )

    regions = semantic_regions_from_runtime(
        _page(),
        frontend_map=_frontend_map(),
        intent=intent,
    )

    assert len(regions) == 1
    region = regions[0]
    assert region.bounds == (0.0, 0.0, 240.0, 800.0)
    assert region.source_targets == (
        "frontend/src/components/Sidebar.tsx",
    )
    assert region.intent_fields == (
        "audience",
        "primary_job",
        "product_goal",
    )
    assert "Route remains reachable: /projects" in region.preserve_contracts
    assert "Keep project routes and API contracts" in region.preserve_contracts
    assert "runtime-sidebar" in region.provenance


def test_visual_context_hashes_map_and_field_level_intent_provenance() -> None:
    intent = DesignIntent.from_dict(
        {
            "product_goal": "Coordinate projects",
            "provenance": {"product_goal": "explicit"},
        }
    )

    hashes, context = build_visual_context(_frontend_map(), intent)

    assert set(hashes) == {"frontend_map", "design_intent"}
    assert all(len(value) == 64 for value in hashes.values())
    assert context["frontend_map"]["source_manifest"]["files"]
    assert context["design_intent"]["provenance"]["product_goal"] == "explicit"


def test_ignore_regions_require_explicit_config_reason_and_scope() -> None:
    config = {
        "visual_evidence": {
            "ignore_regions": [
                {
                    "id": "animated-metric",
                    "viewport": "desktop",
                    "url": "/projects",
                    "bounds": [10, 20, 100, 30],
                    "reason": "count-up animation",
                },
                {
                    "id": "wrong-viewport",
                    "viewport": "mobile",
                    "bounds": [0, 0, 10, 10],
                    "reason": "not applicable",
                },
            ]
        }
    }

    regions = explicit_ignore_regions(config, _page())

    assert len(regions) == 1
    assert regions[0].region_id == "animated-metric"
    assert regions[0].reason == "count-up animation"
    assert regions[0].provenance == (
        "config:visual_evidence.ignore_regions[0]"
    )


def test_corrupt_or_deleted_map_invalidates_captured_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uidetox_dir = tmp_path / ".uidetox"
    snapshots = uidetox_dir / "snapshots"
    snapshots.mkdir(parents=True)
    map_path = uidetox_dir / "frontend-map.json"
    map_path.write_text("{not-json", encoding="utf-8")
    before = snapshots / "before.png"
    after = snapshots / "after.png"
    manifest_path = snapshots / "visual-evidence.json"
    Image.new("RGB", (2, 2), "black").save(before)
    Image.new("RGB", (2, 2), "black").save(after)
    _, _, current_hashes, _ = load_project_visual_context({}, map_path)
    build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=(
                VisualEvidenceCase(
                    case_id="desktop",
                    before_path=before,
                    after_path=after,
                ),
            ),
            output_dir=snapshots,
            manifest_path=manifest_path,
            context_sha256s={
                **current_hashes,
                "frontend_map": "captured-map-hash",
            },
        )
    )
    monkeypatch.setattr(
        visual_semantics,
        "get_uidetox_dir",
        lambda: uidetox_dir,
    )

    corrupt_status = project_visual_evidence_status(
        {},
        required=True,
        manifest_path=manifest_path,
    )
    assert corrupt_status.state == "stale"
    assert any(
        "frontend_map" in reason and "no longer available" in reason
        for reason in corrupt_status.reasons
    )

    map_path.unlink()
    deleted_status = project_visual_evidence_status(
        {},
        required=True,
        manifest_path=manifest_path,
    )
    assert deleted_status.state == "stale"
