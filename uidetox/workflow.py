"""Durable, opt-in execution engine for the UIdetox workflow."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from argparse import Namespace
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from uidetox.design_context import DesignSettings
from uidetox.findings import (
    EligibilityContext,
    current_evidence_hashes,
    evaluate_eligibility,
    structured_review_current,
)
from uidetox.frontend_map import (
    FRONTEND_MAP_FILE,
    frontend_map_is_fresh,
    load_frontend_map,
    map_frontend,
    retain_runtime_evidence,
    save_frontend_map,
)
from uidetox.prototype import save_prototype_brief
from uidetox.redesign import (
    RedesignBrief,
    load_redesign_set,
    propose_redesigns,
    save_redesign_set,
)
from uidetox.state import load_config, load_state
from uidetox.utils import now_iso
from uidetox.visual_semantics import project_visual_evidence_status

WORKFLOW_STATE_FILE = "workflow-state.json"
WAITING_AGENT = "waiting_for_agent"
WAITING_REVIEW = "waiting_for_review"
WAITING_SELECTION = "waiting_for_proposal_selection"
WAITING_VERIFICATION = "waiting_for_verification"


@dataclass(frozen=True)
class PhaseDefinition:
    """Static transition knowledge for one workflow phase."""

    id: str
    adapter: str
    dependencies: tuple[str, ...]
    input_keys: tuple[str, ...]
    artifact_kinds: tuple[str, ...] = ()


PHASES = (
    PhaseDefinition(
        "mechanical_checks",
        "mechanical_checks",
        (),
        ("source",),
        ("check_report",),
    ),
    PhaseDefinition(
        "static_analysis",
        "static_analysis",
        ("mechanical_checks",),
        ("source",),
        ("scan_state",),
    ),
    PhaseDefinition(
        "semantic_map",
        "semantic_map",
        ("static_analysis",),
        ("source",),
        ("frontend_map", "contract_graph"),
    ),
    PhaseDefinition(
        "issue_planning",
        "issue_planning",
        ("static_analysis",),
        ("source", "queue"),
        ("issue_plan",),
    ),
    PhaseDefinition(
        "redesign_planning",
        "redesign_planning",
        ("semantic_map", "issue_planning"),
        ("source", "design"),
        ("redesign_set",),
    ),
    PhaseDefinition(
        "prototype_generation",
        "prototype_generation",
        ("redesign_planning",),
        ("proposal",),
        ("prototype_brief",),
    ),
    PhaseDefinition(
        "subjective_review",
        "subjective_review",
        ("prototype_generation",),
        ("source", "review"),
        ("structured_review",),
    ),
    PhaseDefinition(
        "status_evaluation",
        "status_evaluation",
        ("subjective_review", "issue_planning", "semantic_map"),
        ("source", "queue", "review", "verification", "target"),
        ("status",),
    ),
    PhaseDefinition(
        "finish_eligibility",
        "finish_eligibility",
        ("status_evaluation",),
        ("source", "queue", "verification", "target"),
        ("finish_eligibility",),
    ),
)


@dataclass(frozen=True)
class WorkflowInputs:
    source_fingerprint: str
    queue_fingerprint: str
    design_fingerprint: str
    verification_fingerprint: str
    target_score: int = 95
    proposal_id: str | None = None
    review_fingerprint: str = ""
    verification_fresh: bool = True
    visual_evidence_state: str = "missing"
    visual_evidence_required: bool = False

    def value(self, key: str) -> Any:
        values = {
            "source": self.source_fingerprint,
            "queue": self.queue_fingerprint,
            "design": self.design_fingerprint,
            "verification": self.verification_fingerprint,
            "target": self.target_score,
            "proposal": self.proposal_id,
            "review": self.review_fingerprint,
        }
        return values[key]


@dataclass(frozen=True)
class AdapterResult:
    """Concise, serializable result returned by an in-process phase adapter."""

    artifacts: dict[str, str] = field(default_factory=dict)
    artifact_validation: dict[str, str] = field(default_factory=dict)
    evidence: str = ""
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowContext:
    root: Path
    inputs: WorkflowInputs
    state: dict[str, Any]
    phase: PhaseDefinition


PhaseRunner = Callable[[WorkflowContext], AdapterResult]


@dataclass(frozen=True)
class WorkflowAdapters:
    """Injected in-process functions keyed by phase adapter name."""

    runners: Mapping[str, PhaseRunner]

    def run(self, phase: PhaseDefinition, context: WorkflowContext) -> AdapterResult:
        try:
            runner = self.runners[phase.adapter]
        except KeyError as exc:
            raise KeyError(
                f"No workflow adapter registered for {phase.adapter}."
            ) from exc
        result = runner(context)
        if not isinstance(result, AdapterResult):
            raise TypeError(
                f"Workflow adapter {phase.adapter} returned "
                f"{type(result).__name__}, expected AdapterResult."
            )
        return result


@dataclass(frozen=True)
class WorkflowRunResult:
    status: str
    phase: str | None
    waiting: str | None
    message: str
    state_path: Path
    completed: tuple[str, ...]


class WorkflowPause(RuntimeError):
    def __init__(self, waiting: str, message: str) -> None:
        self.waiting = waiting
        self.message = message
        super().__init__(message)


class WorkflowEngine:
    """Execute each phase at most once per call and persist every transition."""

    def __init__(
        self,
        root: str | Path,
        adapters: WorkflowAdapters,
        *,
        state_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.adapters = adapters
        self.state_path = (
            Path(state_path).expanduser().resolve()
            if state_path is not None
            else self.root / ".uidetox" / WORKFLOW_STATE_FILE
        )
        self._executed_this_run: set[str] = set()

    def run(self, inputs: WorkflowInputs) -> WorkflowRunResult:
        self._executed_this_run = set()
        state = self._load_state(inputs.target_score)
        state["target_score"] = inputs.target_score
        state["waiting"] = None
        state["error"] = None
        self._save_state(state)
        for index, phase in enumerate(PHASES):
            precondition = self._waiting_before(phase, state, inputs)
            if precondition is not None:
                return self._wait(state, phase, *precondition)
            expected = self._phase_fingerprint(phase, state, inputs)
            phase_state = state["phases"][phase.id]
            if (
                phase_state["status"] == "completed"
                and phase_state.get("input_fingerprint") == expected
            ):
                if self._artifacts_fresh(phase, phase_state):
                    after = self._waiting_after(phase, state, inputs)
                    if after is not None:
                        return self._wait(state, phase, *after)
                    continue
                self._invalidate_from(state, index)
                phase_state = state["phases"][phase.id]
                expected = self._phase_fingerprint(phase, state, inputs)
            if phase_state["status"] == "completed":
                self._invalidate_from(state, index)
                phase_state = state["phases"][phase.id]
                expected = self._phase_fingerprint(phase, state, inputs)
            phase_state["status"] = "running"
            phase_state["attempts"] = int(phase_state.get("attempts", 0)) + 1
            phase_state["error"] = None
            phase_state["started_at"] = now_iso()
            self._save_state(state)
            try:
                result = self.adapters.run(
                    phase,
                    WorkflowContext(self.root, inputs, state, phase),
                )
            except WorkflowPause as pause:
                phase_state["status"] = "pending"
                phase_state["error"] = None
                phase_state["completed_at"] = None
                self._save_state(state)
                return self._wait(state, phase, pause.waiting, pause.message)
            except Exception as exc:  # noqa: BLE001 - workflow adapters define their own exception taxonomy
                phase_state["status"] = "failed"
                phase_state["error"] = _concise_error(exc)
                phase_state["completed_at"] = None
                state["status"] = "failed"
                state["error"] = {
                    "phase": phase.id,
                    "message": phase_state["error"],
                }
                self._save_state(state)
                return self._result(
                    state,
                    status="failed",
                    phase=phase.id,
                    message=f"{phase.id} failed: {phase_state['error']}",
                )
            validation = {
                key: result.artifact_validation.get(
                    key,
                    "inline" if ref.startswith("inline:") else "content",
                )
                for key, ref in result.artifacts.items()
            }
            artifact_fingerprints = {
                key: self._artifact_signature(ref, validation[key])
                for key, ref in result.artifacts.items()
            }
            missing_kinds = [
                kind
                for kind in phase.artifact_kinds
                if kind not in result.artifacts
                or artifact_fingerprints.get(kind) is None
            ]
            if missing_kinds:
                phase_state["status"] = "failed"
                phase_state["error"] = (
                    "Adapter did not persist required artifact(s): "
                    + ", ".join(missing_kinds)
                )
                state["status"] = "failed"
                state["error"] = {
                    "phase": phase.id,
                    "message": phase_state["error"],
                }
                self._save_state(state)
                return self._result(
                    state,
                    status="failed",
                    phase=phase.id,
                    message=f"{phase.id} failed: {phase_state['error']}",
                )
            phase_state.update(
                {
                    "status": "completed",
                    "input_fingerprint": expected,
                    "artifacts": dict(sorted(result.artifacts.items())),
                    "artifact_validation": dict(sorted(validation.items())),
                    "artifact_fingerprints": dict(
                        sorted(artifact_fingerprints.items())
                    ),
                    "signals": dict(sorted(result.signals.items())),
                    "evidence": result.evidence[:500],
                    "result_fingerprint": _stable_hash(
                        {
                            "artifacts": result.artifacts,
                            "evidence": result.evidence,
                            "signals": result.signals,
                        }
                    ),
                    "error": None,
                    "completed_at": now_iso(),
                }
            )
            state["signals"].update(result.signals)
            self._executed_this_run.add(phase.id)
            state["status"] = "running"
            self._save_state(state)
            after = self._waiting_after(phase, state, inputs)
            if after is not None:
                return self._wait(state, phase, *after)
        state["status"] = "eligible"
        state["waiting"] = None
        self._save_state(state)
        return self._result(
            state,
            status="eligible",
            phase="finish_eligibility",
            message=(
                "Workflow evidence is fresh and score/queue gates passed. "
                "Run `uidetox finish` explicitly to finalize."
            ),
        )

    def _load_state(self, target_score: int) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"Workflow state is unreadable: {self.state_path}"
                ) from exc
            if not isinstance(value, dict) or int(value.get("schema_version", 0)) != 1:
                raise ValueError("Unsupported workflow state schema.")
            for phase in PHASES:
                phase_state = value.setdefault("phases", {}).setdefault(
                    phase.id,
                    _new_phase_state(),
                )
                phase_state.setdefault("signals", {})
            value.setdefault("signals", {})
            return value
        return {
            "schema_version": 1,
            "status": "pending",
            "target_score": target_score,
            "waiting": None,
            "error": None,
            "signals": {},
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "phases": {phase.id: _new_phase_state() for phase in PHASES},
        }

    def _save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.state_path.name}.",
            dir=str(self.state_path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.state_path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def _phase_fingerprint(
        self,
        phase: PhaseDefinition,
        state: dict[str, Any],
        inputs: WorkflowInputs,
    ) -> str:
        return _stable_hash(
            {
                "phase": phase.id,
                "inputs": {key: inputs.value(key) for key in phase.input_keys},
                "dependencies": {
                    dependency: state["phases"][dependency].get("result_fingerprint")
                    for dependency in phase.dependencies
                },
            }
        )

    def _invalidate_from(self, state: dict[str, Any], index: int) -> None:
        invalidated = {PHASES[index].id}
        changed = True
        while changed:
            changed = False
            for phase in PHASES:
                if phase.id in invalidated:
                    continue
                if any(item in invalidated for item in phase.dependencies):
                    invalidated.add(phase.id)
                    changed = True
        for phase in PHASES:
            if phase.id in invalidated:
                state["phases"][phase.id] = _new_phase_state()
        state["signals"] = {}
        for phase in PHASES:
            phase_state = state["phases"][phase.id]
            if phase_state["status"] == "completed":
                state["signals"].update(phase_state.get("signals", {}))
        state["status"] = "pending"
        state["waiting"] = None
        self._save_state(state)

    def _artifacts_fresh(
        self,
        phase: PhaseDefinition,
        phase_state: dict[str, Any],
    ) -> bool:
        artifacts = dict(phase_state.get("artifacts", {}))
        validation = dict(phase_state.get("artifact_validation", {}))
        fingerprints = dict(phase_state.get("artifact_fingerprints", {}))
        if any(kind not in artifacts for kind in phase.artifact_kinds):
            return False
        for kind in phase.artifact_kinds:
            mode = validation.get(kind)
            if mode not in {"content", "exists", "inline"}:
                return False
            current = self._artifact_signature(artifacts[kind], mode)
            if current is None or current != fingerprints.get(kind):
                return False
        return True

    def _artifact_signature(self, reference: str, mode: str) -> str | None:
        if mode == "inline":
            return _stable_hash({"inline": reference})
        path_text = reference.split("#", 1)[0]
        path = Path(path_text).expanduser()
        path = path if path.is_absolute() else self.root / path
        if not path.is_file():
            return None
        if mode == "exists":
            return "exists"
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _waiting_before(
        self,
        phase: PhaseDefinition,
        state: dict[str, Any],
        inputs: WorkflowInputs,
    ) -> tuple[str, str] | None:
        if phase.id == "prototype_generation" and not inputs.proposal_id:
            return (
                WAITING_SELECTION,
                "Select a redesign proposal and rerun with `--proposal-id`.",
            )
        return None

    def _waiting_after(
        self,
        phase: PhaseDefinition,
        state: dict[str, Any],
        inputs: WorkflowInputs,
    ) -> tuple[str, str] | None:
        if phase.id == "status_evaluation":
            eligibility = state["signals"].get("eligibility", {})
            if isinstance(eligibility, Mapping) and not eligibility.get("eligible"):
                codes = {
                    blocker.get("code")
                    for blocker in eligibility.get("blockers", [])
                    if isinstance(blocker, Mapping)
                }
                waiting = (
                    WAITING_REVIEW
                    if codes & {"missing_structured_review", "stale_review"}
                    else WAITING_VERIFICATION
                    if codes & {"stale_evidence", "incomplete_qualification"}
                    else WAITING_AGENT
                )
                return waiting, "Finalization blocked: " + ", ".join(sorted(codes))
        return None

    def _wait(
        self,
        state: dict[str, Any],
        phase: PhaseDefinition,
        waiting: str,
        message: str,
    ) -> WorkflowRunResult:
        state["status"] = "waiting"
        state["waiting"] = {
            "kind": waiting,
            "phase": phase.id,
            "message": message,
        }
        self._save_state(state)
        return self._result(
            state,
            status="waiting",
            phase=phase.id,
            waiting=waiting,
            message=message,
        )

    def _result(
        self,
        state: dict[str, Any],
        *,
        status: str,
        phase: str | None,
        message: str,
        waiting: str | None = None,
    ) -> WorkflowRunResult:
        return WorkflowRunResult(
            status=status,
            phase=phase,
            waiting=waiting,
            message=message,
            state_path=self.state_path,
            completed=tuple(
                phase.id
                for phase in PHASES
                if state["phases"][phase.id]["status"] == "completed"
            ),
        )


def build_workflow_inputs(
    root: str | Path,
    *,
    target_score: int,
    proposal_id: str | None,
    require_visual_evidence: bool | None = None,
    visual_evidence_file: str | Path | None = None,
) -> WorkflowInputs:
    root_path = Path(root).expanduser().resolve()
    config = load_config()
    state = load_state()
    source_fingerprint = _source_fingerprint(root_path, config)
    queue_payload = {
        "issues": state.get("issues", []),
        "resolved": state.get("resolved", []),
    }
    map_path = root_path / ".uidetox" / FRONTEND_MAP_FILE
    verification_fresh = True
    verification_payload: dict[str, Any] = {"status": "not_mapped"}
    if map_path.exists():
        frontend_map = load_frontend_map(map_path)
        runtime_status = str(frontend_map.evidence.get("runtime_status", "absent"))
        map_fresh = frontend_map_is_fresh(frontend_map, root_path, frontend_map.target)
        verification_fresh = map_fresh and runtime_status == "current"
        verification_payload = {
            "map_fresh": map_fresh,
            "runtime_status": runtime_status,
            "generated_at": frontend_map.generated_at,
        }
    visual_status = project_visual_evidence_status(
        config,
        required=require_visual_evidence,
        manifest_path=visual_evidence_file,
    )
    verification_payload["visual_evidence"] = visual_status.to_dict()
    if visual_status.required:
        verification_fresh = verification_fresh and visual_status.ready
    return WorkflowInputs(
        source_fingerprint=source_fingerprint,
        queue_fingerprint=_stable_hash(queue_payload),
        design_fingerprint=_stable_hash(
            {
                "DESIGN_VARIANCE": config.get("DESIGN_VARIANCE", 8),
                "MOTION_INTENSITY": config.get("MOTION_INTENSITY", 6),
                "VISUAL_DENSITY": config.get("VISUAL_DENSITY", 4),
                "design_intent": config.get("design_intent", {}),
            }
        ),
        verification_fingerprint=_stable_hash(verification_payload),
        target_score=target_score,
        proposal_id=proposal_id,
        review_fingerprint=_stable_hash(state.get("subjective", {})),
        verification_fresh=verification_fresh,
        visual_evidence_state=visual_status.state,
        visual_evidence_required=visual_status.required,
    )


def in_process_adapters() -> WorkflowAdapters:
    """Build production adapters without invoking an external agent or shell CLI."""
    from uidetox.commands import check as check_command
    from uidetox.commands import plan as plan_command
    from uidetox.commands import scan as scan_command

    def mechanical(context: WorkflowContext) -> AdapterResult:
        check_command.run(Namespace(fix=True))
        return AdapterResult(
            artifacts={"check_report": "inline:mechanical-checks-complete"},
            evidence="Mechanical checks completed in process.",
        )

    def static_analysis(context: WorkflowContext) -> AdapterResult:
        scan_command.run(Namespace(path=".", since=None, output="table"))
        current = load_state()
        return AdapterResult(
            artifacts={"scan_state": "inline:" + _stable_hash(current)},
            evidence="Static analysis completed and issue state was refreshed.",
        )

    def semantic_map(context: WorkflowContext) -> AdapterResult:
        output = context.root / ".uidetox" / FRONTEND_MAP_FILE
        previous = load_frontend_map(output) if output.exists() else None
        previous_target = (
            previous.target
            if previous is not None
            and previous.root == str(context.root.resolve())
            and previous.target != "."
            else None
        )
        frontend_map = map_frontend(context.root, previous_target)
        if previous is not None:
            frontend_map = retain_runtime_evidence(previous, frontend_map)
        save_frontend_map(frontend_map, output)
        verification_fresh = (
            frontend_map_is_fresh(frontend_map, context.root, frontend_map.target)
            and frontend_map.evidence.get("runtime_status") == "current"
        )
        return AdapterResult(
            artifacts={
                "frontend_map": str(output),
                "contract_graph": f"{output}#project_map",
            },
            artifact_validation={
                "frontend_map": "content",
                "contract_graph": "content",
            },
            evidence="Semantic frontend map and contract graph persisted.",
            signals={"verification_fresh": verification_fresh},
        )

    def issue_plan(context: WorkflowContext) -> AdapterResult:
        plan_command.run(Namespace())
        current = load_state()
        pending = len(current.get("issues", []))
        return AdapterResult(
            artifacts={
                "issue_plan": "inline:"
                + _stable_hash(
                    {
                        "issues": current.get("issues", []),
                        "resolved": current.get("resolved", []),
                    }
                )
            },
            evidence=f"Issue plan contains {pending} pending issue(s).",
            signals={"issues_pending": pending},
        )

    def redesign(context: WorkflowContext) -> AdapterResult:
        frontend_map = load_frontend_map(context.root / ".uidetox" / FRONTEND_MAP_FILE)
        settings = DesignSettings.from_config(
            load_config(),
            frontend_map,
            frontend_map.target,
        )
        brief = RedesignBrief(
            target=frontend_map.target,
            variants=3,
            design_variance=settings.dials.design_variance,
            motion_intensity=settings.dials.motion_intensity,
            visual_density=settings.dials.visual_density,
            intent=settings.intent,
        )
        output = save_redesign_set(propose_redesigns(frontend_map, brief))
        return AdapterResult(
            artifacts={"redesign_set": str(output)},
            evidence="Source-aware redesign proposals persisted.",
        )

    def prototype(context: WorkflowContext) -> AdapterResult:
        redesigns = load_redesign_set()
        proposal_id = context.inputs.proposal_id
        if proposal_id is None:
            raise ValueError("A proposal ID is required.")
        output = save_prototype_brief(redesigns, proposal_id)
        return AdapterResult(
            artifacts={"prototype_brief": str(output)},
            evidence=f"Prototype brief generated for {proposal_id}.",
        )

    def subjective_review(context: WorkflowContext) -> AdapterResult:
        current = load_state()
        review = current.get("subjective", {})
        hashes = current_evidence_hashes(context.root)
        if not isinstance(review, Mapping) or not structured_review_current(
            review, hashes
        ):
            raise WorkflowPause(
                WAITING_REVIEW,
                "Record a current structured review with `uidetox review`, then resume.",
            )
        return AdapterResult(
            artifacts={"structured_review": "inline:" + _stable_hash(review)},
            evidence="Current structured subjective review confirmed.",
        )

    def status(context: WorkflowContext) -> AdapterResult:
        current = load_state()
        fresh = (
            bool(context.state["signals"].get("verification_fresh", False))
            if "semantic_map" in context.state.get("phases", {})
            else context.inputs.verification_fresh
        )
        eligibility = evaluate_eligibility(
            current,
            EligibilityContext(
                target_score=context.inputs.target_score,
                verification_fresh=fresh,
                evidence_hashes=current_evidence_hashes(context.root),
            ),
        )
        payload = eligibility.to_dict()
        scores = payload["score"]
        return AdapterResult(
            artifacts={"status": "inline:" + json.dumps(payload, sort_keys=True)},
            evidence=f"Canonical eligibility: {payload['eligible']}.",
            signals={
                "blended_score": scores["blended_score"],
                "issues_pending": len(current.get("issues", [])),
                "eligibility": payload,
                "visual_evidence_state": context.inputs.visual_evidence_state,
                "visual_evidence_required": (context.inputs.visual_evidence_required),
            },
        )

    def finish_eligibility(context: WorkflowContext) -> AdapterResult:
        eligibility = context.state["signals"].get("eligibility", {})
        if not isinstance(eligibility, Mapping) or not eligibility.get("eligible"):
            raise RuntimeError("Canonical finalization eligibility is not satisfied.")
        return AdapterResult(
            artifacts={"finish_eligibility": "inline:verified"},
            evidence=(
                "Score, queue, and freshness gates passed. "
                "Finalization remains an explicit command."
            ),
            signals={"finish_eligible": True},
        )

    return WorkflowAdapters(
        {
            "mechanical_checks": mechanical,
            "static_analysis": static_analysis,
            "semantic_map": semantic_map,
            "issue_planning": issue_plan,
            "redesign_planning": redesign,
            "prototype_generation": prototype,
            "subjective_review": subjective_review,
            "status_evaluation": status,
            "finish_eligibility": finish_eligibility,
        }
    )


def run_executable_workflow(
    root: str | Path,
    *,
    target_score: int = 95,
    proposal_id: str | None = None,
    require_visual_evidence: bool | None = None,
    visual_evidence_file: str | Path | None = None,
    adapters: WorkflowAdapters | None = None,
    inputs: WorkflowInputs | None = None,
    state_path: str | Path | None = None,
) -> WorkflowRunResult:
    active_inputs = inputs or build_workflow_inputs(
        root,
        target_score=target_score,
        proposal_id=proposal_id,
        require_visual_evidence=require_visual_evidence,
        visual_evidence_file=visual_evidence_file,
    )
    return WorkflowEngine(
        root,
        adapters or in_process_adapters(),
        state_path=state_path,
    ).run(active_inputs)


def _source_fingerprint(root: Path, config: dict[str, Any]) -> str:
    ignored = {
        ".git",
        ".agents",
        ".claude",
        ".codebase-memory",
        ".cursor",
        ".next",
        ".nuxt",
        ".uidetox",
        ".venv",
        "build",
        "coverage",
        "dist",
        "factory",
        "node_modules",
        "out",
        "vendor",
        *{
            str(item).strip("/")
            for item in config.get("exclude", [])
            if str(item).strip("/")
        },
    }
    source_extensions = {
        ".astro",
        ".css",
        ".go",
        ".html",
        ".java",
        ".js",
        ".jsx",
        ".json",
        ".kt",
        ".less",
        ".md",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".sass",
        ".scss",
        ".svelte",
        ".ts",
        ".tsx",
        ".vue",
        ".yaml",
        ".yml",
    }
    source_names = {
        "Cargo.toml",
        "go.mod",
        "package.json",
        "pyproject.toml",
    }
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if filename in source_names or path.suffix.lower() in source_extensions:
                files.append(path)
    manifest: dict[str, str] = {}
    for path in files:
        try:
            relative = path.relative_to(root).as_posix()
            manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            manifest[str(path)] = "unreadable"
    return _stable_hash(manifest)


def _new_phase_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "attempts": 0,
        "input_fingerprint": None,
        "result_fingerprint": None,
        "artifacts": {},
        "artifact_validation": {},
        "artifact_fingerprints": {},
        "signals": {},
        "evidence": "",
        "error": None,
        "started_at": None,
        "completed_at": None,
    }


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _concise_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    return f"{type(error).__name__}: {message}"[:500]
