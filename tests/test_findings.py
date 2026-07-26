from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from uidetox.analyzer_engine import _analyze_rule, analyze_file
from uidetox.findings import (
    EligibilityContext,
    Finding,
    VerificationResult,
    evaluate_eligibility,
    score_current_snapshot,
)
from uidetox.project_map import ContractNode, SourceAnchor, reconcile_contract_graph
from uidetox.runtime_layout import detect_runtime_findings
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


@pytest.mark.parametrize(
    ("provenance", "anchor"),
    [
        (
            "runtime",
            {
                "runtime_anchor": {
                    "url": "http://localhost:3000",
                    "viewport": "mobile",
                    "selector": "#total",
                    "scenario": "default",
                }
            },
        ),
        (
            "contract",
            {
                "contract_anchor": {
                    "kind": "frontend_only",
                    "normalized_path": "/orders",
                }
            },
        ),
    ],
)
def test_future_canonical_schema_preserves_type_version_and_unknown_fields(
    provenance: str, anchor: dict
) -> None:
    finding = Finding.create(
        detector_id=f"{provenance}-test",
        category="quality",
        severity="warning",
        confidence=0.9,
        message="Future canonical finding",
        provenance=provenance,
        **anchor,
    )
    payload = {**finding.to_dict(), "schema_version": 3, "future": {"mode": "new"}}

    restored = Finding.from_dict(payload)
    serialized = restored.to_dict()

    assert restored.provenance == provenance
    assert restored.schema_version == 3
    assert serialized["schema_version"] == 3
    assert serialized["future"] == {"mode": "new"}
    assert serialized[f"{provenance}_anchor"] == anchor[f"{provenance}_anchor"]


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


def test_confidence_preserves_zero_and_safely_defaults_malformed_values() -> None:
    zero = Finding.create(
        detector_id="ZERO-CONFIDENCE",
        category="quality",
        severity="info",
        confidence=0.0,
        message="Uncertain signal",
        provenance="static",
    )

    assert zero.confidence == 0.0
    assert Finding.from_dict(zero.to_dict()).confidence == 0.0
    assert Finding.from_dict(
        {**zero.to_dict(), "confidence": "not-a-number"}
    ).confidence == 0.5
    for nonfinite in (float("nan"), float("inf"), float("-inf")):
        assert Finding.from_dict(
            {**zero.to_dict(), "confidence": nonfinite}
        ).confidence == 0.5


@pytest.mark.parametrize(
    "payload",
    [
        {
            "id": "SCAN-LEGACY",
            "file": "src/Card.tsx",
            "tier": "T2",
            "issue": "Legacy finding",
            "confidence": "not-a-number",
            "line": "not-a-line",
            "column": [],
            "start": {},
            "end": "not-an-offset",
        },
        {
            "code": "runtime-text-clipped",
            "metrics": {"overflow": 12},
            "confidence": "not-a-number",
            "runtime_anchor": {"selector": "#total"},
        },
    ],
)
def test_malformed_legacy_numbers_use_safe_canonical_defaults(payload: dict) -> None:
    finding = Finding.from_dict(payload)
    serialized = finding.to_dict()

    assert finding.confidence == 0.5
    assert serialized["line"] == 0
    assert serialized["column"] == 0
    if "file" in payload:
        assert finding.source_anchor["start"] == 0
        assert finding.source_anchor["end"] == 0


def test_legacy_queue_uuid_does_not_change_detector_fingerprint() -> None:
    common = {
        "rule_id": "LOREM_IPSUM_SLOP",
        "file": "src/Card.tsx",
        "line": 8,
        "column": 3,
        "tier": "T2",
        "issue": "Placeholder copy",
        "command": "Replace copy",
    }
    first = Finding.from_dict({"id": "SCAN-AAAAAA", **common})
    second = Finding.from_dict({"id": "SCAN-BBBBBB", **common})
    another_occurrence = Finding.from_dict(
        {"id": "SCAN-CCCCCC", **common, "line": 9, "start": 120, "end": 125}
    )

    assert first.detector_id == "LOREM_IPSUM_SLOP"
    assert first.verifier["kind"] == "static"
    assert first.fingerprint == second.fingerprint
    assert another_occurrence.fingerprint != first.fingerprint


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


def test_finding_recursively_freezes_caller_owned_payloads(tmp_path: Path) -> None:
    source_anchor = {"path": str(tmp_path / "Card.tsx"), "start": 1, "end": 2}
    evidence = {"metrics": {"values": [1, 2]}}
    finding = Finding.create(
        detector_id="IMMUTABLE",
        category="quality",
        severity="warning",
        confidence=1.0,
        message="immutable",
        provenance="static",
        evidence=evidence,
        source_anchor=source_anchor,
        verifier={"kind": "static"},
    )

    source_anchor["start"] = 99
    evidence["metrics"]["values"].append(3)

    assert finding.source_anchor["start"] == 1
    assert finding.evidence["metrics"]["values"] == (1, 2)
    with pytest.raises(TypeError):
        finding.source_anchor["start"] = 7
    with pytest.raises(TypeError):
        finding.evidence["metrics"]["values"][0] = 7
    with pytest.raises(TypeError):
        finding.evidence |= {"extra": True}
    with pytest.raises(TypeError):
        dict.__setitem__(finding.evidence, "extra", True)

    thawed = finding.to_dict()
    thawed["evidence"]["metrics"]["values"].append(9)
    assert finding.evidence["metrics"]["values"] == (1, 2)


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
    assert loaded["issues"][0]["detector_id"].startswith("manual-")
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


def test_missing_qualification_evidence_cannot_score_as_clean() -> None:
    scores = score_current_snapshot({"issues": [], "resolved": [], "subjective": {}})

    assert scores["qualified_coverage"] == 0.0
    assert scores["objective_score"] == 0


def test_empty_structured_review_shell_remains_ineligible() -> None:
    state = {
        "issues": [],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": {
            "score": 100,
            "dimensions": {"A": 100, "B": 100, "C": 100, "D": 100},
            "rationale": "",
            "finding_links": [],
            "routes": [],
            "states": [],
            "viewports": [],
            "reviewer": "",
            "evidence_hashes": {},
        },
    }

    result = evaluate_eligibility(state, EligibilityContext())

    assert "missing_structured_review" in {
        blocker.code for blocker in result.blockers
    }


@pytest.mark.parametrize(
    "subjective",
    [
        {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "rationale": "Reviewed all routes.",
            "finding_links": [],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "reviewer": "agent",
            "evidence_hashes": {"source": "s", "map": "m", "runtime": "r"},
        },
        {
            "score": 100,
            "dimensions": {"A": 41, "B": 29, "C": 20, "D": 10},
            "rationale": "Reviewed all routes.",
            "finding_links": [],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "reviewer": "agent",
            "evidence_hashes": {"source": "s", "map": "m", "runtime": "r"},
        },
        {
            "score": 99,
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "rationale": "Reviewed all routes.",
            "finding_links": [],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "reviewer": "agent",
            "evidence_hashes": {"source": "s", "map": "m", "runtime": "r"},
        },
    ],
)
def test_structured_review_rejects_missing_score_over_cap_or_mismatch(
    subjective: dict,
) -> None:
    state = {
        "issues": [],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": subjective,
    }

    result = evaluate_eligibility(state, EligibilityContext())

    assert "missing_structured_review" in {
        blocker.code for blocker in result.blockers
    }


def test_investigative_findings_remain_visible_without_becoming_defects(
    tmp_path: Path,
) -> None:
    finding = Finding.create(
        detector_id="contract-unresolved",
        category="contract",
        severity="info",
        confidence=0.5,
        message="Dynamic route cannot be compared.",
        provenance="contract",
        contract_anchor={"kind": "unresolved", "normalized_path": "/api/:dynamic"},
        verifier={"kind": "contract"},
        status="investigate",
    )
    state = {
        "issues": [finding.to_dict()],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": {},
    }

    scores = score_current_snapshot(state)
    result = evaluate_eligibility(state, EligibilityContext())

    assert scores["current_slop"] == 0
    assert "pending_findings" not in {blocker.code for blocker in result.blockers}


def test_pending_critical_deterministic_finding_caps_blend_at_objective() -> None:
    critical = Finding.create(
        detector_id="runtime-sticky-occlusion",
        category="occlusion",
        severity="critical",
        confidence=1.0,
        message="Primary action is fully occluded.",
        provenance="runtime",
        verifier={"kind": "runtime"},
    )
    state = {
        "issues": [critical.to_dict()],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "score": 100,
            "rationale": "Reviewed the affected route and region.",
            "reviewer": "qa-agent",
            "finding_links": [critical.fingerprint],
            "region_links": ["runtime-primary-action"],
            "routes": ["/checkout"],
            "states": ["ready"],
            "viewports": ["mobile"],
            "evidence_hashes": {"source": "s", "map": "m", "runtime": "r"},
        },
    }

    scores = score_current_snapshot(state)

    assert scores["subjective_score"] == 100
    assert scores["blended_score"] == scores["objective_score"]
    assert scores["critical_deterministic_pending"] is True


def test_incomplete_structured_review_cannot_inflate_score_or_eligibility() -> None:
    state = {
        "issues": [],
        "current_snapshot": {"qualified_coverage": 0.8},
        "subjective": {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "score": 100,
            "rationale": "Reviewed one screenshot.",
            "reviewer": "qa-agent",
            "finding_links": ["finding-1"],
            "region_links": [],
            "routes": ["/"],
            "states": ["initial"],
            "viewports": ["desktop"],
            "evidence_hashes": {"source": "s", "map": "m", "runtime": "r"},
        },
    }

    scores = score_current_snapshot(state)
    result = evaluate_eligibility(state, EligibilityContext())

    assert scores["subjective_score"] is None
    assert scores["blended_score"] == scores["objective_score"] == 80
    assert "missing_structured_review" in {
        blocker.code for blocker in result.blockers
    }


def test_review_hash_drift_removes_subjective_score_and_blocks_finalization() -> None:
    review = {
        "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
        "score": 100,
        "rationale": "Reviewed every route and state.",
        "reviewer": "qa-agent",
        "finding_links": ["finding-1"],
        "region_links": ["runtime-region-1"],
        "routes": ["/"],
        "states": ["default"],
        "viewports": ["desktop"],
        "evidence_hashes": {"source": "old", "map": "m", "runtime": "r"},
    }
    current = {"source": "new", "map": "m", "runtime": "r"}
    state = {
        "issues": [],
        "current_snapshot": {"qualified_coverage": 1.0},
        "subjective": review,
    }
    scores = score_current_snapshot(state, evidence_hashes=current)
    eligibility = evaluate_eligibility(
        state, EligibilityContext(evidence_hashes=current)
    )
    assert scores["subjective_score"] is None
    assert "stale_review" in {blocker.code for blocker in eligibility.blockers}


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


def test_standard_rule_emits_every_ordered_source_occurrence(tmp_path: Path) -> None:
    source = tmp_path / "Card.tsx"
    source.write_text(
        "export const a = 'Lorem ipsum'; const b = 'Lorem ipsum';\n"
        "export const c = 'Lorem ipsum';\n",
        encoding="utf-8",
    )

    findings = [
        item for item in analyze_file(source) if item.detector_id == "LOREM_IPSUM_SLOP"
    ]

    assert len(findings) == 3
    assert [item.source_anchor["line"] for item in findings] == [1, 1, 2]
    assert [item.source_anchor["start"] for item in findings] == sorted(
        item.source_anchor["start"] for item in findings
    )
    assert len({item.fingerprint for item in findings}) == 3


def test_zero_width_standard_rule_terminates_and_preserves_each_anchor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "zero.tsx"
    content = "xx"
    source.write_text(content, encoding="utf-8")
    rule = {
        "id": "ZERO_WIDTH",
        "tier": "T1",
        "description": "zero-width test",
        "command": "inspect",
        "pattern": re.compile(r"(?=x)"),
    }

    findings = _analyze_rule(rule, source, content, ".tsx", 8, None)

    assert [item.source_anchor["start"] for item in findings] == [0, 1]
    assert [item.source_anchor["end"] for item in findings] == [0, 1]


def test_runtime_and_contract_producers_return_canonical_findings() -> None:
    class Element:
        tag = "p"
        measurements = {
            "hasText": True,
            "clientWidth": 120.0,
            "scrollWidth": 156.0,
            "clientHeight": 36.0,
            "scrollHeight": 36.0,
            "overflowX": "hidden",
            "overflowY": "visible",
        }

    runtime = detect_runtime_findings(Element())
    anchor = SourceAnchor(
        file="src/items.ts",
        line=4,
        framework="fetch",
        extractor="test",
        confidence=1.0,
    )
    frontend = ContractNode(
        id="client:GET:/api/items",
        kind="client_operation",
        name="GET /api/items",
        side="frontend",
        capability_status="present",
        source=anchor,
        attributes={"method": "GET", "normalized_path": "/api/items"},
    )
    contract_findings = reconcile_contract_graph((frontend,), ())

    assert runtime
    assert all(isinstance(item, Finding) for item in runtime)
    assert runtime[0].provenance == "runtime"
    assert all(isinstance(item, Finding) for item in contract_findings)
    assert contract_findings[0].provenance == "contract"
    assert contract_findings[0].contract_anchor["normalized_path"] == "/api/items"
