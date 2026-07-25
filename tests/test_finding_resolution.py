from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.findings import (
    EligibilityContext,
    Finding,
    VerificationResult,
    evaluate_eligibility,
    score_current_snapshot,
    verify_finding,
)
from uidetox.state import (
    batch_remove_issues,
    ensure_uidetox_dir,
    load_state,
    record_verification_override,
    remove_issue,
    save_state,
)


def _static(path: Path, *, start: int = 0) -> Finding:
    return Finding.create(
        detector_id="GENERIC_COPY_SLOP",
        category="copy",
        severity="warning",
        confidence=1,
        message="Generic copy",
        provenance="static",
        evidence={"matched_text": "Unlock the power"},
        source_anchor={"path": str(path), "line": 1, "column": 1, "start": start, "end": start + 16},
        verifier={"kind": "static", "detector_id": "GENERIC_COPY_SLOP"},
    )


def test_static_verifier_distinguishes_reproduced_absent_and_stale_anchor(tmp_path):
    source = tmp_path / "copy.md"
    source.write_text("Unlock the power", encoding="utf-8")
    finding = _static(source)

    assert verify_finding(finding, root=tmp_path).outcome == "reproduced"
    source.write_text("Specific product copy", encoding="utf-8")
    assert verify_finding(finding, root=tmp_path).outcome == "absent"
    source.write_text("prefix Unlock the power", encoding="utf-8")
    assert verify_finding(finding, root=tmp_path).outcome == "stale_anchor"


def test_static_verifier_accepts_legacy_line_column_anchor(tmp_path):
    source = tmp_path / "copy.md"
    source.write_text("Unlock the power", encoding="utf-8")
    finding = Finding.create(
        detector_id="GENERIC_COPY_SLOP",
        category="copy",
        severity="warning",
        confidence=1,
        message="Generic copy",
        provenance="static",
        source_anchor={"path": "copy.md", "line": 1, "column": 1},
        verifier={"kind": "static", "detector_id": "GENERIC_COPY_SLOP"},
    )
    assert verify_finding(finding, root=tmp_path).outcome == "reproduced"


def test_runtime_verifier_requires_current_exact_scenario(tmp_path, monkeypatch):
    import uidetox.frontend_map as frontend_map_module

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    monkeypatch.setattr(frontend_map_module, "frontend_map_is_fresh", lambda *args: True)
    runtime = Finding.create(
        detector_id="runtime-text-clipped",
        category="overflow",
        severity="error",
        confidence=0.9,
        message="clipped",
        provenance="runtime",
        runtime_anchor={
            "url": "http://localhost:3000/cart",
            "viewport": "mobile",
            "selector": "#total",
            "scenario": "default",
        },
        verifier={"kind": "runtime", "detector_id": "runtime-text-clipped"},
    )
    artifact = {
        "schema_version": 1,
        "generated_at": "now",
        "root": str(tmp_path),
        "target": ".",
        "nodes": [
            {
                "id": "runtime-node",
                "kind": "runtime_text",
                "name": "Total",
                "file": "",
                "line": 0,
                "metadata": {
                    "runtime_url": "http://localhost:3000/cart",
                    "viewport": "mobile",
                    "selector": "#total",
                    "states": {},
                    "scenario": "default",
                    "findings": [runtime.to_dict()],
                },
            }
        ],
        "edges": [],
        "contracts": {"must_preserve": [], "may_change": [], "unknown": []},
        "fingerprint": {},
        "evidence": {
            "runtime_observed": True,
            "runtime_status": "current",
            "source_manifest": {"files": {}, "project_files": {}},
        },
        "project_map": {},
    }
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )

    assert verify_finding(runtime, root=tmp_path).outcome == "reproduced"
    artifact["evidence"]["runtime_status"] = "stale"
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_evidence"


def test_manual_verifier_requires_linked_structured_review(tmp_path):
    finding = Finding.create(
        detector_id="manual-hierarchy",
        category="hierarchy",
        severity="warning",
        confidence=0.8,
        message="Hierarchy needs review",
        provenance="manual",
        verifier={"kind": "manual"},
    )
    state = {
        "subjective": {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "score": 100,
            "rationale": "Reviewed repaired hierarchy.",
            "reviewer": "qa-agent",
            "finding_links": [finding.fingerprint],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "evidence_hashes": {"source": "a", "map": "b", "runtime": "c"},
        }
    }
    assert verify_finding(finding, state=state, root=tmp_path).outcome == "absent"
    state["subjective"]["finding_links"] = []
    assert verify_finding(finding, state=state, root=tmp_path).outcome == "stale_evidence"


def test_contract_verifier_rebuilds_relevant_operation_slice(tmp_path, monkeypatch):
    import uidetox.frontend_map as frontend_map_module
    import uidetox.project_map as project_map_module

    finding = Finding.create(
        detector_id="contract-frontend-only",
        category="contract",
        severity="warning",
        confidence=0.9,
        message="Frontend operation lacks backend handler.",
        provenance="contract",
        contract_anchor={"kind": "frontend_only", "normalized_path": "/orders"},
        verifier={"kind": "contract", "normalized_path": "/orders"},
    )
    monkeypatch.setattr(
        frontend_map_module,
        "load_frontend_map",
        lambda: SimpleNamespace(nodes=()),
    )
    monkeypatch.setattr(
        project_map_module,
        "build_project_map",
        lambda *args: SimpleNamespace(findings=(finding,)),
    )
    assert verify_finding(finding, root=tmp_path).outcome == "reproduced"
    monkeypatch.setattr(
        project_map_module,
        "build_project_map",
        lambda *args: SimpleNamespace(findings=()),
    )
    assert verify_finding(finding, root=tmp_path).outcome == "absent"


def test_state_removal_requires_absent_verification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    finding = _static(tmp_path / "copy.md")
    save_state({"issues": [finding], "resolved": [], "stats": {}})
    reproduced = VerificationResult("reproduced", "now", "static")
    absent = VerificationResult("absent", "now", "static")

    assert remove_issue(finding.id, note="fixed", verification=reproduced) is False
    assert remove_issue(finding.id, note="fixed", verification=absent) is True
    resolved = load_state()["resolved"][0]
    assert resolved["status"] == "verified_resolved"
    assert resolved["last_verification"]["outcome"] == "absent"


def test_batch_removal_is_atomic_when_any_verifier_does_not_clear(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    one = _static(tmp_path / "one.md")
    two = Finding.create(
        detector_id="OTHER", category="copy", severity="warning", confidence=1,
        message="Other", provenance="static", source_anchor={"path": str(tmp_path / "two.md")},
        verifier={"kind": "static", "detector_id": "OTHER"},
    )
    save_state({"issues": [one, two], "resolved": [], "stats": {}})
    verifications = {
        one.id: VerificationResult("absent", "now", "static"),
        two.id: VerificationResult("reproduced", "now", "static"),
    }
    assert batch_remove_issues([one.id, two.id], note="fixed", verifications=verifications) == []
    assert len(load_state()["issues"]) == 2


def test_override_is_audited_and_remains_a_scored_finalization_blocker(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    finding = _static(tmp_path / "copy.md")
    save_state({"issues": [finding], "resolved": [], "stats": {}})
    record_verification_override(
        [finding.id], actor="omar", reason="accepted risk",
        results={finding.id: VerificationResult("reproduced", "now", "static")},
    )
    state = load_state()
    assert state["issues"][0]["status"] == "overridden"
    assert state["resolved"] == []
    assert state["overrides"][0]["actor"] == "omar"
    assert state["overrides"][0]["reason"] == "accepted risk"
    assert score_current_snapshot(state)["current_slop"] > 0
    eligibility = evaluate_eligibility(state, EligibilityContext())
    assert not eligibility.eligible
    assert "pending_findings" in {blocker.code for blocker in eligibility.blockers}


def test_skip_verify_does_not_bypass_finding_verifier(tmp_path, monkeypatch):
    from uidetox.commands import resolve

    monkeypatch.chdir(tmp_path)
    source = tmp_path / "copy.md"
    source.write_text("Unlock the power", encoding="utf-8")
    finding = _static(source)
    save_state({"issues": [finding], "resolved": [], "stats": {}})
    with pytest.raises(SystemExit):
        resolve.run(argparse.Namespace(issue_id=finding.id, note="fixed", skip_verify=True))
    assert len(load_state()["issues"]) == 1
