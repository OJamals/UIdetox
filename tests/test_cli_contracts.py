from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from uidetox import cli
from uidetox.commands import format_cmd, lint, loop, subagent_cmd, tsc


def _dispatch_result(monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    module = SimpleNamespace(run=lambda _args: result)
    monkeypatch.setattr(cli, "import_module", lambda _name: module)
    monkeypatch.setattr(cli, "_iter_dynamic_skill_names", lambda: [])
    monkeypatch.setattr(cli.sys, "argv", ["uidetox", "detect"])
    cli.main()


@pytest.mark.parametrize("result", [None, True])
def test_cli_main_accepts_success_results(
    monkeypatch: pytest.MonkeyPatch,
    result: object,
) -> None:
    _dispatch_result(monkeypatch, result)


def test_cli_main_maps_false_to_exit_one(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as captured:
        _dispatch_result(monkeypatch, False)

    assert captured.value.code == 1


def test_cli_main_propagates_nonzero_integer_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit) as captured:
        _dispatch_result(monkeypatch, 7)

    assert captured.value.code == 7


def test_cli_main_rejects_unsupported_command_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as captured:
        _dispatch_result(monkeypatch, object())

    assert captured.value.code == 1
    assert "unsupported result type" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "module"),
    [
        ("tsc", tsc),
        ("lint", lint),
        ("format", format_cmd),
    ],
)
@pytest.mark.parametrize(("result", "expected_exit"), [(True, None), (False, 1)])
def test_mechanical_command_results_reach_process_exit(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    module: object,
    result: bool,
    expected_exit: int | None,
) -> None:
    monkeypatch.setattr(module, "run", lambda _args: result)
    monkeypatch.setattr(cli.sys, "argv", ["uidetox", command])

    if expected_exit is None:
        cli.main()
        return

    with pytest.raises(SystemExit) as captured:
        cli.main()
    assert captured.value.code == expected_exit


def test_missing_subagent_show_exits_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subagent_cmd, "get_session", lambda _session_id: None)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["uidetox", "subagent", "--show", "missing"],
    )

    with pytest.raises(SystemExit) as captured:
        cli.main()

    assert captured.value.code == 1


def test_missing_subagent_record_exits_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subagent_cmd,
        "record_result",
        lambda _session_id, _result: False,
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["uidetox", "subagent", "--record", "missing"],
    )

    with pytest.raises(SystemExit) as captured:
        cli.main()

    assert captured.value.code == 1


@pytest.mark.parametrize(
    "args",
    [
        ["tsc", "--fix"],
        ["review", "--score", "95"],
    ],
)
def test_removed_options_are_rejected_by_argparse(args: list[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        cli.parse_args(args)

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "args",
    [
        ["loop", "--execute", "--orchestrator"],
        ["loop", "--proposal-id", "proposal-1"],
        ["loop", "--proposal-id", ""],
        ["loop", "--require-visual-evidence"],
        ["loop", "--visual-evidence-file", "evidence.json"],
        ["loop", "--visual-evidence-file", ""],
    ],
)
def test_impossible_loop_modes_exit_two_before_state_writes(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    def forbid_state_write() -> None:
        raise AssertionError("loop validation must precede state writes")

    monkeypatch.setattr(loop, "ensure_uidetox_dir", forbid_state_write)
    monkeypatch.setattr(cli.sys, "argv", ["uidetox", *args])

    with pytest.raises(SystemExit) as captured:
        cli.main()

    assert captured.value.code == 2


def test_all_registered_commands_support_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_parser: list[argparse.ArgumentParser] = []
    original_parse_args = argparse.ArgumentParser.parse_args

    def capture_parser(
        parser: argparse.ArgumentParser,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        captured_parser[:] = [parser]
        return original_parse_args(parser, args, namespace)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", capture_parser)
    cli.parse_args(["detect"])
    parser = captured_parser[0]
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    for command in subparsers.choices:
        with pytest.raises(SystemExit) as captured:
            cli.parse_args([command, "--help"])
        assert captured.value.code == 0, command
