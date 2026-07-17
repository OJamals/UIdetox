from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from uidetox.cli import parse_args
from uidetox.commands import loop as loop_command
from uidetox.workflow import (
    AdapterResult,
    PHASES,
    WAITING_AGENT,
    WAITING_REVIEW,
    WAITING_SELECTION,
    WAITING_VERIFICATION,
    WorkflowAdapters,
    WorkflowEngine,
    WorkflowInputs,
    build_workflow_inputs,
)


class FakeWorkflow:
    def __init__(
        self,
        *,
        pending: int = 0,
        score: int = 100,
        verification_fresh: bool = True,
        fail_once: str | None = None,
    ) -> None:
        self.pending = pending
        self.score = score
        self.verification_fresh = verification_fresh
        self.fail_once = fail_once
        self.calls: list[str] = []
        self._failed = False

    def run(self, context) -> AdapterResult:
        phase = context.phase.id
        self.calls.append(phase)
        if phase == self.fail_once and not self._failed:
            self._failed = True
            raise RuntimeError(f"{phase} exploded with noisy details\nand a traceback")
        signals = {}
        if phase == "semantic_map":
            signals["verification_fresh"] = self.verification_fresh
        if phase == "issue_planning":
            signals["issues_pending"] = self.pending
        if phase == "status_evaluation":
            signals.update(
                {
                    "issues_pending": self.pending,
                    "blended_score": self.score,
                }
            )
        if phase == "semantic_map":
            artifact = context.root / ".uidetox" / "frontend-map.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"schema_version": 1}\n', encoding="utf-8")
            artifacts = {
                "frontend_map": str(artifact),
                "project_map": f"{artifact}#project_map",
            }
        else:
            artifacts = {
                kind: f"inline:{phase}:{kind}"
                for kind in context.phase.artifact_kinds
            }
        return AdapterResult(
            artifacts=artifacts,
            evidence=f"{phase} complete",
            signals=signals,
        )

    def adapters(self) -> WorkflowAdapters:
        return WorkflowAdapters(
            {phase.adapter: self.run for phase in PHASES}
        )


def _inputs(
    *,
    source: str = "source-v1",
    queue: str = "queue-v1",
    design: str = "design-v1",
    verification: str = "verification-v1",
    proposal: str | None = "REDESIGN-01-task-flow",
    score: int | None = 100,
    fresh: bool = True,
    target: int = 95,
) -> WorkflowInputs:
    return WorkflowInputs(
        source_fingerprint=source,
        queue_fingerprint=queue,
        design_fingerprint=design,
        verification_fingerprint=verification,
        target_score=target,
        proposal_id=proposal,
        subjective_score=score,
        verification_fresh=fresh,
    )


def _engine(tmp_path, fake: FakeWorkflow) -> WorkflowEngine:
    return WorkflowEngine(
        tmp_path,
        fake.adapters(),
        state_path=tmp_path / ".uidetox" / "workflow-state.json",
    )


def test_workflow_happy_path_is_durable_and_finish_is_only_eligible(
    tmp_path,
) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)

    result = engine.run(_inputs())
    state = json.loads(result.state_path.read_text(encoding="utf-8"))

    assert result.status == "eligible"
    assert result.phase == "finish_eligibility"
    assert fake.calls == [phase.id for phase in PHASES]
    assert all(item["status"] == "completed" for item in state["phases"].values())
    assert state["phases"]["finish_eligibility"]["artifacts"] == {
        "finish_eligibility": "inline:finish_eligibility:finish_eligibility"
    }
    assert "Run `uidetox finish` explicitly" in result.message
    assert list(result.state_path.parent.glob(".workflow-state.json.*")) == []


def test_workflow_waits_for_agent_then_selectively_resumes_issue_dependents(
    tmp_path,
) -> None:
    fake = FakeWorkflow(pending=2)
    engine = _engine(tmp_path, fake)

    waiting = engine.run(_inputs(queue="queue-with-issues"))
    assert waiting.waiting == WAITING_AGENT
    assert fake.calls == [
        "mechanical_checks",
        "static_analysis",
        "semantic_map",
        "issue_planning",
    ]

    fake.pending = 0
    resumed = engine.run(_inputs(queue="queue-empty"))

    assert resumed.status == "eligible"
    assert fake.calls.count("mechanical_checks") == 1
    assert fake.calls.count("semantic_map") == 1
    assert fake.calls.count("issue_planning") == 2
    assert fake.calls[-5:] == [
        "redesign_planning",
        "prototype_generation",
        "subjective_review",
        "status_evaluation",
        "finish_eligibility",
    ]


def test_workflow_waits_for_explicit_proposal_selection(tmp_path) -> None:
    fake = FakeWorkflow()
    result = _engine(tmp_path, fake).run(_inputs(proposal=None))

    assert result.waiting == WAITING_SELECTION
    assert result.phase == "prototype_generation"
    assert fake.calls[-1] == "redesign_planning"
    assert "prototype_generation" not in fake.calls


def test_workflow_waits_for_subjective_review_input(tmp_path) -> None:
    fake = FakeWorkflow()
    result = _engine(tmp_path, fake).run(_inputs(score=None))

    assert result.waiting == WAITING_REVIEW
    assert result.phase == "subjective_review"
    assert fake.calls[-1] == "prototype_generation"


def test_workflow_waits_when_verification_is_stale_or_blocked(tmp_path) -> None:
    fake = FakeWorkflow(verification_fresh=False)
    result = _engine(tmp_path, fake).run(_inputs())

    assert result.waiting == WAITING_VERIFICATION
    assert result.phase == "status_evaluation"
    assert fake.calls[-1] == "subjective_review"
    assert "status_evaluation" not in fake.calls


def test_failed_phase_is_retryable_and_never_completes_later_phases(
    tmp_path,
) -> None:
    fake = FakeWorkflow(fail_once="static_analysis")
    engine = _engine(tmp_path, fake)

    failed = engine.run(_inputs())
    failed_state = json.loads(failed.state_path.read_text(encoding="utf-8"))

    assert failed.status == "failed"
    assert failed.phase == "static_analysis"
    assert failed_state["phases"]["static_analysis"]["attempts"] == 1
    assert failed_state["phases"]["semantic_map"]["status"] == "pending"
    assert "\n" not in failed_state["phases"]["static_analysis"]["error"]

    resumed = engine.run(_inputs())
    resumed_state = json.loads(resumed.state_path.read_text(encoding="utf-8"))

    assert resumed.status == "eligible"
    assert fake.calls.count("mechanical_checks") == 1
    assert fake.calls.count("static_analysis") == 2
    assert resumed_state["phases"]["static_analysis"]["attempts"] == 2


def test_fresh_completed_phases_are_idempotent_on_resume(tmp_path) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)

    first = engine.run(_inputs())
    first_calls = list(fake.calls)
    second = engine.run(_inputs())

    assert first.status == second.status == "eligible"
    assert fake.calls == first_calls


def test_missing_persisted_artifact_regenerates_phase_and_dependents(
    tmp_path,
) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)
    first = engine.run(_inputs())
    state = json.loads(first.state_path.read_text(encoding="utf-8"))
    artifact = state["phases"]["semantic_map"]["artifacts"]["frontend_map"]
    baseline_count = len(fake.calls)
    Path(artifact).unlink()

    resumed = engine.run(_inputs())

    assert resumed.status == "eligible"
    assert fake.calls[baseline_count:] == [
        "semantic_map",
        "redesign_planning",
        "prototype_generation",
        "subjective_review",
        "status_evaluation",
        "finish_eligibility",
    ]
    after_missing = len(fake.calls)
    Path(artifact).write_text('{"tampered": true}\n', encoding="utf-8")

    repaired = engine.run(_inputs())

    assert repaired.status == "eligible"
    assert fake.calls[after_missing:] == [
        "semantic_map",
        "redesign_planning",
        "prototype_generation",
        "subjective_review",
        "status_evaluation",
        "finish_eligibility",
    ]


def test_artifact_invalidation_preserves_unaffected_issue_gate_signal(
    tmp_path,
) -> None:
    fake = FakeWorkflow(pending=2)
    engine = _engine(tmp_path, fake)
    first = engine.run(_inputs(queue="queue-with-issues"))
    state = json.loads(first.state_path.read_text(encoding="utf-8"))
    artifact = Path(
        state["phases"]["semantic_map"]["artifacts"]["frontend_map"]
    )
    artifact.unlink()
    baseline_count = len(fake.calls)

    resumed = engine.run(_inputs(queue="queue-with-issues"))
    resumed_state = json.loads(resumed.state_path.read_text(encoding="utf-8"))

    assert resumed.waiting == WAITING_AGENT
    assert fake.calls[baseline_count:] == ["semantic_map"]
    assert fake.calls.count("issue_planning") == 1
    assert resumed_state["signals"]["issues_pending"] == 2


def test_input_changes_invalidate_only_dependent_downstream_phases(
    tmp_path,
) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)
    engine.run(_inputs())
    baseline_count = len(fake.calls)

    engine.run(_inputs(proposal="REDESIGN-02-object-workspace"))
    assert fake.calls[baseline_count:] == [
        "prototype_generation",
        "subjective_review",
        "status_evaluation",
        "finish_eligibility",
    ]
    after_proposal = len(fake.calls)

    engine.run(
        _inputs(
            proposal="REDESIGN-02-object-workspace",
            score=98,
        )
    )
    assert fake.calls[after_proposal:] == [
        "subjective_review",
        "status_evaluation",
        "finish_eligibility",
    ]


def test_source_change_invalidates_every_dependent_phase(tmp_path) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)
    engine.run(_inputs())
    baseline_count = len(fake.calls)

    engine.run(_inputs(source="source-v2"))

    assert fake.calls[baseline_count:] == [phase.id for phase in PHASES]


def test_external_verification_change_controls_status_gate(tmp_path) -> None:
    fake = FakeWorkflow()
    engine = _engine(tmp_path, fake)
    engine.run(_inputs())
    baseline_count = len(fake.calls)

    waiting = engine.run(
        _inputs(
            verification="verification-stale",
            fresh=False,
        )
    )

    assert waiting.waiting == WAITING_VERIFICATION
    assert fake.calls[baseline_count:] == []


def test_loop_preview_remains_default_and_does_not_create_workflow_state(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text(
        "export function App() { return <main />; }",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    loop_command.run(
        Namespace(
            target=95,
            orchestrator=False,
            execute=False,
            proposal_id=None,
            review_score=None,
        )
    )
    output = capsys.readouterr().out

    assert "THE LOOP PROTOCOL" in output
    assert "Run `uidetox scan --path .`" in output
    assert not (tmp_path / ".uidetox" / "workflow-state.json").exists()


def test_cli_documents_execute_inputs_and_keeps_preview_default() -> None:
    preview = parse_args(["loop"])
    execute = parse_args(
        [
            "loop",
            "--execute",
            "--proposal-id",
            "REDESIGN-01-task-flow",
            "--review-score",
            "97",
        ]
    )

    assert preview.execute is False
    assert execute.execute is True
    assert execute.proposal_id == "REDESIGN-01-task-flow"
    assert execute.review_score == 97


def test_workflow_inputs_track_backend_source_and_design_dials(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text(
        "export function App() { return <main />; }",
        encoding="utf-8",
    )
    backend = tmp_path / "api.py"
    backend.write_text("@app.get('/items')\ndef items(): ...\n", encoding="utf-8")
    uidetox_dir = tmp_path / ".uidetox"
    uidetox_dir.mkdir()
    config_path = uidetox_dir / "config.json"
    config_path.write_text('{"DESIGN_VARIANCE": 8}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    first = build_workflow_inputs(
        tmp_path,
        target_score=95,
        proposal_id=None,
        subjective_score=None,
    )
    backend.write_text("@app.post('/items')\ndef items(): ...\n", encoding="utf-8")
    second = build_workflow_inputs(
        tmp_path,
        target_score=95,
        proposal_id=None,
        subjective_score=None,
    )
    config_path.write_text('{"DESIGN_VARIANCE": 9}\n', encoding="utf-8")
    third = build_workflow_inputs(
        tmp_path,
        target_score=95,
        proposal_id=None,
        subjective_score=None,
    )

    assert first.source_fingerprint != second.source_fingerprint
    assert second.design_fingerprint != third.design_fingerprint
