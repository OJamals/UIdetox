from uidetox.state import (
    add_issue,
    add_issues,
    load_config,
    load_state,
    save_config,
    save_state,
)


def test_save_config_round_trip_is_atomic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    save_config({"DESIGN_VARIANCE": 3, "custom": {"enabled": True}})

    config = load_config()
    assert config["DESIGN_VARIANCE"] == 3
    assert config["custom"] == {"enabled": True}
    assert list((tmp_path / ".uidetox").glob("config_*.tmp")) == []


def test_save_state_round_trip_is_atomic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = {
        "last_scan": None,
        "issues": [],
        "resolved": [],
        "diff_baseline": [],
        "subjective": {},
        "stats": {"total_found": 1, "total_resolved": 0, "scans_run": 1},
    }

    save_state(state)

    loaded = load_state()
    assert loaded["issues"] == state["issues"]
    assert loaded["resolved"] == state["resolved"]
    assert loaded["diff_baseline"] == state["diff_baseline"]
    assert loaded["stats"] == state["stats"]
    assert loaded["subjective"] == {"history": []}
    assert list((tmp_path / ".uidetox").glob("state_*.tmp")) == []


def _issue(name: str) -> dict:
    return {
        "id": f"SCAN-{name}",
        "file": f"src/{name}.tsx",
        "tier": "T2",
        "issue": f"Issue {name}",
        "command": f"Fix {name}",
    }


def test_add_issues_empty_batch_does_not_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert add_issues([]) == 0
    assert not (tmp_path / ".uidetox" / "state.json").exists()


def test_add_issues_accepts_unique_items_in_input_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    issues = [_issue("first"), _issue("second")]

    assert add_issues(issues) == 2

    state = load_state()
    assert [issue["id"] for issue in state["issues"]] == ["SCAN-first", "SCAN-second"]
    assert state["stats"]["total_found"] == 2
    assert all(issue.get("created_at") for issue in issues)


def test_add_issues_discards_existing_and_intra_batch_duplicates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existing = _issue("existing")
    assert add_issue(existing) is True

    existing_duplicate = _issue("existing")
    new_issue = _issue("new")
    batch_duplicate = _issue("new")

    assert add_issues([existing_duplicate, new_issue, batch_duplicate]) == 1

    state = load_state()
    assert [issue["id"] for issue in state["issues"]] == ["SCAN-existing", "SCAN-new"]
    assert state["stats"]["total_found"] == 2
    assert "created_at" not in existing_duplicate
    assert new_issue.get("created_at")
    assert "created_at" not in batch_duplicate


def test_add_issue_wrapper_preserves_return_and_timestamp_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    issue = _issue("wrapper")
    duplicate = _issue("wrapper")

    assert add_issue(issue) is True
    assert issue.get("created_at")
    assert add_issue(duplicate) is False
    assert "created_at" not in duplicate


def test_add_issues_handles_malformed_normalized_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_state({"issues": "bad", "stats": "bad"})

    assert add_issues([_issue("normalized")]) == 1

    state = load_state()
    assert [issue["id"] for issue in state["issues"]] == ["SCAN-normalized"]
    assert state["stats"]["total_found"] == 1


def test_add_issues_uses_one_load_and_save_for_large_batch(tmp_path, monkeypatch):
    import uidetox.state as state_module

    monkeypatch.chdir(tmp_path)
    issues = [_issue(f"bulk-{index:03d}") for index in range(100)]
    duplicate = _issue("bulk-050")
    batch = [*issues, duplicate]
    load_calls = 0
    save_calls = 0
    original_load_state = state_module.load_state
    original_save_state = state_module.save_state

    def counted_load_state():
        nonlocal load_calls
        load_calls += 1
        return original_load_state()

    def counted_save_state(state):
        nonlocal save_calls
        save_calls += 1
        return original_save_state(state)

    monkeypatch.setattr(state_module, "load_state", counted_load_state)
    monkeypatch.setattr(state_module, "save_state", counted_save_state)

    assert add_issues(batch) == 100
    assert load_calls == 1
    assert save_calls == 1

    persisted = original_load_state()
    assert [issue["id"] for issue in persisted["issues"]] == [
        issue["id"] for issue in issues
    ]
    assert persisted["stats"]["total_found"] == 100
    assert "created_at" not in duplicate
