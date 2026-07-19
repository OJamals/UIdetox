import argparse
from pathlib import Path

import pytest

from uidetox.commands import review
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
