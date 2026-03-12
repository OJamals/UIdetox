"""Tests for GitNexus query/context caching (gitnexus_cache module)."""

import json
import time
from pathlib import Path

import pytest

from uidetox import state as state_module
from uidetox.state import ensure_uidetox_dir
from uidetox.gitnexus_cache import (
    _cache_dir,
    _cache_key,
    cache_query_result,
    cache_stats,
    get_cached_result,
    get_iteration,
    invalidate_cache,
    list_cached_entries,
    set_iteration,
)


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state_module._project_root_cache = None
    ensure_uidetox_dir()
    yield
    state_module._project_root_cache = None


class TestCacheKey:
    def test_deterministic(self):
        k1 = _cache_key("find all components", "query")
        k2 = _cache_key("find all components", "query")
        assert k1 == k2

    def test_different_queries_different_keys(self):
        k1 = _cache_key("query A", "query")
        k2 = _cache_key("query B", "query")
        assert k1 != k2

    def test_includes_kind_prefix(self):
        q = _cache_key("test", "query")
        c = _cache_key("test", "context")
        assert q.startswith("query_")
        assert c.startswith("context_")


class TestCacheReadWrite:
    def test_cache_and_retrieve(self):
        data = {"files": ["a.tsx", "b.tsx"], "count": 2}
        cache_query_result("frontend components", data)

        result = get_cached_result("frontend components")
        assert result == data

    def test_cache_miss_returns_none(self):
        result = get_cached_result("nonexistent query")
        assert result is None

    def test_context_type_caching(self):
        data = {"context": "full project layout"}
        cache_query_result("project context", data, kind="context")

        result = get_cached_result("project context", kind="context")
        assert result == data

    def test_ttl_expiry(self):
        cache_query_result("short lived", {"x": 1})
        # With a 0-second TTL, the entry should be stale immediately
        result = get_cached_result("short lived", ttl=0)
        assert result is None

    def test_iteration_staleness(self):
        """Entries from a previous iteration should not be returned."""
        set_iteration(0)
        cache_query_result("old query", {"old": True})

        # Advance iteration
        set_iteration(1)

        result = get_cached_result("old query")
        assert result is None  # stale from previous iteration


class TestIterationManagement:
    def test_set_and_get_iteration(self):
        set_iteration(5)
        assert get_iteration() == 5

    def test_advancing_iteration_prunes_stale(self):
        set_iteration(0)
        cache_query_result("iter0 query", {"data": "old"})
        assert get_cached_result("iter0 query") is not None

        set_iteration(1)
        # Pruning happens on iteration advance; the file should be deleted
        entries = list_cached_entries()
        # Stale entries are pruned on iteration advance
        iter0_entries = [e for e in entries if e.get("iteration", -1) < 1]
        assert len(iter0_entries) == 0


class TestCacheStats:
    def test_stats_empty_cache(self):
        stats = cache_stats()
        assert stats["total_entries"] == 0
        assert stats["queries"] == 0
        assert stats["contexts"] == 0

    def test_stats_after_caching(self):
        cache_query_result("q1", {"a": 1})
        cache_query_result("q2", {"b": 2})
        cache_query_result("c1", {"c": 3}, kind="context")

        stats = cache_stats()
        assert stats["total_entries"] == 3
        assert stats["queries"] == 2
        assert stats["contexts"] == 1


class TestInvalidateCache:
    def test_invalidate_clears_all_entries(self):
        cache_query_result("q1", {"x": 1})
        cache_query_result("q2", {"y": 2})
        assert len(list_cached_entries()) == 2

        removed = invalidate_cache()
        assert removed == 2
        assert len(list_cached_entries()) == 0


class TestListCachedEntries:
    def test_lists_metadata_without_result_data(self):
        cache_query_result("test query", {"big": "payload"})
        entries = list_cached_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["query"] == "test query"
        assert entry["kind"] == "query"
        assert "result" not in entry  # metadata only
