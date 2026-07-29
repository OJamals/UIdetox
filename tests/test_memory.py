"""Behavior tests for dependency-free persistent project memory."""

from __future__ import annotations

import multiprocessing
import os

from uidetox.memory import (
    add_note,
    add_pattern,
    get_fix_history,
    get_last_scan,
    get_notes,
    get_patterns,
    get_progress_log,
    get_reviewed_files,
    get_session,
    load_memory,
    log_progress,
    mark_file_reviewed,
    record_fix_outcome,
    save_scan_summary,
    save_session,
)
from uidetox.subagent import _build_memory_block


def _mutate_memory_concurrently(
    project_dir: str,
    barrier,
    action: str,
    rounds: int,
) -> None:
    os.chdir(project_dir)
    for round_index in range(rounds):
        barrier.wait(timeout=15)
        if action == "review":
            mark_file_reviewed(f"src/{round_index}.tsx", verdict="clean")
        elif action.startswith("pattern-"):
            add_pattern(f"{action}-{round_index}")
        elif action == "note":
            add_note(f"note-{round_index}")
        elif action == "fix":
            record_fix_outcome(
                f"src/{round_index}.tsx",
                f"issue-{round_index}",
                f"fix-{round_index}",
            )
        elif action == "session":
            save_session(
                phase=f"phase-{round_index}",
                last_command=f"command-{round_index}",
                issues_fixed=1,
            )
        elif action == "scan":
            save_scan_summary(
                total_found=round_index,
                by_tier={},
                by_category={},
                files_scanned=round_index,
                top_files=[],
            )
        elif action == "progress":
            log_progress(f"action-{round_index}")


def test_concurrent_memory_mutators_preserve_all_updates(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    context = multiprocessing.get_context("spawn")
    pattern_writers = tuple(f"pattern-{index}" for index in range(4))
    actions = (
        "review",
        *pattern_writers,
        "note",
        "fix",
        "session",
        "scan",
        "progress",
    )
    rounds = 3
    barrier = context.Barrier(len(actions))
    processes = [
        context.Process(
            target=_mutate_memory_concurrently,
            args=(str(tmp_path), barrier, action, rounds),
        )
        for action in actions
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
    assert [process.exitcode for process in processes] == [0] * len(actions)

    observed = {
        "reviewed": sorted(get_reviewed_files()),
        "patterns": sorted(entry["pattern"] for entry in get_patterns(limit=50)),
        "notes": sorted(entry["note"] for entry in get_notes(limit=rounds)),
        "fixes": sorted(entry["fix"] for entry in get_fix_history(limit=rounds)),
        "session_fixes": get_session()["issues_fixed_this_session"],
        "scan_total": get_last_scan()["total_found"],
        "progress": sorted(entry["action"] for entry in get_progress_log()),
    }
    assert observed == {
        "reviewed": [f"src/{index}.tsx" for index in range(rounds)],
        "patterns": sorted(
            f"{writer}-{round_index}"
            for writer in pattern_writers
            for round_index in range(rounds)
        ),
        "notes": [f"note-{index}" for index in range(rounds)],
        "fixes": [f"fix-{index}" for index in range(rounds)],
        "session_fixes": rounds,
        "scan_total": rounds - 1,
        "progress": [f"action-{index}" for index in range(rounds)],
    }


def test_queries_filter_json_patterns_and_notes_by_relevance(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    add_pattern("Preserve the card layout hierarchy", category="layout")
    add_pattern("Use strict API response types", category="architecture")
    add_note("Card actions stay beside the card title")
    add_note("Database migrations require rollback steps")

    patterns = get_patterns(query="card layout", limit=5)
    notes = get_notes(query="card actions", limit=5)

    assert [entry["pattern"] for entry in patterns] == [
        "Preserve the card layout hierarchy"
    ]
    assert [entry["note"] for entry in notes] == [
        "Card actions stay beside the card title"
    ]


def test_fix_outcomes_persist_and_filter_by_file_and_issue(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    record_fix_outcome(
        file_path="src/Card.tsx",
        issue="Card hierarchy is flat",
        fix="Grouped metadata beneath the title",
    )
    record_fix_outcome(
        file_path="src/api/client.ts",
        issue="Response type is implicit",
        fix="Added an explicit response contract",
    )

    matches = get_fix_history(query="Card hierarchy", limit=5)

    assert len(matches) == 1
    assert matches[0]["file"] == "src/Card.tsx"
    assert load_memory()["fix_history"] == [
        {
            "file": "src/Card.tsx",
            "issue": "Card hierarchy is flat",
            "fix": "Grouped metadata beneath the title",
            "outcome": "resolved",
            "recorded_at": matches[0]["recorded_at"],
        },
        {
            "file": "src/api/client.ts",
            "issue": "Response type is implicit",
            "fix": "Added an explicit response contract",
            "outcome": "resolved",
            "recorded_at": load_memory()["fix_history"][1]["recorded_at"],
        },
    ]


def test_memory_block_targets_json_memory_with_issue_and_file_terms(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    add_pattern("Preserve the Card component hierarchy", category="layout")
    add_pattern("Use strict API response types", category="architecture")
    add_note("Card actions stay beside the title")
    add_note("Database migrations require rollback steps")
    record_fix_outcome(
        file_path="src/Card.tsx",
        issue="Card hierarchy is flat",
        fix="Grouped metadata beneath the title",
    )

    block = _build_memory_block(
        query="repair card hierarchy",
        files=["src/Card.tsx"],
    )

    assert "Preserve the Card component hierarchy" in block
    assert "Card actions stay beside the title" in block
    assert "Grouped metadata beneath the title" in block
    assert "Use strict API response types" not in block
    assert "Database migrations require rollback steps" not in block
