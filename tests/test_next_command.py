from argparse import Namespace

import pytest

from uidetox.commands import next as next_command


def _disable_optional_context(monkeypatch):
    import uidetox.subagent as subagent

    monkeypatch.setattr(next_command, "_get_relevant_context", lambda batch: [])
    monkeypatch.setattr(next_command, "_get_skill_path", lambda: None)
    monkeypatch.setattr(subagent, "_build_memory_block", lambda **kwargs: "")


def test_run_batches_highest_priority_directory(monkeypatch, capsys):
    issues = [
        {
            "id": f"CARD-{index}",
            "tier": "T1",
            "file": f"src/card/file-{index}.tsx",
            "issue": f"Card issue {index}",
            "command": "polish",
        }
        for index in range(16)
    ]
    issues.insert(
        0,
        {
            "id": "OTHER-1",
            "tier": "T2",
            "file": "src/other/file.tsx",
            "issue": "Other issue",
        },
    )
    monkeypatch.setattr(next_command, "load_state", lambda: {"issues": issues, "resolved": [1, 2]})
    monkeypatch.setattr(next_command, "load_config", lambda: {})
    _disable_optional_context(monkeypatch)

    next_command.run(Namespace())
    output = capsys.readouterr().out

    assert "Next Component: card (15 file(s))" in output
    assert "Directory: src/card" in output
    assert "Batching 15 issue(s)" in output
    assert "CARD-0" in output
    assert "CARD-14" in output
    assert "CARD-15" not in output
    assert "OTHER-1" not in output
    assert "Queue : 2 remaining after this batch" in output
    assert "16xT1, 1xT2, 0xT3, 0xT4 | 2 resolved so far" in output


def test_run_renders_design_dials_and_auto_commit(monkeypatch, capsys):
    monkeypatch.setattr(
        next_command,
        "load_state",
        lambda: {
            "issues": [
                {
                    "id": "UI-1",
                    "tier": "T3",
                    "file": "App.tsx",
                    "issue": "Layout issue",
                }
            ],
            "resolved": [],
        },
    )
    monkeypatch.setattr(
        next_command,
        "load_config",
        lambda: {
            "DESIGN_VARIANCE": 2,
            "MOTION_INTENSITY": 8,
            "VISUAL_DENSITY": 6,
            "auto_commit": True,
        },
    )
    _disable_optional_context(monkeypatch)

    next_command.run(Namespace())
    output = capsys.readouterr().out

    assert "DESIGN_VARIANCE  = 2" in output
    assert "(clean, centered, standard grids)" in output
    assert "MOTION_INTENSITY = 8" in output
    assert "(scroll-triggered, spring physics, magnetic effects)" in output
    assert "VISUAL_DENSITY   = 6" in output
    assert "(standard web app spacing)" in output
    assert "uidetox batch-resolve UI-1" in output
    assert "AUTO-COMMIT is ON" in output


def test_run_empty_queue_signals_rescan(monkeypatch, capsys):
    monkeypatch.setattr(next_command, "load_state", lambda: {"issues": []})
    monkeypatch.setattr(next_command, "load_config", lambda: {})

    with pytest.raises(SystemExit) as error:
        next_command.run(Namespace())

    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "Queue is empty. No pending issues." in output
    assert "[AGENT LOOP SIGNAL]" in output
    assert "uidetox rescan" in output
