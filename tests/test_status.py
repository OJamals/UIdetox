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
    )
    monkeypatch.setattr(status, "load_state", _state)
    monkeypatch.setattr(status, "load_config", lambda: {})
    monkeypatch.setattr(status, "get_session", lambda: None)
    monkeypatch.setattr(
        status,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: evidence,
    )

    status.run(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["visual_evidence"]["state"] == "fresh"
    assert payload["visual_evidence"]["comparisons"] == 4


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
    assert json.loads(capsys.readouterr().out)["visual_evidence"]["state"] == (
        "stale"
    )
