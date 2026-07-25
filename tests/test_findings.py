from __future__ import annotations

import json
from pathlib import Path

from uidetox.findings import (
    EligibilityContext,
    Finding,
    VerificationResult,
    evaluate_eligibility,
    score_current_snapshot,
)
from uidetox.state import load_state, save_state


def _static_finding(
    path: Path,
    *,
    status: str = "pending",
    confidence: float = 0.9,
) -> Finding:
    return Finding.create(
        detector_id="SLOP-TEST",
        category="quality",
        severity="warning",
        confidence=confidence,
        message="Avoid the repeated placeholder.",
        provenance="static",
        evidence={"matched_text": "placeholder", "source_hash": "abc"},
        source_anchor={
            "path": str(path),
            "line": 2,
            "column": 4,
            "start": 12,
            "end": 23,
        },
        suppression_key="SLOP-TEST",
        verifier={"kind": "static", "detector_id": "SLOP-TEST"},
        status=status,
        display_excerpt="const value = 'placeholder'",
    )


def test_finding_round_trip_is_versioned_stable_and_forward_compatible(
    tmp_path: Path,
) -> None:
    finding = _static_finding(tmp_path / "src" / "Card.tsx")
    payload = finding.to_dict()
    payload["future_field"] = {"enabled": True}

    restored = Finding.from_dict(payload)

    assert payload["schema_version"] == 2
    assert restored.fingerprint == finding.fingerprint
    assert restored.id == finding.fingerprint
    assert restored.to_dict()["future_field"] == {"enabled": True}
    assert restored.to_dict()["source_anchor"]["start"] == 12


def test_finding_fingerprint_ignores_display_copy_but_tracks_anchor_and_evidence(
    tmp_path: Path,
) -> None:
    original = _static_finding(tmp_path / "src" / "Card.tsx")
    changed_copy = Finding.from_dict(
        {
            **original.to_dict(),
            "message": "Different remediation prose.",
            "display_excerpt": "different safe excerpt",
        }
    )
    changed_anchor = Finding.from_dict(
        {
            **original.to_dict(),
            "fingerprint": "",
            "id": "",
            "source_anchor": {
                **original.to_dict()["source_anchor"],
                "start": 13,
                "end": 24,
            },
        }
    )

    assert changed_copy.fingerprint == original.fingerprint
    assert changed_anchor.fingerprint != original.fingerprint


def test_finding_sanitizes_sensitive_matched_evidence_before_construction(
    tmp_path: Path,
) -> None:
    secret = "ghp_" + ("a" * 36)

    finding = Finding.create(
        detector_id="secret-in-client",
        category="security",
        severity="error",
        confidence=1.0,
        message="Credential-like bytes detected.",
        provenance="static",
        evidence={"matched_text": secret},
        source_anchor={"path": str(tmp_path / "client.ts"), "start": 0, "end": 40},
        verifier={"kind": "static", "detector_id": "secret-in-client"},
        display_excerpt=secret,
    )

    serialized = json.dumps(finding.to_dict())
    assert secret not in serialized
    assert "redacted" in serialized.lower()


def test_legacy_state_loads_as_canonical_without_read_time_rewrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / ".uidetox"
    state_dir.mkdir()
    state_path = state_dir / "state.json"
    legacy = {
        "issues": [
            {
                "id": "SCAN-001",
                "file": "src/Card.tsx",
                "tier": "T2",
                "issue": "Card needs review",
                "command": "uidetox polish src/Card.tsx",
                "line": 4,
            }
        ],
        "resolved": [],
        "stats": {"total_found": 1, "total_resolved": 0, "scans_run": 1},
    }
    original = json.dumps(legacy, indent=2)
    state_path.write_text(original, encoding="utf-8")

    loaded = load_state()

    assert state_path.read_text(encoding="utf-8") == original
    assert loaded["schema_version"] == 2
    assert loaded["issues"][0]["schema_version"] == 2
    assert loaded["issues"][0]["detector_id"] == "SCAN-001"
    assert loaded["issues"][0]["legacy"]["command"] == (
        "uidetox polish src/Card.tsx"
    )

    save_state(loaded)
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 2
    assert persisted["issues"][0]["fingerprint"]


def test_current_snapshot_score_ignores_historical_resolutions(tmp_path: Path) -> None:
    finding = _static_finding(tmp_path / "src" / "Card.tsx")
    state = {
        "issues": [finding.to_dict()],
        "resolved": [],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": {},
    }
    baseline = score_current_snapshot(state)
    with_history = score_current_snapshot(
        {
            **state,
            "resolved": [
                {
                    **finding.to_dict(),
                    "status": "verified_resolved",
                    "last_verification": VerificationResult(
                        outcome="absent",
                        checked_at="2026-07-25T12:00:00Z",
                        verifier_kind="static",
                    ).to_dict(),
                }
                for _ in range(50)
            ],
        }
    )

    assert with_history == baseline
    assert baseline["resolved_slop"] == 0
    assert baseline["current_slop"] > 0


def test_eligibility_returns_typed_blockers_for_every_finalization_gate(
    tmp_path: Path,
) -> None:
    finding = _static_finding(tmp_path / "src" / "Card.tsx")
    context = EligibilityContext(
        target_score=95,
        current_branch="main",
        session_branch="uidetox-session-test",
        dirty=True,
        verification_fresh=False,
        require_session_branch=True,
    )
    result = evaluate_eligibility(
        {
            "issues": [finding.to_dict()],
            "resolved": [],
            "current_snapshot": {"qualified_coverage": 0.5},
            "subjective": {"score": 100},
        },
        context,
    )

    codes = {blocker.code for blocker in result.blockers}
    assert {
        "pending_findings",
        "target_score",
        "incomplete_qualification",
        "stale_evidence",
        "missing_structured_review",
        "dirty_tree",
        "session_branch_required",
    } <= codes
    assert result.eligible is False
