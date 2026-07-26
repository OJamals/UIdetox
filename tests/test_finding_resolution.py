from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.findings import (
    EligibilityContext,
    Finding,
    VerificationResult,
    current_verification_fresh,
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
    save_config,
    save_state,
)


@pytest.mark.parametrize("status", ("degraded", "partial", "failed", "stale"))
def test_current_verification_requires_exact_current_runtime_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    from uidetox import frontend_map

    monkeypatch.setattr(
        frontend_map,
        "load_frontend_map",
        lambda _path: SimpleNamespace(target=".", evidence={"runtime_status": status}),
    )
    monkeypatch.setattr(frontend_map, "frontend_map_is_fresh", lambda *_args: True)

    assert current_verification_fresh(tmp_path) is False


def _static(path: Path, *, start: int = 0) -> Finding:
    return Finding.create(
        detector_id="GENERIC_COPY_SLOP",
        category="copy",
        severity="warning",
        confidence=1,
        message="Generic copy",
        provenance="static",
        evidence={"matched_text": "Unlock the power"},
        source_anchor={
            "path": str(path),
            "line": 1,
            "column": 1,
            "start": start,
            "end": start + 16,
        },
        verifier={"kind": "static", "detector_id": "GENERIC_COPY_SLOP"},
    )


def test_static_verifier_distinguishes_reproduced_absent_and_stale_anchor(tmp_path):
    source = tmp_path / "copy.md"
    source.write_text("Unlock the power", encoding="utf-8")
    finding = _static(source)

    reproduced = verify_finding(finding, root=tmp_path)
    assert reproduced.outcome == "reproduced"
    assert reproduced.evidence_hash
    source.write_text("Specific product copy", encoding="utf-8")
    absent = verify_finding(finding, root=tmp_path)
    assert absent.outcome == "absent"
    assert absent.evidence_hash
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
    monkeypatch.setattr(
        frontend_map_module, "frontend_map_is_fresh", lambda *args: True
    )
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
            "state": "ready",
            "capture_id": "cart-ready-mobile",
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
                    "state": "ready",
                    "capture_id": "cart-ready-mobile",
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
            "runtime_capture_matrix": [
                {
                    "capture_id": "cart-ready-mobile",
                    "scenario": "default",
                    "state": "ready",
                    "url": "http://localhost:3000/cart",
                    "viewport": {"name": "mobile", "width": 390, "height": 844},
                    "status": "completed",
                    "diagnostics": [],
                }
            ],
            "source_manifest": {"files": {}, "project_files": {}},
        },
        "project_map": {},
    }
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )

    reproduced = verify_finding(runtime, root=tmp_path)
    assert reproduced.outcome == "reproduced"
    assert reproduced.evidence_hash
    artifact["evidence"]["runtime_capture_matrix"][0]["scenario"] = "hover"
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_evidence"
    artifact["evidence"]["runtime_capture_matrix"][0]["scenario"] = "default"
    artifact["evidence"]["runtime_capture_matrix"][0]["viewport"]["name"] = "desktop"
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_evidence"
    artifact["evidence"]["runtime_capture_matrix"][0]["viewport"]["name"] = "mobile"
    artifact["nodes"][0]["metadata"]["selector"] = "#other"
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_anchor"
    requested = json.loads(json.dumps(artifact["nodes"][0]))
    requested["id"] = "requested-selector"
    requested["metadata"]["selector"] = "#total"
    requested["metadata"]["findings"] = []
    artifact["nodes"].append(requested)
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_anchor"
    artifact["nodes"][0]["metadata"]["findings"] = []
    other_state = json.loads(json.dumps(artifact["nodes"][0]))
    other_state["id"] = "other-state"
    other_state["metadata"]["state"] = "loading"
    other_state["metadata"]["capture_id"] = "cart-loading-mobile"
    other_state["metadata"]["findings"] = [runtime.to_dict()]
    artifact["nodes"].append(other_state)
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    absent = verify_finding(runtime, root=tmp_path)
    assert absent.outcome == "absent"
    assert absent.evidence_hash
    artifact["evidence"]["runtime_status"] = "stale"
    (tmp_path / ".uidetox" / "frontend-map.json").write_text(
        json.dumps(artifact), encoding="utf-8"
    )
    assert verify_finding(runtime, root=tmp_path).outcome == "stale_evidence"


def test_runtime_diagnostic_verifier_uses_exact_capture_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uidetox.frontend_map as frontend_map_module

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    monkeypatch.setattr(
        frontend_map_module, "frontend_map_is_fresh", lambda *args: True
    )
    anchor = {
        "url": "http://localhost:3000/cart",
        "viewport": "mobile",
        "scenario": "checkout",
        "state": "ready",
        "source": "console",
        "capture_id": "checkout-ready-mobile",
    }
    finding = Finding.create(
        detector_id="browser-console-error",
        category="runtime",
        severity="error",
        confidence=1,
        message="console failed",
        provenance="runtime",
        evidence={"kind": "console", "source": "console"},
        runtime_anchor=anchor,
        verifier={
            "kind": "runtime",
            "detector_id": "browser-console-error",
            **anchor,
        },
    )
    diagnostic = {
        "kind": "console",
        "code": finding.detector_id,
        "message": finding.message,
        "severity": "error",
        "scenario": anchor["scenario"],
        "state": anchor["state"],
        "url": anchor["url"],
        "viewport": anchor["viewport"],
        "source": anchor["source"],
    }
    artifact = {
        "schema_version": 1,
        "generated_at": "now",
        "root": str(tmp_path),
        "target": ".",
        "nodes": [],
        "edges": [],
        "contracts": {"must_preserve": [], "may_change": [], "unknown": []},
        "fingerprint": {},
        "evidence": {
            "runtime_observed": True,
            "runtime_status": "current",
            "runtime_capture_matrix": [
                {
                    "capture_id": anchor["capture_id"],
                    "scenario": anchor["scenario"],
                    "state": anchor["state"],
                    "url": anchor["url"],
                    "viewport": {
                        "name": anchor["viewport"],
                        "width": 390,
                        "height": 844,
                    },
                    "status": "completed",
                    "diagnostics": [diagnostic],
                }
            ],
            "source_manifest": {"files": {}, "project_files": {}},
        },
        "project_map": {},
    }
    path = tmp_path / ".uidetox" / "frontend-map.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    assert verify_finding(finding, root=tmp_path).outcome == "reproduced"
    artifact["evidence"]["runtime_capture_matrix"][0]["diagnostics"] = []
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert verify_finding(finding, root=tmp_path).outcome == "absent"
    artifact["evidence"]["runtime_capture_matrix"][0]["capture_id"] = "stale-capture"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    assert verify_finding(finding, root=tmp_path).outcome == "stale_evidence"


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
    hashes = {"source": "a", "map": "b", "runtime": "c"}
    state = {
        "subjective": {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "score": 100,
            "rationale": "Reviewed repaired hierarchy.",
            "reviewer": "qa-agent",
            "finding_links": [finding.fingerprint],
            "region_links": ["runtime-hierarchy"],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "evidence_hashes": dict(hashes),
            "scope_validation": {
                "status": "validated",
                "evidence_hashes": dict(hashes),
                "finding_links": [finding.fingerprint],
                "region_links": ["runtime-hierarchy"],
                "capture_matrix": [
                    {"route": "/", "state": "default", "viewport": "desktop"}
                ],
            },
        }
    }
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "uidetox.findings.current_evidence_hashes", lambda _root: dict(hashes)
        )
        absent = verify_finding(finding, state=state, root=tmp_path)
        assert absent.outcome == "absent"
        assert absent.evidence_hash
        state["subjective"]["stale"] = True
        assert (
            verify_finding(finding, state=state, root=tmp_path).outcome
            == "stale_evidence"
        )
        state["subjective"]["stale"] = False
        state["subjective"]["evidence_hashes"]["source"] = "old"
        assert (
            verify_finding(finding, state=state, root=tmp_path).outcome
            == "stale_evidence"
        )
        state["subjective"]["evidence_hashes"] = hashes
        state["subjective"]["finding_links"] = []
        assert (
            verify_finding(finding, state=state, root=tmp_path).outcome
            == "stale_evidence"
        )


def test_add_issue_produces_manual_finding_linkable_by_displayed_queue_id(
    tmp_path, monkeypatch
):
    from uidetox.commands import add_issue as add_issue_command

    captured = []
    hashes = {"source": "s", "map": "m", "runtime": "r"}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(add_issue_command, "load_config", lambda: {})
    monkeypatch.setattr(add_issue_command, "add_issue", captured.append)
    add_issue_command.run(
        argparse.Namespace(
            file="src/Card.tsx",
            tier="T2",
            issue="Hierarchy needs review",
            fix_command="uidetox polish src/Card.tsx",
        )
    )
    finding = captured[0]
    queue_id = finding.to_dict()["id"]

    assert isinstance(finding, Finding)
    assert finding.provenance == "manual"
    assert finding.verifier["kind"] == "manual"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("uidetox.findings.current_evidence_hashes", lambda _root: hashes)
        assert (
            verify_finding(finding, state={}, root=tmp_path).outcome == "stale_evidence"
        )
        review = {
            "dimensions": {"A": 40, "B": 30, "C": 20, "D": 10},
            "score": 100,
            "rationale": "Reviewed the repaired hierarchy.",
            "reviewer": "qa-agent",
            "finding_links": [queue_id],
            "region_links": ["runtime-hierarchy"],
            "routes": ["/"],
            "states": ["default"],
            "viewports": ["desktop"],
            "evidence_hashes": hashes,
            "scope_validation": {
                "status": "validated",
                "evidence_hashes": hashes,
                "finding_links": [queue_id],
                "region_links": ["runtime-hierarchy"],
                "capture_matrix": [
                    {"route": "/", "state": "default", "viewport": "desktop"}
                ],
            },
        }
        assert (
            verify_finding(finding, state={"subjective": review}, root=tmp_path).outcome
            == "absent"
        )


def test_add_issue_reuses_stable_detector_identity_for_same_evidence(
    tmp_path, monkeypatch, capsys
):
    from uidetox.commands import add_issue as add_issue_command

    monkeypatch.chdir(tmp_path)
    add_issue_command.run(
        argparse.Namespace(
            file=" src/Card.tsx ",
            tier="T2",
            issue="Hierarchy   needs review",
            fix_command="uidetox   polish src/Card.tsx",
        )
    )
    first_output = capsys.readouterr().out
    add_issue_command.run(
        argparse.Namespace(
            file="src/Card.tsx",
            tier="T2",
            issue="Hierarchy needs review",
            fix_command="uidetox polish src/Card.tsx",
        )
    )
    duplicate_output = capsys.readouterr().out

    state = load_state()
    assert len(state["issues"]) == 1
    assert state["issues"][0]["detector_id"].startswith("manual-")
    assert first_output.startswith("Added issue SCAN-")
    assert duplicate_output == (
        "Issue already queued: [T2] Hierarchy needs review in src/Card.tsx\n"
    )
    assert "Added issue" not in duplicate_output


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
        lambda *_args: SimpleNamespace(nodes=(), target="."),
    )
    monkeypatch.setattr(
        frontend_map_module, "frontend_map_is_fresh", lambda *args: True
    )
    monkeypatch.setattr(
        project_map_module,
        "build_project_map",
        lambda *args: SimpleNamespace(findings=(finding,)),
    )
    reproduced = verify_finding(finding, root=tmp_path)
    assert reproduced.outcome == "reproduced"
    assert reproduced.evidence_hash
    monkeypatch.setattr(
        project_map_module,
        "build_project_map",
        lambda *args: SimpleNamespace(findings=()),
    )
    absent = verify_finding(finding, root=tmp_path)
    assert absent.outcome == "absent"
    assert absent.evidence_hash
    independent = Finding.create(
        detector_id="contract-frontend-only",
        category="contract",
        severity="warning",
        confidence=0.9,
        message="Independent route mismatch",
        provenance="contract",
        contract_anchor={"kind": "frontend_only", "normalized_path": "/users"},
        verifier={"kind": "contract", "normalized_path": "/users"},
    )
    monkeypatch.setattr(
        project_map_module,
        "build_project_map",
        lambda *args: SimpleNamespace(findings=(independent,)),
    )
    # Contract detector IDs represent families: another route is independently resolvable.
    assert verify_finding(finding, root=tmp_path).outcome == "absent"
    monkeypatch.setattr(
        frontend_map_module, "frontend_map_is_fresh", lambda *args: False
    )
    assert verify_finding(finding, root=tmp_path).outcome == "stale_evidence"


def test_state_removal_requires_absent_verification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    finding = _static(tmp_path / "copy.md")
    save_state({"issues": [finding], "resolved": [], "stats": {}})
    reproduced = VerificationResult("reproduced", "now", "static")
    absent = VerificationResult("absent", "now", "static", evidence_hash="current")

    assert remove_issue(finding.id, note="fixed", verification=reproduced) is False
    assert remove_issue(finding.id, note="fixed", verification=absent) is True
    resolved = load_state()["resolved"][0]
    assert resolved["status"] == "verified_resolved"
    assert resolved["last_verification"]["outcome"] == "absent"


def test_state_removal_rejects_unbound_absent_verification(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    finding = _static(tmp_path / "copy.md")
    save_state({"issues": [finding], "resolved": [], "stats": {}})

    assert (
        remove_issue(
            finding.id,
            verification=VerificationResult("absent", "now", "static"),
        )
        is False
    )
    assert load_state()["issues"]


def test_batch_removal_is_atomic_when_any_verifier_does_not_clear(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    one = _static(tmp_path / "one.md")
    two = Finding.create(
        detector_id="OTHER",
        category="copy",
        severity="warning",
        confidence=1,
        message="Other",
        provenance="static",
        source_anchor={"path": str(tmp_path / "two.md")},
        verifier={"kind": "static", "detector_id": "OTHER"},
    )
    save_state({"issues": [one, two], "resolved": [], "stats": {}})
    verifications = {
        one.id: VerificationResult("absent", "now", "static", evidence_hash="one"),
        two.id: VerificationResult("reproduced", "now", "static", evidence_hash="two"),
    }
    assert (
        batch_remove_issues([one.id, two.id], note="fixed", verifications=verifications)
        == []
    )
    assert len(load_state()["issues"]) == 2


def test_override_is_audited_and_remains_a_scored_finalization_blocker(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    finding = _static(tmp_path / "copy.md")
    save_state({"issues": [finding], "resolved": [], "stats": {}})
    record_verification_override(
        [finding.id],
        actor="omar",
        reason="accepted risk",
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
        resolve.run(
            argparse.Namespace(issue_id=finding.id, note="fixed", skip_verify=True)
        )
    assert len(load_state()["issues"]) == 1


@pytest.mark.parametrize(
    ("module_name", "tool", "tooling", "output"),
    [
        (
            "tsc",
            "typescript",
            {"name": "typescript", "run_cmd": "tsc --noEmit"},
            "src/App.ts(1,2): error TS2322: Type mismatch\n",
        ),
        (
            "lint",
            "linter",
            {"name": "eslint", "run_cmd": "eslint .", "fix_cmd": "eslint . --fix"},
            "src/App.ts:1:2: no-unused-vars\n",
        ),
    ],
)
def test_skip_verify_never_bypasses_originating_mechanical_tool(
    tmp_path, monkeypatch, module_name, tool, tooling, output
):
    from uidetox import mechanical
    from uidetox.commands import lint, resolve, tsc

    command_module = tsc if module_name == "tsc" else lint
    config = {"tooling": {tool: tooling}}
    captured = []
    monkeypatch.chdir(tmp_path)
    save_config(config)
    monkeypatch.setattr(command_module, "add_issue", captured.append)
    monkeypatch.setattr(
        mechanical.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 1, stdout=output, stderr=""
        ),
    )
    command_module.run(argparse.Namespace(fix=False))
    finding = captured[0]
    save_state({"issues": [finding], "resolved": [], "stats": {}})

    with pytest.raises(SystemExit):
        resolve.run(
            argparse.Namespace(
                issue_id=finding.to_dict()["id"],
                note="fixed",
                skip_verify=True,
            )
        )

    assert load_state()["issues"]


@pytest.mark.parametrize(
    ("module_name", "fixture_name", "output"),
    [
        (
            "tsc",
            "tsconfig.json",
            "src/App.ts(1,2): error TS2322: Type mismatch\n",
        ),
        (
            "lint",
            "eslint.config.js",
            "src/App.ts:1:2: no-unused-vars\n",
        ),
    ],
)
def test_detected_mechanical_tool_remains_available_to_verifier(
    tmp_path, monkeypatch, module_name, fixture_name, output
):
    from uidetox import mechanical
    from uidetox.commands import lint, tsc

    command_module = tsc if module_name == "tsc" else lint
    (tmp_path / fixture_name).write_text("{}", encoding="utf-8")
    captured = []
    runs = iter(
        [
            subprocess.CompletedProcess([], 1, stdout=output, stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(command_module, "add_issue", captured.append)
    monkeypatch.setattr(
        mechanical.subprocess, "run", lambda *_args, **_kwargs: next(runs)
    )

    command_module.run(argparse.Namespace(fix=False))
    result = verify_finding(captured[0], root=tmp_path)

    assert result.outcome == "absent"
    assert result.evidence_hash


def test_mechanical_verifier_reads_config_from_explicit_root(tmp_path, monkeypatch):
    from uidetox import mechanical

    project_root = tmp_path / "project"
    caller_root = tmp_path / "caller"
    project_root.mkdir()
    caller_root.mkdir()
    monkeypatch.chdir(project_root)
    save_config(
        {
            "tooling": {
                "typescript": {
                    "name": "typescript",
                    "run_cmd": "project-tsc --noEmit",
                }
            }
        }
    )
    finding = Finding.create(
        detector_id="mechanical-typescript-signature",
        category="code quality",
        severity="info",
        confidence=1.0,
        message="Diagnostic",
        provenance="mechanical",
        source_anchor={"path": "src/App.ts", "line": 1, "column": 1},
        verifier={
            "kind": "mechanical",
            "tool": "typescript",
            "signature": "signature",
        },
        legacy={"id": "TSC-1", "command": "tsc-fix"},
    )
    calls = []
    monkeypatch.chdir(caller_root)
    monkeypatch.setattr(
        mechanical.subprocess,
        "run",
        lambda *args, **kwargs: (
            calls.append((args, kwargs))
            or subprocess.CompletedProcess([], 0, stdout="", stderr="")
        ),
    )

    result = verify_finding(finding, root=project_root)

    assert result.outcome == "absent"
    assert calls[0][0][0] == ["project-tsc", "--noEmit"]


def test_batch_resolve_runs_matching_mechanical_recipe_once_per_command(
    tmp_path, monkeypatch
):
    from uidetox import mechanical
    from uidetox.commands import batch_resolve

    findings = [
        Finding.create(
            detector_id=f"mechanical-typescript-signature-{index}",
            category="code quality",
            severity="info",
            confidence=1.0,
            message=f"Diagnostic {index}",
            provenance="mechanical",
            source_anchor={"path": "src/App.ts", "line": index, "column": 1},
            verifier={
                "kind": "mechanical",
                "tool": "typescript",
                "signature": f"signature-{index}",
            },
            legacy={"id": f"TSC-{index}", "command": "tsc-fix"},
        )
        for index in (1, 2)
    ]
    calls = []
    monkeypatch.chdir(tmp_path)
    save_config(
        {"tooling": {"typescript": {"name": "typescript", "run_cmd": "tsc --noEmit"}}}
    )
    monkeypatch.setattr(
        mechanical.subprocess,
        "run",
        lambda *args, **kwargs: (
            calls.append((args, kwargs))
            or subprocess.CompletedProcess([], 0, stdout="", stderr="")
        ),
    )
    monkeypatch.setattr(batch_resolve, "log_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(batch_resolve, "save_session", lambda *_args, **_kwargs: None)
    args = argparse.Namespace(
        issue_ids=[finding.to_dict()["id"] for finding in findings],
        note="fixed",
        single=False,
        skip_verify=True,
        override_verifier="",
        actor="",
    )

    for _ in range(2):
        save_state({"issues": findings, "resolved": [], "stats": {}})
        batch_resolve.run(args)

    assert len(calls) == 2
    assert load_state()["issues"] == []
