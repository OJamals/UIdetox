from uidetox.state import load_config, load_state, save_config, save_state


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
