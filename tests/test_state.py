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