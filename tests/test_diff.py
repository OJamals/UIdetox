"""Regression coverage for machine-readable diff output."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.commands import diff
from uidetox.findings import Finding


def _finding(path: Path, line: int) -> Finding:
    return Finding.create(
        detector_id="SLOP-JSON",
        category="quality",
        severity="warning",
        confidence=0.9,
        message=f"Avoid placeholder {line}.",
        provenance="static",
        evidence={"matched_text": "placeholder", "metrics": {"count": line}},
        source_anchor={"path": str(path), "line": line, "column": 1},
        suppression_key="SLOP-JSON",
        verifier={"kind": "static", "detector_id": "SLOP-JSON"},
    )


def test_diff_json_projects_canonical_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = _finding(tmp_path / "current.py", 1)
    introduced = _finding(tmp_path / "introduced.py", 2)
    resolved = _finding(tmp_path / "resolved.py", 3)

    monkeypatch.setattr(diff, "load_config", lambda: {})
    monkeypatch.setattr(
        diff,
        "load_state",
        lambda: {"diff_baseline": [current.to_dict(), resolved.to_dict()]},
    )
    monkeypatch.setattr(diff, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        diff,
        "_analyze_target",
        lambda *_args, **_kwargs: [current, introduced],
    )

    diff.run(SimpleNamespace(path=".", since=None, output="json", save=False))

    payload = json.loads(capsys.readouterr().out)
    assert [row["fingerprint"] for row in payload["new"]] == [introduced.fingerprint]
    assert [row["fingerprint"] for row in payload["fixed"]] == [resolved.fingerprint]
    assert [row["fingerprint"] for row in payload["unchanged"]] == [current.fingerprint]
    for rows in (payload["new"], payload["fixed"], payload["unchanged"]):
        assert all(isinstance(row, dict) for row in rows)
        assert all(row["schema_version"] == 2 for row in rows)
