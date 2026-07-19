from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from uidetox.capabilities import (
    CODEBASE_MEMORY_DOCS_URL,
    Capability,
    CapabilityEnvironment,
    CapabilityProvisioningResult,
    CommandExecution,
    InstallMethod,
    InvocationKind,
    ProbeState,
    SetupOutcome,
    build_setup_plan,
    capture_install_guidance,
    detect_capabilities,
    detect_invocation_kind,
    execute_setup_plan,
    provision_capabilities,
    visual_install_guidance,
)
from uidetox.onboarding import OnboardingEnvironment, run_first_run


def _inputs(*answers: str) -> Callable[[str], str]:
    remaining = iter(answers)
    return lambda _prompt: next(remaining)


def _environment(
    *,
    distributions: set[str] | None = None,
    imports: set[str] | None = None,
    chromium: ProbeState = ProbeState.UNKNOWN,
    executables: set[str] | None = None,
    input_fn: Callable[[str], str] | None = None,
    output: list[str] | None = None,
    runner: Callable[[tuple[str, ...], int], CommandExecution] | None = None,
    interactive: bool = True,
    python_executable: str = "/venv/bin/python",
    prefix: str = "/venv",
    environ: dict[str, str] | None = None,
    mcp: ProbeState = ProbeState.UNKNOWN,
) -> CapabilityEnvironment:
    distributions = distributions or set()
    imports = imports or set()
    executables = executables or set()
    output = output if output is not None else []

    def distribution_version(name: str) -> str:
        if name not in distributions:
            raise PackageNotFoundError(name)
        return "1.0"

    def find_spec(name: str) -> object | None:
        return object() if name in imports else None

    def which(name: str) -> str | None:
        return f"/tools/{name}" if name in executables else None

    return CapabilityEnvironment(
        interactive=interactive,
        input_fn=input_fn or _inputs("n"),
        output_fn=output.append,
        python_executable=python_executable,
        prefix=prefix,
        environ=environ or {},
        distribution_version=distribution_version,
        find_spec=find_spec,
        which=which,
        chromium_probe=lambda: chromium,
        runner=runner
        or (
            lambda argv, _timeout: CommandExecution(
                argv=argv,
                returncode=0,
                stdout="",
                stderr="",
            )
        ),
        mcp_probe=lambda _executable: mcp,
    )


def _status_map(environment: CapabilityEnvironment):
    return {status.capability: status for status in detect_capabilities(environment)}


def test_detection_distinguishes_pillow_distribution_from_pil_import() -> None:
    statuses = _status_map(_environment(distributions={"Pillow"}, imports=set()))

    assert statuses[Capability.PILLOW].distribution is ProbeState.AVAILABLE
    assert statuses[Capability.PILLOW].importable is ProbeState.MISSING
    assert statuses[Capability.PILLOW].ready is False


def test_detection_distinguishes_playwright_package_from_missing_browser() -> None:
    statuses = _status_map(
        _environment(
            distributions={"playwright"},
            imports={"playwright"},
            chromium=ProbeState.MISSING,
        )
    )

    assert statuses[Capability.PLAYWRIGHT].ready is True
    assert statuses[Capability.CHROMIUM].runtime is ProbeState.MISSING
    assert statuses[Capability.CHROMIUM].ready is False


def test_codebase_memory_unavailable_is_external_and_mcp_state_is_unknown() -> None:
    status = _status_map(_environment())[Capability.CODEBASE_MEMORY]

    assert status.command is ProbeState.MISSING
    assert status.mcp is ProbeState.UNKNOWN
    assert status.distribution is ProbeState.NOT_APPLICABLE
    assert CODEBASE_MEMORY_DOCS_URL in status.detail


def test_codebase_memory_command_does_not_guess_unverifiable_mcp_readiness() -> None:
    status = _status_map(
        _environment(
            executables={"codebase-memory-mcp"},
            mcp=ProbeState.UNKNOWN,
        )
    )[Capability.CODEBASE_MEMORY]

    assert status.command is ProbeState.AVAILABLE
    assert status.mcp is ProbeState.UNKNOWN
    assert status.ready is False


def test_detect_invocation_kind_covers_pip_uv_tool_and_uvx() -> None:
    assert detect_invocation_kind("/venv", {}) is InvocationKind.ACTIVE_PYTHON
    assert (
        detect_invocation_kind(
            "/Users/me/.local/share/uv/tools/uidetox",
            {"UV_TOOL_DIR": "/Users/me/.local/share/uv/tools"},
        )
        is InvocationKind.UV_TOOL
    )
    assert (
        detect_invocation_kind(
            "/Users/me/.cache/uv/archive-v0/abc",
            {"UV_CACHE_DIR": "/Users/me/.cache/uv"},
        )
        is InvocationKind.UVX
    )
    assert (
        detect_invocation_kind(
            r"C:\Users\me\AppData\Local\uv\cache\archive-v0\abc",
            {},
        )
        is InvocationKind.UVX
    )


def test_uv_plan_uses_durable_tool_install_and_separate_chromium_step() -> None:
    environment = _environment(executables={"uv"})

    plan = build_setup_plan(
        (Capability.PILLOW, Capability.PLAYWRIGHT, Capability.CHROMIUM),
        InstallMethod.UV,
        environment,
    )

    assert plan[0].capabilities == (Capability.PILLOW, Capability.PLAYWRIGHT)
    assert plan[0].argv == (
        "/tools/uv",
        "tool",
        "install",
        "uidetox[capture]",
    )
    assert plan[1].capabilities == (Capability.CHROMIUM,)
    assert plan[1].argv == (
        "/tools/uv",
        "tool",
        "run",
        "--from",
        "playwright",
        "playwright",
        "install",
        "chromium",
    )


def test_pip_plan_targets_active_interpreter_and_keeps_browser_separate() -> None:
    environment = _environment(python_executable="/chosen/python")

    plan = build_setup_plan(
        (Capability.PILLOW, Capability.CHROMIUM),
        InstallMethod.PIP,
        environment,
    )

    assert plan[0].argv == (
        "/chosen/python",
        "-m",
        "pip",
        "install",
        "uidetox[visual]",
    )
    assert plan[1].argv == (
        "/chosen/python",
        "-m",
        "playwright",
        "install",
        "chromium",
    )


def test_uvx_refuses_pip_mutation_and_uv_plan_remains_durable() -> None:
    environment = _environment(
        executables={"uv"},
        prefix="/cache/uv/archive-v0/run",
        environ={"UV_CACHE_DIR": "/cache/uv"},
    )

    with pytest.raises(ValueError, match="disposable uvx"):
        build_setup_plan((Capability.PILLOW,), InstallMethod.PIP, environment)

    plan = build_setup_plan(
        (Capability.PILLOW,),
        InstallMethod.UV,
        environment,
    )
    assert plan[0].argv[:3] == ("/tools/uv", "tool", "install")

    windows_uvx = _environment(
        prefix=r"C:\Users\me\AppData\Local\uv\cache\archive-v0\run",
    )
    with pytest.raises(ValueError, match="disposable uvx"):
        build_setup_plan((Capability.PILLOW,), InstallMethod.PIP, windows_uvx)


def test_missing_uv_executable_becomes_structured_failure() -> None:
    action = build_setup_plan(
        (Capability.PILLOW,),
        InstallMethod.UV,
        _environment(executables={"uv"}),
    )[0]
    environment = _environment(executables=set())

    result = execute_setup_plan((action,), environment)

    assert result[0].outcome is SetupOutcome.FAILED
    assert "executable" in result[0].message.lower()


def test_failed_subprocess_is_structured_and_output_is_bounded() -> None:
    huge = "x" * 10_000

    def fail(argv: tuple[str, ...], _timeout: int) -> CommandExecution:
        return CommandExecution(argv=argv, returncode=7, stdout=huge, stderr=huge)

    environment = _environment(executables={"uv"}, runner=fail)
    action = build_setup_plan(
        (Capability.PILLOW,),
        InstallMethod.UV,
        environment,
    )[0]

    result = execute_setup_plan((action,), environment, output_limit=128)

    assert result[0].outcome is SetupOutcome.FAILED
    assert result[0].returncode == 7
    assert len(result[0].stdout) <= 160
    assert len(result[0].stderr) <= 160
    assert "truncated" in result[0].stdout


def test_shell_metacharacters_remain_one_inert_argv_item() -> None:
    executable = "/tmp/python; touch /tmp/uidetox-pwned"
    environment = _environment(python_executable=executable)

    plan = build_setup_plan(
        (Capability.PILLOW,),
        InstallMethod.PIP,
        environment,
    )

    assert plan[0].argv[0] == executable
    assert len(plan[0].argv) == 5


def test_declining_all_capabilities_runs_nothing_and_completes_skip() -> None:
    calls: list[tuple[str, ...]] = []
    prompts: list[str] = []

    def input_fn(prompt: str) -> str:
        prompts.append(prompt)
        return "n"

    environment = _environment(
        input_fn=input_fn,
        runner=lambda argv, _timeout: (
            calls.append(argv)
            or CommandExecution(argv=argv, returncode=0, stdout="", stderr="")
        ),
    )

    result = provision_capabilities(environment)

    assert result.complete is True
    assert result.skipped is True
    assert calls == []
    assert prompts and "optional" in prompts[0].lower()


def test_noninteractive_provisioning_never_installs() -> None:
    calls: list[tuple[str, ...]] = []
    result = provision_capabilities(
        _environment(
            interactive=False,
            runner=lambda argv, _timeout: (
                calls.append(argv)
                or CommandExecution(argv=argv, returncode=0, stdout="", stderr="")
            ),
        )
    )

    assert result.complete is False
    assert result.skipped is False
    assert calls == []


def test_custom_selection_declines_unselected_capabilities() -> None:
    installed: set[str] = set()
    calls: list[tuple[str, ...]] = []

    def distribution_version(name: str) -> str:
        if name not in installed:
            raise PackageNotFoundError(name)
        return "1.0"

    def runner(argv: tuple[str, ...], _timeout: int) -> CommandExecution:
        calls.append(argv)
        installed.update({"Pillow", "PIL"})
        return CommandExecution(argv=argv, returncode=0, stdout="", stderr="")

    environment = _environment(
        input_fn=_inputs("custom", "pillow", "pip"),
        runner=runner,
    )
    environment = replace(
        environment,
        distribution_version=distribution_version,
        find_spec=lambda name: object() if name in installed else None,
    )

    result = provision_capabilities(environment)

    assert result.complete is True
    assert len(calls) == 1
    assert calls[0][-1] == "uidetox[visual]"
    assert all("playwright" not in item for item in calls[0])


def test_default_interactive_selection_installs_all_missing_and_verifies() -> None:
    calls: list[tuple[str, ...]] = []
    output: list[str] = []

    def runner(argv: tuple[str, ...], _timeout: int) -> CommandExecution:
        calls.append(argv)
        return CommandExecution(argv=argv, returncode=0, stdout="ok", stderr="")

    environment = _environment(
        input_fn=_inputs("", ""),
        output=output,
        executables={"uv", "codebase-memory-mcp"},
        mcp=ProbeState.AVAILABLE,
        runner=runner,
    )

    result = provision_capabilities(environment)

    assert result.complete is True
    assert result.skipped is False
    assert calls[0][:3] == ("/tools/uv", "tool", "install")
    assert calls[1][-3:] == ("playwright", "install", "chromium")
    assert all(item.outcome is SetupOutcome.VERIFIED for item in result.results)
    assert all(
        status.ready is False
        for status in result.statuses
        if status.capability
        in {Capability.PILLOW, Capability.PLAYWRIGHT, Capability.CHROMIUM}
    )
    assert all("re-run" in item.message.lower() for item in result.results)
    assert any("optional" in line.lower() for line in output)
    assert any("re-run" in line.lower() for line in output)


def test_external_codebase_memory_plan_is_guidance_when_binary_is_missing() -> None:
    action = build_setup_plan(
        (Capability.CODEBASE_MEMORY,),
        InstallMethod.PIP,
        _environment(),
    )[0]

    assert action.argv is None
    assert action.guidance is not None
    assert CODEBASE_MEMORY_DOCS_URL in action.guidance
    assert "uidetox[" not in action.guidance


def test_external_codebase_memory_installer_is_never_run_inside_agent_session() -> None:
    action = build_setup_plan(
        (Capability.CODEBASE_MEMORY,),
        InstallMethod.UV,
        _environment(executables={"codebase-memory-mcp", "uv"}),
    )[0]

    assert action.argv is None
    assert action.guidance is not None
    assert "outside this active agent session" in action.guidance
    assert CODEBASE_MEMORY_DOCS_URL in action.guidance


def test_install_guidance_is_centralized_for_capture_and_visual_paths() -> None:
    assert "pip install 'uidetox[capture]'" in capture_install_guidance()
    assert "python -m playwright install chromium" in capture_install_guidance()
    assert "pip install 'uidetox[visual]'" in visual_install_guidance()


def test_onboarding_completes_capability_step_after_agent_step(
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
                "completed_steps": ["intro", "agent"],
                "next_step": "capabilities",
                "started_at": "2026-07-19T20:00:00+00:00",
                "updated_at": "2026-07-19T20:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    calls: list[CapabilityEnvironment] = []

    def provision(environment: CapabilityEnvironment) -> CapabilityProvisioningResult:
        calls.append(environment)
        return CapabilityProvisioningResult(
            complete=True,
            skipped=True,
            statuses=(),
            results=(),
        )

    monkeypatch.setattr("uidetox.capabilities.provision_capabilities", provision)
    output: list[str] = []

    handled = run_first_run(
        OnboardingEnvironment(
            state_path=state_path,
            interactive=True,
            input_fn=lambda _prompt: "n",
            output_fn=output.append,
            now_fn=lambda: "2026-07-19T21:00:00+00:00",
        )
    )

    assert handled is True
    assert len(calls) == 1
    assert calls[0].input_fn("prompt") == "n"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["completed_steps"] == ["intro", "agent", "capabilities"]
    assert state["next_step"] == "intent"
