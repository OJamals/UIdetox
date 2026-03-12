from pathlib import Path

import pytest

from uidetox import state as state_module
from uidetox.state import add_issue, batch_add_issues, ensure_uidetox_dir, load_state


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None


def test_add_issue_deduplicates_pending_issue_and_upgrades_tier():
    first = {
        "id": "SCAN-ONE",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Generic AI Typography detected.",
        "command": "Swap the font family.",
    }
    second = {
        "id": "SCAN-TWO",
        "file": "src/App.tsx",
        "tier": "T1",
        "issue": "Generic AI Typography detected.",
        "command": "Swap the font family and tighten hierarchy.",
    }

    assert add_issue(first) == "added"
    assert add_issue(second) == "updated"

    state = load_state()
    assert len(state["issues"]) == 1
    assert state["issues"][0]["tier"] == "T1"
    assert state["issues"][0]["command"] == "Swap the font family and tighten hierarchy."
    assert state["stats"]["total_found"] == 1


def test_batch_add_issues_deduplicates_existing_and_incoming_duplicates():
    summary = batch_add_issues(
        [
            {
                "id": "SCAN-ONE",
                "file": "src/App.tsx",
                "tier": "T2",
                "issue": "Purple-blue gradient detected.",
                "command": "Replace the gradient.",
            },
            {
                "id": "SCAN-TWO",
                "file": "src/App.tsx",
                "tier": "T1",
                "issue": "Purple-blue gradient detected.",
                "command": "Replace the gradient with a single accent.",
            },
            {
                "id": "SCAN-THREE",
                "file": "src/Button.tsx",
                "tier": "T1",
                "issue": "Missing focus state.",
                "command": "Add focus styles.",
            },
        ]
    )

    assert summary == {"added": 2, "updated": 1, "skipped": 0}

    state = load_state()
    assert len(state["issues"]) == 2
    issues_by_file = {issue["file"]: issue for issue in state["issues"]}
    assert issues_by_file["src/App.tsx"]["tier"] == "T1"
    assert state["stats"]["total_found"] == 2


# ── Phase-scoped deduplication tests ─────────────────────────────


def test_phase_scoped_dedupe_same_phase_deduplicates():
    """Within the same phase, identical issues are still deduplicated."""
    issue_a = {
        "id": "PHASE-A",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Missing dark mode support.",
        "command": "Add dark mode.",
    }
    issue_b = {
        "id": "PHASE-B",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Missing dark mode support.",
        "command": "Add dark mode.",
    }
    assert add_issue(issue_a, phase="check") == "added"
    assert add_issue(issue_b, phase="check") == "skipped"
    state = load_state()
    assert len(state["issues"]) == 1


def test_phase_scoped_dedupe_different_phases_separate():
    """The same issue in different phases is treated as distinct."""
    issue_check = {
        "id": "PH-CHECK",
        "file": "src/App.tsx",
        "tier": "T3",
        "issue": "Unused CSS class detected.",
        "command": "Remove unused class.",
    }
    issue_scan = {
        "id": "PH-SCAN",
        "file": "src/App.tsx",
        "tier": "T3",
        "issue": "Unused CSS class detected.",
        "command": "Remove unused class.",
    }
    assert add_issue(issue_check, phase="check") == "added"
    assert add_issue(issue_scan, phase="scan") == "added"
    state = load_state()
    assert len(state["issues"]) == 2


def test_batch_phase_scoped_dedupe():
    """batch_add_issues with a phase tag deduplicates within that phase."""
    issues_list = [
        {
            "id": "BATCH-1",
            "file": "src/Nav.tsx",
            "tier": "T2",
            "issue": "Generic copy detected.",
            "command": "Refine copy.",
        },
        {
            "id": "BATCH-2",
            "file": "src/Nav.tsx",
            "tier": "T1",
            "issue": "Generic copy detected.",
            "command": "Refine copy intensively.",
        },
    ]
    result = batch_add_issues(issues_list, phase="lint")
    assert result["added"] == 1
    assert result["updated"] == 1

    state = load_state()
    assert len(state["issues"]) == 1
    assert state["issues"][0]["tier"] == "T1"  # upgraded


def test_global_dedupe_backward_compatible():
    """Without phase, dedup is global (backward-compatible behavior)."""
    issue_a = {
        "id": "GLOB-A",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Shadow slop detected.",
        "command": "Reduce shadow.",
    }
    issue_b = {
        "id": "GLOB-B",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Shadow slop detected.",
        "command": "Reduce shadow.",
    }
    assert add_issue(issue_a) == "added"
    assert add_issue(issue_b) == "skipped"
    state = load_state()
    assert len(state["issues"]) == 1