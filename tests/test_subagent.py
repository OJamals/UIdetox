import pytest

from uidetox import memory as memory_module
from uidetox import state as state_module
from uidetox.state import ensure_uidetox_dir
from uidetox.subagent import _shard_items, create_session, get_session, record_result


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    # Clear managed ChromaDB clients so each test gets a fresh state
    memory_module._chroma_clients.clear()
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None
    memory_module._chroma_clients.clear()


def test_shard_items_balances_workload_round_robin():
    shards = _shard_items([1, 2, 3, 4, 5], 3)
    assert shards == [[1, 4], [2, 5], [3]]


def test_record_result_clears_stale_review_request_when_confidence_recovers():
    session_id = create_session("verify", "verify prompt")
    assert record_result(session_id, {"note": "manual check required", "confidence": 0.6}) is True

    session_dir = ensure_uidetox_dir() / "sessions" / f"session_{session_id}"
    assert (session_dir / "review_request.json").exists()

    assert record_result(session_id, {"note": "all checks passed", "confidence": 0.95}) is True
    assert not (session_dir / "review_request.json").exists()

    session = get_session(session_id)
    assert session is not None
    assert session["meta"]["status"] == "completed"