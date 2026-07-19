from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from uidetox.agent_integration import (
    SUPPORTED_AGENT_NAMES,
    Agent,
    AgentIntegrationEnvironment,
    AgentProvisioningResult,
    ProvisioningStatus,
    detect_agent_candidates,
    install_agent,
    provision_agent_integration,
)
from uidetox.capabilities import CapabilityEnvironment, CapabilityProvisioningResult
from uidetox.commands import update_skill
from uidetox.onboarding import OnboardingEnvironment, run_first_run


def _inputs(*answers: str) -> Callable[[str], str]:
    remaining = iter(answers)
    return lambda _prompt: next(remaining)


def _agent_data(root: Path) -> Path:
    data = root / "data"
    (data / "commands" / "nested").mkdir(parents=True)
    (data / "reference").mkdir()
    (data / "docs").mkdir()
    (data / "SKILL.md").write_text("uidetox skill\n", encoding="utf-8")
    (data / "AGENTS.md").write_text("uidetox agents\n", encoding="utf-8")
    (data / "commands" / "audit.md").write_text("audit\n", encoding="utf-8")
    (data / "commands" / "nested" / "polish.md").write_text(
        "polish\n",
        encoding="utf-8",
    )
    (data / "reference" / "rules.md").write_text("rules\n", encoding="utf-8")
    for agent in Agent:
        (data / "docs" / f"{agent.value.upper()}.md").write_text(
            f"{agent.value} guide\n",
            encoding="utf-8",
        )
    return data


def _environment(
    tmp_path: Path,
    *,
    data_root: Path | None = None,
    input_fn: Callable[[str], str] | None = None,
    output: list[str] | None = None,
    commands: set[str] | None = None,
    interactive: bool = True,
) -> AgentIntegrationEnvironment:
    output = output if output is not None else []
    commands = commands or set()
    return AgentIntegrationEnvironment(
        project_root=tmp_path / "project",
        home=tmp_path / "home",
        data_root=data_root or _agent_data(tmp_path),
        interactive=interactive,
        input_fn=input_fn or _inputs("n"),
        output_fn=output.append,
        which=lambda name: f"/tools/{name}" if name in commands else None,
    )


@pytest.mark.parametrize(
    ("agent", "relative_destination"),
    (
        (Agent.CLAUDE, ".claude/skills/uidetox"),
        (Agent.CURSOR, ".cursor/skills/uidetox"),
        (Agent.GEMINI, ".gemini/skills/uidetox"),
        (Agent.WINDSURF, ".windsurf/skills/uidetox"),
        (Agent.COPILOT, ".github/skills/uidetox"),
    ),
)
def test_project_provider_adapters_install_and_verify_all_bundled_assets(
    tmp_path: Path,
    agent: Agent,
    relative_destination: str,
) -> None:
    environment = _environment(tmp_path)
    destination = environment.project_root / relative_destination
    destination.mkdir(parents=True)
    unrelated = destination / "user-notes.md"
    unrelated.write_text("keep me\n", encoding="utf-8")
    root_instruction = environment.project_root / "AGENTS.md"
    root_instruction.parent.mkdir(parents=True, exist_ok=True)
    root_instruction.write_text("project-owned\n", encoding="utf-8")

    result = install_agent(agent, environment)

    assert result.success is True
    assert result.verified is True
    assert destination in result.destinations
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "uidetox skill\n"
    assert (destination / "AGENTS.md").read_text(encoding="utf-8") == (
        "uidetox agents\n"
    )
    assert (destination / "commands" / "audit.md").is_file()
    assert (destination / "commands" / "nested" / "polish.md").is_file()
    assert (destination / "reference" / "rules.md").is_file()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"
    assert root_instruction.read_text(encoding="utf-8") == "project-owned\n"


def test_cursor_adapter_writes_namespaced_rule_without_touching_siblings(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    rules = environment.project_root / ".cursor" / "rules"
    rules.mkdir(parents=True)
    sibling = rules / "project.mdc"
    sibling.write_text("project rule\n", encoding="utf-8")

    result = install_agent(Agent.CURSOR, environment)

    rule = rules / "uidetox.mdc"
    assert result.success is True
    assert rule.is_file()
    assert ".cursor/skills/uidetox/SKILL.md" in rule.read_text(encoding="utf-8")
    assert sibling.read_text(encoding="utf-8") == "project rule\n"


def test_codex_adapter_is_global_and_home_is_fully_injectable(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    project_codex = environment.project_root / ".codex"

    result = install_agent(Agent.CODEX, environment)

    skill = environment.home / ".codex" / "skills" / "uidetox"
    prompts = environment.home / ".codex" / "prompts" / "uidetox"
    assert result.success is True
    assert result.destinations == (skill, prompts)
    assert (skill / "SKILL.md").is_file()
    assert (prompts / "audit.md").is_file()
    assert (prompts / "nested" / "polish.md").is_file()
    assert not project_codex.exists()


def test_installation_is_idempotent_and_preserves_unrelated_namespaced_files(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path)
    destination = environment.project_root / ".claude" / "skills" / "uidetox"

    first = install_agent(Agent.CLAUDE, environment)
    unrelated = destination / "notes.md"
    unrelated.write_text("preserve\n", encoding="utf-8")
    second = install_agent(Agent.CLAUDE, environment)

    assert first.success is True
    assert first.changed is True
    assert second.success is True
    assert second.changed is False
    assert unrelated.read_text(encoding="utf-8") == "preserve\n"


def test_missing_bundled_assets_returns_structured_error(tmp_path: Path) -> None:
    empty_data = tmp_path / "empty-data"
    empty_data.mkdir()
    environment = _environment(tmp_path, data_root=empty_data)

    result = install_agent(Agent.CLAUDE, environment)

    assert result.success is False
    assert result.error_code == "missing_assets"
    assert "SKILL.md" in result.error
    assert not (environment.project_root / ".claude").exists()


def test_malformed_bundled_asset_types_are_rejected(tmp_path: Path) -> None:
    data = _agent_data(tmp_path)
    shutil_target = data / "commands"
    for item in sorted(
        shutil_target.rglob("*"),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if item.is_file():
            item.unlink()
        else:
            item.rmdir()
    shutil_target.rmdir()
    shutil_target.write_text("not a directory\n", encoding="utf-8")
    environment = _environment(tmp_path, data_root=data)

    result = install_agent(Agent.CLAUDE, environment)

    assert result.success is False
    assert result.error_code == "missing_assets"
    assert str(shutil_target) in result.error


def test_write_failure_returns_structured_error_without_exiting(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment.project_root.mkdir(parents=True)
    (environment.project_root / ".claude").write_text(
        "blocks directory\n",
        encoding="utf-8",
    )

    result = install_agent(Agent.CLAUDE, environment)

    assert result.success is False
    assert result.error_code == "write_failed"
    assert result.error


def test_candidate_detection_combines_project_home_and_executable_evidence(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path, commands={"gemini"})
    (environment.project_root / ".claude").mkdir(parents=True)
    (environment.project_root / ".cursor").mkdir()
    (environment.home / ".codex").mkdir(parents=True)

    candidates = detect_agent_candidates(environment)

    assert tuple(candidate.agent for candidate in candidates) == (
        Agent.CLAUDE,
        Agent.CURSOR,
        Agent.GEMINI,
        Agent.CODEX,
    )
    assert all(candidate.reasons for candidate in candidates)


def test_candidate_detection_reports_existing_verified_install(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    assert install_agent(Agent.WINDSURF, environment).success is True

    candidates = detect_agent_candidates(environment)

    candidate = next(item for item in candidates if item.agent is Agent.WINDSURF)
    assert candidate.installed is True


def test_declining_detected_agents_writes_nothing_and_completes_skip(
    tmp_path: Path,
) -> None:
    environment = _environment(tmp_path, input_fn=_inputs("n"), commands={"claude"})

    result = provision_agent_integration(environment)

    assert result.status is ProvisioningStatus.SKIPPED
    assert result.complete is True
    assert result.skipped is True
    assert not (environment.project_root / ".claude").exists()


def test_default_confirmation_installs_detected_candidates(tmp_path: Path) -> None:
    output: list[str] = []
    environment = _environment(
        tmp_path,
        input_fn=_inputs(""),
        output=output,
        commands={"cursor"},
    )

    result = provision_agent_integration(environment)

    assert result.status is ProvisioningStatus.COMPLETE
    assert result.complete is True
    assert result.results[0].agent is Agent.CURSOR
    assert result.results[0].verified is True
    assert (environment.project_root / ".cursor" / "skills" / "uidetox").is_dir()
    assert any("cursor" in line.lower() for line in output)


def test_no_candidate_requires_explicit_agent_or_skip(tmp_path: Path) -> None:
    environment = _environment(tmp_path, input_fn=_inputs("claude"))

    result = provision_agent_integration(environment)

    assert result.complete is True
    assert result.results[0].agent is Agent.CLAUDE


def test_noninteractive_agent_provisioning_never_writes(tmp_path: Path) -> None:
    environment = _environment(
        tmp_path,
        interactive=False,
        commands={"claude"},
    )

    result = provision_agent_integration(environment)

    assert result.status is ProvisioningStatus.INCOMPLETE
    assert not (environment.project_root / ".claude").exists()


def test_supported_names_are_single_source_for_command_compatibility() -> None:
    assert SUPPORTED_AGENT_NAMES == (
        "claude",
        "cursor",
        "gemini",
        "codex",
        "windsurf",
        "copilot",
    )


def test_update_skill_command_preserves_success_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    data = _agent_data(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(update_skill, "_get_data_dir", lambda: data)

    update_skill.run(argparse.Namespace(agent="claude"))

    output = capsys.readouterr().out
    assert "UIdetox → Claude" in output
    assert "Installing UIdetox skill files for Claude" in output
    assert "Claude Integration Guide" in output
    assert "✓ Done. Run `uidetox setup` then `uidetox scan` to begin." in output
    assert (project / ".claude" / "skills" / "uidetox" / "SKILL.md").is_file()


def test_update_skill_command_preserves_missing_bundle_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    data = tmp_path / "empty"
    data.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(update_skill, "_get_data_dir", lambda: data)

    with pytest.raises(SystemExit) as error:
        update_skill.run(argparse.Namespace(agent="claude"))

    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert "Bundled SKILL.md not found" in stderr
    assert "pip install --force-reinstall uidetox" in stderr


def test_onboarding_runs_agent_before_capabilities_and_records_skip(
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
                "next_step": "agent",
                "started_at": "2026-07-19T20:00:00+00:00",
                "updated_at": "2026-07-19T20:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    events: list[str] = []

    def provision_agent(
        _environment: AgentIntegrationEnvironment,
    ) -> AgentProvisioningResult:
        events.append("agent")
        return AgentProvisioningResult(
            status=ProvisioningStatus.SKIPPED,
            candidates=(),
            results=(),
        )

    def provision_capabilities(
        _environment: CapabilityEnvironment,
    ) -> CapabilityProvisioningResult:
        events.append("capabilities")
        return CapabilityProvisioningResult(
            complete=True,
            skipped=True,
            statuses=(),
            results=(),
        )

    monkeypatch.setattr(
        "uidetox.agent_integration.provision_agent_integration",
        provision_agent,
    )
    monkeypatch.setattr(
        "uidetox.capabilities.provision_capabilities",
        provision_capabilities,
    )

    handled = run_first_run(
        OnboardingEnvironment(
            state_path=state_path,
            interactive=True,
            input_fn=lambda _prompt: "n",
            output_fn=lambda _line: None,
            now_fn=lambda: "2026-07-19T21:00:00+00:00",
        )
    )

    assert handled is True
    assert events == ["agent", "capabilities"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_steps"] == ["intro", "agent", "capabilities"]
    assert state["next_step"] == "intent"
