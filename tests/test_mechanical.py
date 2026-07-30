from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from uidetox import mechanical
from uidetox.commands import check


def _configure_check(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    tooling: dict[str, dict[str, str] | None],
    *,
    auto_commit: bool = False,
) -> list[str]:
    diagnostic_calls: list[str] = []

    monkeypatch.setattr(check, "get_project_root", lambda: root)
    monkeypatch.setattr(
        check,
        "load_config",
        lambda: {"auto_commit": auto_commit, "tooling": tooling},
    )
    monkeypatch.setattr(check, "save_config", lambda config: None)

    for name, command_module in (
        ("typescript", check.tsc_cmd),
        ("linter", check.lint_cmd),
        ("formatter", check.format_cmd),
    ):
        monkeypatch.setattr(
            command_module,
            "run",
            lambda args, name=name: diagnostic_calls.append(name) or True,
        )

    return diagnostic_calls


def test_run_mechanical_command_preserves_success_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="stdout\n", stderr="stderr\n")

    monkeypatch.setattr(mechanical.subprocess, "run", fake_run)

    run = mechanical.run_mechanical_command("tool --flag", tmp_path)

    assert run == mechanical.MechanicalRun(0, "stdout\nstderr\n")
    assert calls == [
        (
            ["tool", "--flag"],
            {
                "capture_output": True,
                "text": True,
                "cwd": tmp_path,
                "timeout": 120,
                "env": None,
            },
        )
    ]


def test_run_mechanical_command_preserves_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        mechanical.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 7, stdout="partial\n", stderr="failure\n"
        ),
    )

    assert mechanical.run_mechanical_command("tool", tmp_path) == mechanical.MechanicalRun(
        7, "partial\nfailure\n"
    )


@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (FileNotFoundError(), "command_not_found"),
        (subprocess.TimeoutExpired(["tool"], 0.01), "timeout"),
    ],
)
def test_run_mechanical_command_maps_execution_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: BaseException,
    expected_error: str,
) -> None:
    def fail_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise failure

    monkeypatch.setattr(mechanical.subprocess, "run", fail_run)

    assert mechanical.run_mechanical_command(
        "tool", tmp_path, timeout=0.01
    ) == mechanical.MechanicalRun(-1, "", expected_error)


def test_run_mechanical_command_propagates_cwd_and_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mechanical.subprocess, "run", fake_run)

    mechanical.run_mechanical_command("UIDETOX_TEST_VALUE=ready tool", tmp_path)

    assert captured["argv"] == ["tool"]
    assert captured["cwd"] == tmp_path
    assert captured["timeout"] == 120
    assert isinstance(captured["env"], dict)
    assert captured["env"]["UIDETOX_TEST_VALUE"] == "ready"


def test_run_mechanical_command_terminates_real_child_before_one_second(
    tmp_path: Path,
) -> None:
    command = shlex.join(
        [sys.executable, "-c", "import time; time.sleep(2)"]
    )

    started = time.monotonic()
    run = mechanical.run_mechanical_command(command, tmp_path, timeout=0.05)
    elapsed = time.monotonic() - started

    assert run == mechanical.MechanicalRun(-1, "", "timeout")
    assert elapsed < 1


def test_check_fix_commands_use_shared_bounded_runner_until_converged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    diagnostic_calls = _configure_check(
        monkeypatch,
        tmp_path,
        {
            "typescript": None,
            "formatter": {"fix_cmd": "fmt --write ."},
            "linter": {"fix_cmd": "lint --fix"},
        },
    )
    outputs = {
        "fmt --write .": iter(("formatted 1 file", "")),
        "lint --fix": iter(("fixed 1 file", "")),
    }
    calls: list[tuple[str, Path]] = []

    def fake_mechanical_run(command: str, root: Path) -> mechanical.MechanicalRun:
        calls.append((command, root))
        return mechanical.MechanicalRun(0, next(outputs[command]))

    monkeypatch.setattr(check, "run_mechanical_command", fake_mechanical_run)

    check.run(argparse.Namespace(fix=True))

    assert calls == [
        ("fmt --write .", tmp_path),
        ("lint --fix", tmp_path),
        ("fmt --write .", tmp_path),
        ("lint --fix", tmp_path),
    ]
    assert diagnostic_calls == ["linter", "formatter"]


@pytest.mark.parametrize("error", ["timeout", "command_not_found"])
def test_check_terminal_fix_error_is_not_retried_but_diagnostics_continue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: str
) -> None:
    diagnostic_calls = _configure_check(
        monkeypatch,
        tmp_path,
        {
            "typescript": None,
            "formatter": {"fix_cmd": "fmt"},
            "linter": {"fix_cmd": "lint"},
        },
        auto_commit=True,
    )
    calls: list[str] = []
    lint_runs = iter(
        (
            mechanical.MechanicalRun(0, "fixed 1 file"),
            mechanical.MechanicalRun(0, ""),
        )
    )

    def fake_mechanical_run(command: str, root: Path) -> mechanical.MechanicalRun:
        calls.append(command)
        if command == "fmt":
            return mechanical.MechanicalRun(-1, "", error)
        return next(lint_runs)

    auto_commit_calls: list[set[str]] = []
    monkeypatch.setattr(check, "run_mechanical_command", fake_mechanical_run)
    monkeypatch.setattr(check, "_tracked_changed_files", lambda: set())
    monkeypatch.setattr(
        check,
        "_auto_commit_changed_files",
        lambda files, message: auto_commit_calls.append(files),
    )

    with pytest.raises(RuntimeError, match="^Mechanical checks failed\\.$"):
        check.run(argparse.Namespace(fix=True))

    assert calls == ["fmt", "lint", "lint"]
    assert diagnostic_calls == ["linter", "formatter"]
    assert auto_commit_calls == []


def test_check_nonzero_fix_result_fails_and_prevents_auto_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_check(
        monkeypatch,
        tmp_path,
        {
            "typescript": None,
            "formatter": {"fix_cmd": "fmt"},
            "linter": None,
        },
        auto_commit=True,
    )
    calls: list[str] = []

    def fake_mechanical_run(command: str, root: Path) -> mechanical.MechanicalRun:
        calls.append(command)
        return mechanical.MechanicalRun(2, "formatter failed")

    auto_commit_calls: list[set[str]] = []
    tracked_calls = 0

    def tracked_changes() -> set[str]:
        nonlocal tracked_calls
        tracked_calls += 1
        return set() if tracked_calls == 1 else {"src/App.tsx"}

    monkeypatch.setattr(check, "run_mechanical_command", fake_mechanical_run)
    monkeypatch.setattr(check, "_tracked_changed_files", tracked_changes)
    monkeypatch.setattr(
        check,
        "_auto_commit_changed_files",
        lambda files, message: auto_commit_calls.append(files),
    )

    with pytest.raises(RuntimeError, match="^Mechanical checks failed\\.$"):
        check.run(argparse.Namespace(fix=True))

    assert calls == ["fmt"]
    assert auto_commit_calls == []


def test_check_caps_successful_changed_fix_iterations_at_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_check(
        monkeypatch,
        tmp_path,
        {
            "typescript": None,
            "formatter": {"fix_cmd": "fmt"},
            "linter": None,
        },
    )
    calls: list[str] = []

    def fake_mechanical_run(command: str, root: Path) -> mechanical.MechanicalRun:
        calls.append(command)
        return mechanical.MechanicalRun(0, "formatted 1 file")

    monkeypatch.setattr(check, "run_mechanical_command", fake_mechanical_run)

    check.run(argparse.Namespace(fix=True))

    assert calls == ["fmt", "fmt", "fmt"]
