"""Behavior tests for dependency-free persistent project memory."""

from __future__ import annotations

from uidetox.memory import (
    add_note,
    add_pattern,
    get_fix_history,
    get_notes,
    get_patterns,
    load_memory,
    record_fix_outcome,
)
from uidetox.subagent import _build_memory_block


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
