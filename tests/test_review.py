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


def _validated_review_map(
    tmp_path: Path,
    *,
    capture_matrix: list[dict] | None = None,
    project_findings: list[dict] | None = None,
    contracts: ExperienceContract | None = None,
) -> FrontendMap:
    return FrontendMap(
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
                metadata={"selector": "#card"},
            ),
        ),
        edges=(),
        contracts=contracts or ExperienceContract((), (), ()),
        fingerprint={},
        evidence={
            "source_status": "current",
            "runtime_status": "current",
            "runtime_findings": [{"fingerprint": "finding-1", "id": "finding-1"}],
            "runtime_capture_matrix": capture_matrix
            if capture_matrix is not None
            else [
                {
                    "scenario": "checkout",
                    "state": "error",
                    "url": "http://localhost:3000/checkout",
                    "viewport": {"name": "mobile"},
                    "status": "completed",
                }
            ],
        },
        project_map={"findings": project_findings or []},
    )


def test_review_gate_requires_fresh_visual_evidence(
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
    with pytest.raises(SystemExit) as exc_info:
        review.run(
            argparse.Namespace(
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
    monkeypatch.setattr(
        review, "_load_review_map", lambda: _validated_review_map(tmp_path)
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
    assert stored["scope_validation"]["status"] == "validated"
    assert (
        stored["scope_validation"]["policy_version"]
        == review.STRUCTURED_REVIEW_POLICY_VERSION
    )
    assert stored["scope_validation"]["capture_matrix"] == [
        {"route": "/checkout", "state": "error", "viewport": "mobile"}
    ]
    assert len(stored["required_matrix_digest"]) == 64
    assert (
        stored["scope_validation"]["required_matrix_digest"]
        == stored["required_matrix_digest"]
    )


def test_structured_review_rejects_subset_of_non_cartesian_completed_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        review,
        "_load_review_map",
        lambda: _validated_review_map(
            tmp_path,
            capture_matrix=[
                {
                    "scenario": "one",
                    "state": "initial",
                    "url": "http://localhost:3000/one",
                    "viewport": {"name": "desktop"},
                    "status": "completed",
                },
                {
                    "scenario": "two",
                    "state": "error",
                    "url": "http://localhost:3000/two",
                    "viewport": {"name": "mobile"},
                    "status": "completed",
                },
            ],
        ),
    )
    monkeypatch.setattr(
        review,
        "current_evidence_hashes",
        lambda: {"source": "s", "map": "m", "runtime": "r"},
    )

    with pytest.raises(SystemExit):
        review._store_structured_review(
            argparse.Namespace(
                rationale="Reviewed only one completed capture.",
                reviewer="qa-agent",
                finding_link=["finding-1"],
                region_link=["runtime-card"],
                route=["/one"],
                state=["initial"],
                viewport=["desktop"],
            ),
            {"A": 36, "B": 27, "C": 18, "D": 9},
        )

    error = capsys.readouterr().err
    assert "/two/error/mobile" in error

    review._store_structured_review(
        argparse.Namespace(
            rationale="Reviewed both completed captures.",
            reviewer="qa-agent",
            finding_link=["finding-1"],
            region_link=["runtime-card"],
            route=["/one", "/two"],
            state=["initial", "error"],
            viewport=["desktop", "mobile"],
        ),
        {"A": 36, "B": 27, "C": 18, "D": 9},
    )
    assert load_state()["subjective"]["scope_validation"]["capture_matrix"] == [
        {"route": "/one", "state": "initial", "viewport": "desktop"},
        {"route": "/two", "state": "error", "viewport": "mobile"},
    ]


def test_structured_review_rejects_stale_links_and_incomplete_capture_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        review, "_load_review_map", lambda: _validated_review_map(tmp_path)
    )
    monkeypatch.setattr(
        review,
        "current_evidence_hashes",
        lambda: {"source": "s", "map": "m", "runtime": "r"},
    )

    with pytest.raises(SystemExit):
        review._store_structured_review(
            argparse.Namespace(
                rationale="Reviewed the matrix.",
                reviewer="qa-agent",
                finding_link=["stale-finding"],
                region_link=["stale-region"],
                route=["/checkout", "/checkout"],
                state=["error", "success"],
                viewport=["mobile", "mobile"],
            ),
            {"A": 36, "B": 27, "C": 18, "D": 9},
        )

    error = capsys.readouterr().err
    assert "stale-finding" in error
    assert "stale-region" in error
    assert "/checkout/success/mobile" in error


def test_structured_review_accepts_current_contract_finding_links(
    tmp_path: Path,
) -> None:
    frontend_map = _validated_review_map(
        tmp_path,
        project_findings=[
            {"fingerprint": "contract-finding", "id": "contract-finding"}
        ],
    )

    validation = review._validate_review_scope(
        frontend_map,
        {"issues": []},
        {"source": "s", "map": "m", "runtime": "r"},
        {
            "finding_link": ["contract-finding"],
            "region_link": ["runtime-card"],
            "route": ["/checkout"],
            "state": ["error"],
            "viewport": ["mobile"],
        },
    )

    assert validation["status"] == "validated"
    assert validation["errors"] == []


def test_structured_review_rejects_initial_only_interactive_state_evidence(
    tmp_path: Path,
) -> None:
    frontend_map = _validated_review_map(
        tmp_path,
        capture_matrix=[
            {
                "scenario": "default",
                "state": "initial",
                "url": "http://localhost:3000/projects",
                "viewport": {"name": "mobile"},
                "status": "completed",
            }
        ],
        contracts=ExperienceContract(
            must_preserve=("User-visible state remains represented: error",),
            may_change=(),
            unknown=(
                (
                    "Only initial runtime state was observed; triggered, authenticated, "
                    "and failure states remain unknown."
                ),
            ),
        ),
    )

    validation = review._validate_review_scope(
        frontend_map,
        {"issues": []},
        {"source": "s", "map": "m", "runtime": "r"},
        {
            "finding_link": ["finding-1"],
            "region_link": ["runtime-card"],
            "route": ["/projects"],
            "state": ["initial"],
            "viewport": ["mobile"],
        },
    )

    assert validation["status"] == "invalid"
    assert validation["errors"] == [
        "interactive review requires at least one non-initial runtime scenario state"
    ]


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
