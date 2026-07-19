"""First-run onboarding behavior and CLI integration."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from uidetox import cli
from uidetox import onboarding
from uidetox.agent_integration import (
    AgentProvisioningResult,
    ProvisioningStatus,
)
from uidetox.onboarding import (
    ONBOARDING_STEPS,
    OnboardingEnvironment,
    run_first_run,
)


def _environment(
    state_path: Path,
    *,
    interactive: bool = True,
    answer: str = "",
    output: list[str] | None = None,
    input_fn: Callable[[str], str] | None = None,
) -> OnboardingEnvironment:
    messages = output if output is not None else []
    return OnboardingEnvironment(
        state_path=state_path,
        interactive=interactive,
        input_fn=input_fn or (lambda _prompt: answer),
        output_fn=messages.append,
        now_fn=lambda: "2026-07-19T20:00:00+00:00",
    )


def test_interactive_first_run_persists_intro_and_pending_order(tmp_path: Path) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    output: list[str] = []

    handled = run_first_run(_environment(state_path, output=output))

    assert handled is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state == {
        "version": 1,
        "status": "in_progress",
        "completed_steps": ["intro"],
        "next_step": "agent",
        "started_at": "2026-07-19T20:00:00+00:00",
        "updated_at": "2026-07-19T20:00:00+00:00",
    }
    rendered = "\n".join(output)
    assert "UIdetox guided setup" in rendered
    assert "Next: agent" in rendered
    for step in ONBOARDING_STEPS[1:]:
        assert step in rendered


def test_interactive_first_run_resumes_without_replaying_intro(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "in_progress",
                "completed_steps": ["intro"],
                "started_at": "2026-07-19T19:00:00+00:00",
                "updated_at": "2026-07-19T19:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    output: list[str] = []
    monkeypatch.setattr(
        "uidetox.agent_integration.provision_agent_integration",
        lambda _environment: AgentProvisioningResult(
            status=ProvisioningStatus.INCOMPLETE,
            candidates=(),
            results=(),
        ),
    )

    handled = run_first_run(
        _environment(
            state_path,
            output=output,
            input_fn=lambda _prompt: pytest.fail("resume must not replay intro prompt"),
        )
    )

    assert handled is True
    rendered = "\n".join(output)
    assert "Resuming UIdetox guided setup" in rendered
    assert "Next: agent" in rendered
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_steps"] == ["intro"]
    assert state["next_step"] == "agent"


def test_noninteractive_first_run_defers_to_cli_help_without_writes(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"

    handled = run_first_run(_environment(state_path, interactive=False))

    assert handled is False
    assert not state_path.exists()


def test_completed_onboarding_defers_to_cli_help(tmp_path: Path) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "complete",
                "completed_steps": list(ONBOARDING_STEPS),
                "started_at": "2026-07-19T19:00:00+00:00",
                "updated_at": "2026-07-19T20:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    handled = run_first_run(_environment(state_path))

    assert handled is False


def test_malformed_state_recovers_to_a_valid_first_run(tmp_path: Path) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    state_path.parent.mkdir()
    state_path.write_text("{not-json", encoding="utf-8")

    handled = run_first_run(_environment(state_path))

    assert handled is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_steps"] == ["intro"]
    assert state["status"] == "in_progress"


def test_scrambled_completed_steps_reset_to_a_valid_prefix(tmp_path: Path) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    state_path.parent.mkdir()
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "in_progress",
                "completed_steps": ["agent", "intro"],
                "started_at": "2026-07-19T19:00:00+00:00",
                "updated_at": "2026-07-19T19:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    handled = run_first_run(_environment(state_path))

    assert handled is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_steps"] == ["intro"]
    assert state["next_step"] == "agent"


def test_eof_declines_first_run_without_writing_state(tmp_path: Path) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    output: list[str] = []

    def _raise_eof(_prompt: str) -> str:
        raise EOFError

    handled = run_first_run(
        _environment(state_path, output=output, input_fn=_raise_eof)
    )

    assert handled is True
    assert not state_path.exists()
    assert "Setup skipped" in "\n".join(output)


def test_atomic_save_failure_leaves_no_partial_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / ".uidetox" / "onboarding.json"
    monkeypatch.setattr(
        onboarding.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        run_first_run(_environment(state_path))

    assert not state_path.exists()
    assert list(state_path.parent.glob("*.tmp")) == []


def test_cli_no_command_uses_onboarding_when_it_handles_first_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "uidetox.onboarding.run_first_run", lambda: calls.append(1) or True
    )
    monkeypatch.setattr(cli.sys, "argv", ["uidetox"])

    cli.main()

    assert calls == [1]


def test_cli_no_command_retains_help_when_onboarding_does_not_handle(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("uidetox.onboarding.run_first_run", lambda: False)
    monkeypatch.setattr(cli.sys, "argv", ["uidetox"])

    with pytest.raises(SystemExit) as captured:
        cli.main()

    assert captured.value.code == 0
    assert "usage: uidetox" in capsys.readouterr().out


def test_cli_help_never_invokes_onboarding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "uidetox.onboarding.run_first_run",
        lambda: pytest.fail("--help must not start onboarding"),
    )
    monkeypatch.setattr(cli.sys, "argv", ["uidetox", "--help"])

    with pytest.raises(SystemExit) as captured:
        cli.main()

    assert captured.value.code == 0
