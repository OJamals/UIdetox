"""GitNexus query/context output persistence.

Caches the results of expensive GitNexus graph queries per iteration
so repeated calls within the same loop cycle are served from disk,
improving deterministic agent behavior and reducing latency.

Cache structure:
    .uidetox/gitnexus_cache/
        meta.json               — iteration counter + TTL info
        query_<hash>.json       — cached query results
        context_<hash>.json     — cached context results

Cache invalidation:
    - Automatic: when iteration counter advances
    - Manual: ``invalidate_cache()``
    - TTL: entries older than ``_DEFAULT_TTL_SECONDS``
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from uidetox.state import get_uidetox_dir, ensure_uidetox_dir, _atomic_write_json
from uidetox.utils import now_iso


# Default TTL: 10 minutes — long enough for a full loop iteration
_DEFAULT_TTL_SECONDS = 600


def _cache_dir() -> Path:
    """Return the GitNexus cache directory, creating it if needed."""
    d = get_uidetox_dir() / "gitnexus_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(query: str, kind: str = "query") -> str:
    """Generate a stable cache key from a query string."""
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return f"{kind}_{h}"


def _meta_path() -> Path:
    return _cache_dir() / "meta.json"


def _load_meta() -> dict:
    """Load cache metadata."""
    mp = _meta_path()
    if not mp.exists():
        return {"iteration": 0, "created_at": now_iso(), "entries": 0}
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"iteration": 0, "created_at": now_iso(), "entries": 0}


def _save_meta(meta: dict) -> None:
    """Persist cache metadata."""
    _atomic_write_json(_meta_path(), meta, dir=_cache_dir())


def set_iteration(iteration: int) -> None:
    """Update the current iteration counter.

    When the iteration advances, stale entries from previous iterations
    are automatically pruned.
    """
    meta = _load_meta()
    prev = meta.get("iteration", 0)
    meta["iteration"] = iteration
    meta["updated_at"] = now_iso()
    _save_meta(meta)

    # Prune entries from previous iterations
    if iteration > prev:
        _prune_stale_entries()


def get_iteration() -> int:
    """Return the current iteration counter."""
    return _load_meta().get("iteration", 0)


def cache_query_result(query: str, result: Any, *, kind: str = "query") -> Path:
    """Cache the result of a GitNexus query.

    Args:
        query: The query string or context name.
        result: The result data (must be JSON-serializable).
        kind: "query" or "context" — determines filename prefix.

    Returns:
        Path to the cached file.
    """
    ensure_uidetox_dir()
    key = _cache_key(query, kind)
    cache_path = _cache_dir() / f"{key}.json"

    meta = _load_meta()
    entry = {
        "query": query,
        "kind": kind,
        "result": result,
        "iteration": meta.get("iteration", 0),
        "cached_at": now_iso(),
        "timestamp": time.time(),
    }

    _atomic_write_json(cache_path, entry, dir=_cache_dir())

    meta["entries"] = meta.get("entries", 0) + 1
    meta["last_cached_at"] = now_iso()
    _save_meta(meta)

    return cache_path


def get_cached_result(query: str, *, kind: str = "query", ttl: int | None = None) -> Any | None:
    """Retrieve a cached GitNexus result if fresh.

    Args:
        query: The query string or context name.
        kind: "query" or "context".
        ttl: Override TTL in seconds (default: ``_DEFAULT_TTL_SECONDS``).

    Returns:
        The cached result data, or None if not found or stale.
    """
    if ttl is None:
        ttl = _DEFAULT_TTL_SECONDS

    key = _cache_key(query, kind)
    cache_path = _cache_dir() / f"{key}.json"

    if not cache_path.exists():
        return None

    try:
        entry = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    # Check TTL
    cached_ts = entry.get("timestamp", 0)
    if time.time() - cached_ts > ttl:
        return None

    # Check iteration freshness
    meta = _load_meta()
    current_iter = meta.get("iteration", 0)
    entry_iter = entry.get("iteration", -1)
    if entry_iter < current_iter:
        return None

    return entry.get("result")


def list_cached_entries() -> list[dict]:
    """List all cached entries with their metadata (excluding result data)."""
    entries: list[dict] = []
    cache = _cache_dir()

    for f in sorted(cache.iterdir()):
        if f.name == "meta.json" or not f.name.endswith(".json"):
            continue
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            entries.append({
                "file": f.name,
                "query": entry.get("query", ""),
                "kind": entry.get("kind", ""),
                "iteration": entry.get("iteration", -1),
                "cached_at": entry.get("cached_at", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return entries


def _prune_stale_entries() -> int:
    """Remove cache entries from previous iterations or past TTL."""
    cache = _cache_dir()
    meta = _load_meta()
    current_iter = meta.get("iteration", 0)
    now = time.time()
    pruned = 0

    for f in list(cache.iterdir()):
        if f.name == "meta.json" or not f.name.endswith(".json"):
            continue
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            entry_iter = entry.get("iteration", -1)
            entry_ts = entry.get("timestamp", 0)

            if entry_iter < current_iter or (now - entry_ts > _DEFAULT_TTL_SECONDS):
                f.unlink(missing_ok=True)
                pruned += 1
        except (json.JSONDecodeError, OSError):
            f.unlink(missing_ok=True)
            pruned += 1

    if pruned > 0:
        meta["entries"] = max(0, meta.get("entries", 0) - pruned)
        _save_meta(meta)

    return pruned


def invalidate_cache() -> int:
    """Clear the entire GitNexus cache. Returns number of entries removed."""
    cache = _cache_dir()
    count = 0
    for f in list(cache.iterdir()):
        if f.name == "meta.json":
            continue
        try:
            f.unlink(missing_ok=True)
            count += 1
        except OSError:
            pass

    meta = _load_meta()
    meta["entries"] = 0
    meta["invalidated_at"] = now_iso()
    _save_meta(meta)

    return count


def cache_stats() -> dict:
    """Return cache statistics."""
    meta = _load_meta()
    entries = list_cached_entries()
    return {
        "iteration": meta.get("iteration", 0),
        "total_entries": len(entries),
        "queries": sum(1 for e in entries if e.get("kind") == "query"),
        "contexts": sum(1 for e in entries if e.get("kind") == "context"),
        "created_at": meta.get("created_at", ""),
        "last_cached_at": meta.get("last_cached_at", ""),
    }
