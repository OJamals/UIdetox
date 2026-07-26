import argparse
from pathlib import Path

import pytest

import uidetox.state as state_module
from uidetox.commands import review
from uidetox.frontend_map import (
    SCHEMA_VERSION,
    ExperienceContract,
    FrontendMap,
    FrontendNode,
)
from uidetox.state import load_state
from uidetox.visual_evidence import VisualEvidenceStatus


def test_review_score_gate_requires_fresh_visual_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review, "load_config", lambda: {})
    monkeypatch.setattr(
        review,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="missing",
            ready=False,
            required=True,
            manifest_path=tmp_path / "visual-evidence.json",
            reasons=("visual evidence manifest is missing",),
        ),
    )
    monkeypatch.setattr(
        review,
        "_store_subjective_score",
        lambda _score: pytest.fail("stale evidence must block scoring"),
    )

    with pytest.raises(SystemExit) as exc_info:
        review.run(
            argparse.Namespace(
                score=90,
                require_visual_evidence=True,
                visual_evidence_file=None,
            )
        )

    assert exc_info.value.code == 1


def test_review_reports_reviewer_artifacts_regions_and_incomplete_viewports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(review, "load_config", lambda: {"tooling": {}})
    monkeypatch.setattr(state_module, "get_uidetox_dir", lambda: tmp_path)
    monkeypatch.setattr(
        review,
        "_load_review_map",
        lambda: FrontendMap(
            schema_version=SCHEMA_VERSION,
            generated_at="2026-07-26T00:00:00Z",
            root=str(tmp_path),
            target=".",
            nodes=(
                FrontendNode(
                    id="runtime-card",
                    kind="runtime_region",
                    name="Card",
                    file="",
                    line=0,
                    metadata={
                        "selector": "#card",
                        "source_targets": ["src/Card.tsx"],
                    },
                ),
            ),
            edges=(),
            contracts=ExperienceContract((), (), ()),
            fingerprint={},
            evidence={
                "runtime_capture_matrix": [
                    {
                        "scenario": "default",
                        "state": "initial",
                        "url": "http://localhost:3000/",
                        "viewport": {"name": "desktop"},
                        "status": "completed",
                    }
                ],
                "runtime_screenshots": ["/tmp/desktop.png"],
                "runtime_semantic_coverage": {
                    "elements": 1,
                    "paint_resolved": 0,
                    "paint_unresolved": 1,
                    "paint_unobserved": 0,
                    "equivalence_grouped": 0,
                },
                "runtime_findings": [
                    {
                        "code": "runtime-color-unresolved",
                        "selector": "#card",
                    }
                ],
            },
        ),
    )
    monkeypatch.setattr(
        review,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="fresh",
            ready=True,
            required=False,
            manifest_path=tmp_path / "visual-evidence.json",
            comparisons=2,
            reviewer_artifacts=(
                {
                    "case_id": None,
                    "kind": "contact_sheet",
                    "status": "generated",
                    "path": str(tmp_path / "contact_sheet.png"),
                    "reason": "",
                },
            ),
            top_changed_regions=(
                {
                    "case_id": "desktop",
                    "region_id": "primary",
                    "pixels_changed": 42,
                },
            ),
            incomplete_viewports=("tablet",),
            warnings=("invalid ICC profile fallback",),
        ),
    )

    review.run(
        argparse.Namespace(
            score=None,
            require_visual_evidence=False,
            visual_evidence_file=None,
        )
    )

    output = capsys.readouterr().out
    assert "contact_sheet" in output
    assert "desktop/primary: 42 px" in output
    assert "Incomplete viewports: tablet" in output
    assert "invalid ICC profile fallback" in output
    assert "default/initial desktop completed" in output
    assert "Paint unresolved: 1" in output
    assert "runtime-color-unresolved #card" in output
    assert "runtime-card #card -> src/Card.tsx" in output


def test_review_stores_structured_dimensions_and_current_evidence_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(review, "load_config", lambda: {})
    monkeypatch.setattr(
        review,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="fresh", ready=True, required=False, manifest_path=tmp_path / "v.json"
        ),
    )
    monkeypatch.setattr(
        review,
        "current_evidence_hashes",
        lambda: {"source": "s", "map": "m", "runtime": "r"},
    )
    review.run(
        argparse.Namespace(
            score=None,
            dimension_a=36,
            dimension_b=27,
            dimension_c=18,
            dimension_d=9,
            rationale="Reviewed hierarchy, states, and responsive evidence.",
            reviewer="qa-agent",
            finding_link=["finding-1"],
            region_link=["runtime-card"],
            route=["/checkout"],
            state=["error"],
            viewport=["mobile"],
            require_visual_evidence=False,
            visual_evidence_file=None,
        )
    )
    stored = load_state()["subjective"]
    assert stored["score"] == 90
    assert stored["dimensions"] == {"A": 36, "B": 27, "C": 18, "D": 9}
    assert stored["evidence_hashes"] == {"source": "s", "map": "m", "runtime": "r"}
    assert stored["region_links"] == ["runtime-card"]


def test_structured_review_requires_citations_and_coverage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        review._store_structured_review(
            argparse.Namespace(
                rationale="Reviewed the page.",
                reviewer="qa-agent",
                finding_link=[],
                region_link=[],
                route=[],
                state=[],
                viewport=[],
            ),
            {"A": 36, "B": 27, "C": 18, "D": 9},
        )

    assert exc_info.value.code == 1
    error = capsys.readouterr().err
    assert "--finding-link is required" in error
    assert "--region-link is required" in error
    assert "--route is required" in error
    assert "--state is required" in error
    assert "--viewport is required" in error


def test_legacy_scalar_review_is_explicitly_incomplete(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    review._store_subjective_score(87)
    stored = load_state()["subjective"]
    assert stored["legacy"] is True
    assert stored["stale"] is True
    assert "dimensions" not in stored
