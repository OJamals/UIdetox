"""Resumable first-run onboarding for the UIdetox CLI."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from uidetox.design_context import DesignSettings
from uidetox.intent_journal import record_intent_artifacts
from uidetox.state import get_uidetox_dir

ONBOARDING_VERSION = 1
ONBOARDING_STEPS = ("intro", "agent", "capabilities", "intent", "handoff")
_STEP_DESCRIPTIONS = {
    "agent": "install UIdetox skills and instructions for your coding agent",
    "capabilities": "optionally add codebase-memory, Pillow, Playwright, and Chromium",
    "intent": "capture the website purpose, audience, primary job, and constraints",
    "handoff": "save a provenance-linked prompt for your coding agent",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _system_is_interactive() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


@dataclass(frozen=True)
class OnboardingEnvironment:
    """Process and filesystem inputs for one onboarding run."""

    state_path: Path
    interactive: bool
    input_fn: Callable[[str], str]
    output_fn: Callable[[str], None]
    now_fn: Callable[[], str]

    @classmethod
    def from_system(cls) -> OnboardingEnvironment:
        return cls(
            state_path=get_uidetox_dir() / "onboarding.json",
            interactive=_system_is_interactive(),
            input_fn=input,
            output_fn=print,
            now_fn=_utc_now,
        )


@dataclass(frozen=True)
class _OnboardingState:
    completed_steps: tuple[str, ...] = ()
    started_at: str = ""
    updated_at: str = ""

    @property
    def status(self) -> str:
        if self.completed_steps == ONBOARDING_STEPS:
            return "complete"
        if self.completed_steps:
            return "in_progress"
        return "not_started"

    @property
    def pending_steps(self) -> tuple[str, ...]:
        return tuple(
            step for step in ONBOARDING_STEPS if step not in self.completed_steps
        )

    @property
    def next_step(self) -> str | None:
        return self.pending_steps[0] if self.pending_steps else None

    def complete(self, step: str, timestamp: str) -> _OnboardingState:
        completed = tuple(
            candidate
            for candidate in ONBOARDING_STEPS
            if candidate in {*self.completed_steps, step}
        )
        return _OnboardingState(
            completed_steps=completed,
            started_at=self.started_at or timestamp,
            updated_at=timestamp,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": ONBOARDING_VERSION,
            "status": self.status,
            "completed_steps": list(self.completed_steps),
            "next_step": self.next_step,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


def _normalize_state(payload: object) -> _OnboardingState:
    if not isinstance(payload, Mapping) or payload.get("version") != ONBOARDING_VERSION:
        return _OnboardingState()

    raw_completed = payload.get("completed_steps")
    if not isinstance(raw_completed, list):
        raw_completed = []
    completed_prefix: list[str] = []
    for index, value in enumerate(raw_completed):
        if index >= len(ONBOARDING_STEPS) or value != ONBOARDING_STEPS[index]:
            break
        completed_prefix.append(value)
    completed = tuple(completed_prefix)
    started_at = payload.get("started_at")
    updated_at = payload.get("updated_at")
    return _OnboardingState(
        completed_steps=completed,
        started_at=started_at if isinstance(started_at, str) else "",
        updated_at=updated_at if isinstance(updated_at, str) else "",
    )


def _load_state(path: Path) -> _OnboardingState:
    if not path.exists():
        return _OnboardingState()
    try:
        return _normalize_state(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _OnboardingState()


def _save_state(path: Path, state: _OnboardingState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state.to_dict(), stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _load_onboarding_config(state_path: Path) -> dict[str, object]:
    config_path = state_path.parent / "config.json"
    if not config_path.exists():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_onboarding_config(
    state_path: Path,
    config: dict[str, object],
) -> None:
    config_path = state_path.parent / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, config_path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _confirmed_start(environment: OnboardingEnvironment) -> bool:
    try:
        answer = environment.input_fn("Start guided setup now? [Y/n] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() not in {"n", "no"}


def _render_pending(
    environment: OnboardingEnvironment,
    state: _OnboardingState,
) -> None:
    pending = state.pending_steps
    if not pending:
        return
    environment.output_fn(f"Next: {pending[0]}")
    environment.output_fn("Remaining setup:")
    for step in pending:
        environment.output_fn(f"  - {step}: {_STEP_DESCRIPTIONS[step]}")


def run_first_run(environment: OnboardingEnvironment | None = None) -> bool:
    """Handle an interactive no-command invocation.

    Returns ``True`` when onboarding produced the CLI response. ``False`` asks
    the caller to retain the normal help behavior.
    """

    environment = environment or OnboardingEnvironment.from_system()
    if not environment.interactive:
        return False

    state = _load_state(environment.state_path)
    if state.status == "complete":
        _save_state(environment.state_path, state)
        return False

    starting_now = state.status == "not_started"
    if starting_now:
        environment.output_fn("UIdetox guided setup")
        environment.output_fn(
            "Configure your agent, optional analysis tools, website intent, "
            "and a copy-ready handoff."
        )
        if not _confirmed_start(environment):
            environment.output_fn("Setup skipped. Run `uidetox` again when ready.")
            return True
        state = state.complete("intro", environment.now_fn())
        _save_state(environment.state_path, state)
    else:
        _save_state(environment.state_path, state)
        environment.output_fn("Resuming UIdetox guided setup")

    entry_step = state.next_step
    if not starting_now and state.next_step == "agent":
        from uidetox.agent_integration import (
            AgentIntegrationEnvironment,
            provision_agent_integration,
        )

        agent_result = provision_agent_integration(
            AgentIntegrationEnvironment.from_system(
                interactive=environment.interactive,
                input_fn=environment.input_fn,
                output_fn=environment.output_fn,
            )
        )
        if agent_result.complete:
            state = state.complete("agent", environment.now_fn())
            _save_state(environment.state_path, state)

    if state.next_step == "capabilities":
        from uidetox.capabilities import (
            CapabilityEnvironment,
            provision_capabilities,
        )

        capability_result = provision_capabilities(
            CapabilityEnvironment.from_system(
                interactive=environment.interactive,
                input_fn=environment.input_fn,
                output_fn=environment.output_fn,
            )
        )
        if capability_result.complete:
            state = state.complete("capabilities", environment.now_fn())
            _save_state(environment.state_path, state)

    if state.next_step == "intent" and entry_step == "intent":
        from uidetox.commands.setup import capture_interactive_intent

        config = _load_onboarding_config(environment.state_path)
        settings, intent_changed = capture_interactive_intent(
            config,
            input_fn=environment.input_fn,
            output_fn=environment.output_fn,
            confirmed_at=environment.now_fn(),
        )
        if intent_changed:
            config.update(settings.dials.to_config())
            _save_onboarding_config(environment.state_path, config)
        if settings.intent.confirmation_status == "confirmed":
            state = state.complete("intent", environment.now_fn())
            _save_state(environment.state_path, state)
        else:
            environment.output_fn(
                "Website intent is not confirmed. Provide the product goal, "
                "audience, and primary job to continue."
            )

    if state.next_step == "handoff":
        config = _load_onboarding_config(environment.state_path)
        intent = DesignSettings.from_config(config).intent
        if intent.confirmation_status == "confirmed":
            artifacts = record_intent_artifacts(
                intent,
                source="onboarding:interactive",
                project_root=environment.state_path.parent.parent,
                uidetox_dir=environment.state_path.parent,
            )
            environment.output_fn(f"Intent event saved: {artifacts.event['event_id']}")
            environment.output_fn(f"Agent handoff saved: {artifacts.handoff_path}")
            environment.output_fn("Copy-ready agent prompt:")
            environment.output_fn(artifacts.prompt)
            state = state.complete("handoff", environment.now_fn())
            _save_state(environment.state_path, state)

    _render_pending(environment, state)
    return True
