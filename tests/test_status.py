import argparse
import json
from pathlib import Path

import pytest

from uidetox.commands import status
from uidetox.visual_evidence import VisualEvidenceStatus


def _state() -> dict:
    return {
        "issues": [],
        "resolved": [],
        "stats": {"scans_run": 0, "total_found": 0},
    }


def test_status_json_exposes_visual_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = VisualEvidenceStatus(
        state="fresh",
        ready=True,
        required=False,
        manifest_path=tmp_path / "visual-evidence.json",
        comparisons=4,
        reviewer_artifacts=(
            {
                "case_id": "desktop",
                "kind": "heat_overlay",
                "status": "generated",
                "path": str(tmp_path / "heat.png"),
                "reason": "",
            },
        ),
        top_changed_regions=(
            {
                "case_id": "desktop",
                "region_id": "primary",
                "pixels_changed": 25,
                "changed_ratio": 0.25,
            },
        ),
        incomplete_viewports=("mobile",),
        warnings=("ICC profile fallback",),
    )
    monkeypatch.setattr(status, "load_state", _state)
    monkeypatch.setattr(status, "load_config", lambda: {})
    monkeypatch.setattr(status, "_git_context", lambda: ("main", False))
    monkeypatch.setattr(status, "current_verification_fresh", lambda: False)
    monkeypatch.setattr(
        status,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: evidence,
    )

    status.run(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["visual_evidence"]["state"] == "fresh"
    assert payload["visual_evidence"]["comparisons"] == 4
    assert payload["visual_evidence"]["incomplete_viewports"] == ["mobile"]
    assert (
        payload["visual_evidence"]["top_changed_regions"][0]["region_id"] == "primary"
    )
    assert "eligibility" in payload
    assert "incomplete_qualification" in {
        blocker["code"] for blocker in payload["eligibility"]["blockers"]
    }


def test_status_required_visual_evidence_gate_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = VisualEvidenceStatus(
        state="stale",
        ready=False,
        required=True,
        manifest_path=tmp_path / "visual-evidence.json",
        reasons=("before source hash changed",),
    )
    monkeypatch.setattr(status, "load_state", _state)
    monkeypatch.setattr(status, "load_config", lambda: {})
    monkeypatch.setattr(status, "_git_context", lambda: ("main", False))
    monkeypatch.setattr(status, "current_verification_fresh", lambda: False)
    monkeypatch.setattr(
        status,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: evidence,
    )

    with pytest.raises(SystemExit) as exc_info:
        status.run(
            argparse.Namespace(
                json=True,
                require_visual_evidence=True,
                visual_evidence_file=None,
            )
        )

    assert exc_info.value.code == 1
    assert json.loads(capsys.readouterr().out)["visual_evidence"]["state"] == ("stale")


def test_status_splits_actionable_and_investigative_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from uidetox.findings import Finding

    actionable = Finding.create(
        detector_id="runtime-overlap",
        category="layout",
        severity="warning",
        confidence=1,
        message="Controls overlap.",
        provenance="runtime",
    )
    investigative = Finding.create(
        detector_id="contract-response-evidence-unknown",
        category="contract",
        severity="info",
        confidence=0.5,
        message="Response evidence is unknown.",
        provenance="contract",
        status="investigate",
    )
    evidence = VisualEvidenceStatus(
        state="not-required",
        ready=True,
        required=False,
        manifest_path=tmp_path / "visual-evidence.json",
    )
    monkeypatch.setattr(
        status,
        "load_state",
        lambda: {
            "issues": [actionable.to_dict(), investigative.to_dict()],
            "resolved": [],
            "stats": {},
        },
    )
    monkeypatch.setattr(status, "load_config", lambda: {})
    monkeypatch.setattr(status, "_git_context", lambda: ("main", False))
    monkeypatch.setattr(status, "current_verification_fresh", lambda: False)
    monkeypatch.setattr(
        status,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: evidence,
    )

    status.run(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["total_issues"] == 2
    assert payload["actionable_issues"] == 1
    assert payload["investigative_findings"] == 1
