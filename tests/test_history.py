import json
from pathlib import Path

import pytest

from uidetox import history
from uidetox.visual_evidence import VisualEvidenceStatus


def test_history_snapshot_records_visual_evidence_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = VisualEvidenceStatus(
        state="fresh",
        ready=True,
        required=True,
        manifest_path=tmp_path / "visual-evidence.json",
        comparisons=2,
    )
    monkeypatch.setattr(history, "_history_dir", lambda: tmp_path)
    monkeypatch.setattr(
        history,
        "load_state",
        lambda: {"issues": [], "resolved": [], "stats": {}},
    )
    monkeypatch.setattr(history, "load_config", lambda: {})
    monkeypatch.setattr(
        history,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: evidence,
    )

    snapshot_path = history.save_run_snapshot(trigger="visual-test")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot["visual_evidence"]["state"] == "fresh"
    assert snapshot["visual_evidence"]["required"] is True
    assert history.compare_runs()[0]["visual_evidence_state"] == "fresh"
