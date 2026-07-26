import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.commands import finish
from uidetox.visual_evidence import VisualEvidenceStatus


def test_finish_stops_before_git_mutation_when_required_evidence_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(stdout="uidetox-session-test\n")

    monkeypatch.setattr(finish.subprocess, "run", fake_run)
    monkeypatch.setattr(finish, "load_config", lambda: {})
    monkeypatch.setattr(finish, "load_state", lambda: {})
    monkeypatch.setattr(finish, "_workspace_dirty", lambda: False)
    monkeypatch.setattr(finish, "current_verification_fresh", lambda: True)
    monkeypatch.setattr(
        finish,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="stale",
            ready=False,
            required=True,
            manifest_path=tmp_path / "visual-evidence.json",
            reasons=("after source hash changed",),
        ),
    )
    monkeypatch.setattr(
        finish,
        "_detect_main_branch",
        lambda: pytest.fail("finish must stop before branch detection"),
    )

    with pytest.raises(SystemExit) as exc_info:
        finish.run(
            argparse.Namespace(
                require_visual_evidence=True,
                visual_evidence_file=None,
            )
        )

    assert exc_info.value.code == 1
    assert calls == [["git", "branch", "--show-current"]]


def test_finish_uses_canonical_pending_finding_gate_before_git_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finding = {
        "id": "manual-1",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Hierarchy defect",
        "command": "Fix hierarchy",
    }
    monkeypatch.setattr(
        finish.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(stdout="uidetox-session-test\n"),
    )
    monkeypatch.setattr(finish, "load_config", lambda: {"target_score": 95})
    monkeypatch.setattr(
        finish,
        "load_state",
        lambda: {
            "issues": [finding],
            "current_snapshot": {"qualified_coverage": 1.0},
            "subjective": {},
        },
    )
    monkeypatch.setattr(finish, "_workspace_dirty", lambda: False)
    monkeypatch.setattr(finish, "current_verification_fresh", lambda: True)
    monkeypatch.setattr(
        finish,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="fresh", ready=True, required=False, manifest_path=tmp_path / "v.json"
        ),
    )
    monkeypatch.setattr(
        finish,
        "_detect_main_branch",
        lambda: pytest.fail("eligibility must block before branch mutation"),
    )
    with pytest.raises(SystemExit):
        finish.run(argparse.Namespace(require_visual_evidence=False, visual_evidence_file=None))
