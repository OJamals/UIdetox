"""Persistent agent memory: tracks reviewed files, learned patterns, session progress, and continuation state."""

import atexit
import json
import logging
from pathlib import Path

import hashlib
from typing import Any
from uidetox.state import get_uidetox_dir, ensure_uidetox_dir, _atomic_write_json, _locked_file
from uidetox.utils import now_iso

logger = logging.getLogger(__name__)

# ── ChromaDB client management ──────────────────────────────────
# We keep at most one live client per db_path.  An atexit hook
# guarantees connections are closed when the process exits.

_chroma_clients: dict[str, Any] = {}


def _get_chroma_client_cached(db_path: str):
    """Get or create a ChromaDB PersistentClient for *db_path*.

    Clients are cached per path and automatically closed at process exit.
    """
    if db_path in _chroma_clients:
        return _chroma_clients[db_path]
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_clients[db_path] = client
        return client
    except ImportError:
        return None


def close_chroma_clients() -> None:
    """Close all cached ChromaDB clients, releasing file handles and memory."""
    for db_path in list(_chroma_clients):
        try:
            del _chroma_clients[db_path]
            logger.debug("Closed ChromaDB client for %s", db_path)
        except (KeyError, AttributeError) as exc:
            logger.debug("Error closing ChromaDB client for %s: %s", db_path, exc)


# Ensure all ChromaDB clients are closed when the process exits.
atexit.register(close_chroma_clients)


def _get_chroma_client():
    """Return a ChromaDB client for the current project's .uidetox/chroma dir."""
    db_path = str((get_uidetox_dir() / "chroma").resolve())
    return _get_chroma_client_cached(db_path)


def _get_collection(name: str) -> Any:
    """Get a ChromaDB collection for semantic memory search."""
    client = _get_chroma_client()
    if client is None:
        return None
    try:
        return client.get_or_create_collection(name=name)
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to get/create ChromaDB collection %r: %s", name, exc)
        return None


MEMORY_FILE = "memory.json"
_EMBEDDED_COLLECTIONS = ("patterns", "notes", "file_contexts", "fix_history")


def _memory_path() -> Path:
    return get_uidetox_dir() / MEMORY_FILE


# Timestamp helper: use now_iso() directly from utils


def load_memory() -> dict:
    """Load persistent agent memory, creating defaults if missing."""
    path = _memory_path()
    if not path.exists():
        return _default_memory()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all fields exist
        for key, default in _default_memory().items():
            data.setdefault(key, default)
        return data
    except (json.JSONDecodeError, OSError):
        return _default_memory()


def _default_memory() -> dict:
    return {
        "reviewed_files": {},
        "patterns": [],
        "notes": [],
        "exclusions": [],
        "session": {},
        "last_scan": None,
        "progress_log": [],
    }


def save_memory(memory: dict):
    """Save agent memory to disk atomically to prevent corruption."""
    ensure_uidetox_dir()
    _atomic_write_json(_memory_path(), memory)


def _clear_embedding_memory() -> None:
    """Delete semantic memory collections so reset operations are truly clean."""
    client = _get_chroma_client()
    if client is None:
        return
    for collection_name in _EMBEDDED_COLLECTIONS:
        try:
            client.delete_collection(collection_name)  # type: ignore[attr-defined]
        except Exception:
            # Collection doesn't exist or DB error — skip
            continue


# ── Embedding compaction ────────────────────────────────────────

# Hard caps per collection.  Once a collection exceeds _MAX_EMBEDDINGS,
# compact_embeddings() trims the oldest entries (by insertion order) down
# to _TARGET_EMBEDDINGS so the trim isn't needed on every write.
_MAX_EMBEDDINGS = 500
_TARGET_EMBEDDINGS = 400


def compact_embeddings() -> dict[str, int]:
    """Trim oversized ChromaDB collections to bounded sizes.

    Returns a dict of {collection_name: items_removed}.
    Call periodically (e.g. after a scan or on ``uidetox finish``).
    """
    client = _get_chroma_client()
    if client is None:
        return {}

    removed: dict[str, int] = {}
    for name in _EMBEDDED_COLLECTIONS:
        try:
            col = client.get_collection(name)
        except Exception:
            # Collection doesn't exist yet — nothing to compact
            continue
        count = col.count()
        if count <= _MAX_EMBEDDINGS:
            continue

        # Fetch all IDs (ChromaDB returns insertion-ordered by default)
        all_data = col.get(limit=count)
        ids = all_data.get("ids", [])
        to_delete = ids[: count - _TARGET_EMBEDDINGS]
        if to_delete:
            col.delete(ids=to_delete)
            removed[name] = len(to_delete)
            logger.info("Compacted %s: removed %d / %d embeddings", name, len(to_delete), count)

    return removed


# ── Reviewed Files ──────────────────────────────────────────────


_MAX_REVIEWED_FILES = 500


def mark_file_reviewed(file_path: str, *, verdict: str = "clean") -> None:
    """Mark a file as reviewed with a verdict (clean, has_issues, skipped)."""
    with _locked_file("memory"):
        mem = load_memory()
        reviewed = mem["reviewed_files"]
        reviewed[file_path] = {
            "reviewed_at": now_iso(),
            "verdict": verdict,
        }
        # Cap reviewed_files to prevent unbounded growth
        if len(reviewed) > _MAX_REVIEWED_FILES:
            # Evict oldest entries (by reviewed_at timestamp)
            sorted_keys = sorted(
                reviewed, key=lambda k: reviewed[k].get("reviewed_at", "")
            )
            for k in sorted_keys[: len(reviewed) - _MAX_REVIEWED_FILES]:
                del reviewed[k]
        save_memory(mem)


def is_file_reviewed(file_path: str) -> bool:
    """Check if a file has been reviewed in this session."""
    mem = load_memory()
    return file_path in mem.get("reviewed_files", {})


def get_reviewed_files() -> dict:
    """Return all reviewed files with their verdicts."""
    mem = load_memory()
    return mem.get("reviewed_files", {})


# ── Patterns & Notes ────────────────────────────────────────────


def add_pattern(pattern: str, *, category: str = "general"):
    """Record a learned pattern (e.g., 'this codebase uses Tailwind, not vanilla CSS').

    Patterns are capped at 50 entries in JSON state, but all are embedded.
    """
    with _locked_file("memory"):
        mem = load_memory()
        mem["patterns"].append({
            "pattern": pattern,
            "category": category,
            "learned_at": now_iso(),
        })
        # Cap at 50 patterns — evict oldest
        mem["patterns"] = mem["patterns"][-50:]
        save_memory(mem)

    collection = _get_collection("patterns")
    if collection:
        # Include category in hash to avoid collision when same text has different categories
        doc_id = hashlib.md5(f"{category}:{pattern}".encode("utf-8")).hexdigest()
        collection.upsert(
            documents=[pattern],
            metadatas=[{"category": category}],
            ids=[doc_id]
        )


def get_patterns(query: str | None = None, limit: int = 15) -> list[dict]:
    """Return learned patterns. Performs semantic search if query is provided."""
    mem = load_memory()
    patterns = mem.get("patterns", [])

    if query and patterns:
        collection = _get_collection("patterns")
        if collection:
            cnt = collection.count() # type: ignore
            if cnt > 0:
                n = min(limit, cnt) # type: ignore
                results = collection.query(query_texts=[query], n_results=n)
                if results and results.get("documents") and results["documents"][0]:
                    matched = []
                    docs = results["documents"][0]
                    metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                    for doc, meta in zip(docs, metas):
                        matched.append({
                            "pattern": doc,
                            "category": meta.get("category", "general") if meta else "general"
                        })
                    return matched

    return patterns[-limit:] if patterns else []


def add_note(note: str):
    """Store a free-form agent note for future reference.

    Notes are capped at 30 entries in JSON.
    """
    with _locked_file("memory"):
        mem = load_memory()
        mem["notes"].append({
            "note": note,
            "created_at": now_iso(),
        })
        # Cap at 30 notes — evict oldest
        mem["notes"] = mem["notes"][-30:]
        save_memory(mem)

    collection = _get_collection("notes")
    if collection:
        doc_id = hashlib.md5(note.encode("utf-8")).hexdigest()
        collection.upsert(
            documents=[note],
            metadatas=[{"type": "note"}],
            ids=[doc_id]
        )


def get_notes(query: str | None = None, limit: int = 10) -> list[dict]:
    """Return agent notes. Performs semantic search if query is provided."""
    mem = load_memory()
    notes = mem.get("notes", [])

    if query and notes:
        collection = _get_collection("notes")
        if collection:
            cnt = collection.count() # type: ignore
            if cnt > 0:
                n = min(limit, cnt) # type: ignore
                results = collection.query(query_texts=[query], n_results=n)
                if results and results.get("documents") and results["documents"][0]:
                    matched = []
                    docs = results["documents"][0]
                    for doc in docs:
                        matched.append({"note": doc})
                    return matched

    return notes[-limit:] if notes else []


# ── Session & Progress (auto-save) ─────────────────────────────


def save_session(*, phase: str, last_command: str, last_component: str = "",
                 issues_fixed: int = 0, context: str = ""):
    """Auto-save session checkpoint for continuation.

    Called automatically by scan, resolve, batch-resolve, rescan.
    Allows the agent to resume from the exact point it left off.
    """
    with _locked_file("memory"):
        mem = load_memory()
        prev_fixed = mem.get("session", {}).get("issues_fixed_this_session", 0)
        mem["session"] = {
            "phase": phase,
            "last_command": last_command,
            "last_component": last_component,
            # Only accumulate when caller reports a positive delta.
            "issues_fixed_this_session": prev_fixed + max(0, issues_fixed),
            "saved_at": now_iso(),
            "context": context,
        }
        save_memory(mem)


def get_session() -> dict:
    """Return the current session state for continuation."""
    mem = load_memory()
    return mem.get("session", {})


def save_scan_summary(*, total_found: int, by_tier: dict, by_category: dict,
                      files_scanned: int, top_files: list[str]):
    """Auto-save the last scan summary for quick review without re-scanning."""
    with _locked_file("memory"):
        mem = load_memory()
        mem["last_scan"] = {
            "timestamp": now_iso(),
            "total_found": total_found,
            "by_tier": by_tier,
            "by_category": by_category,
            "files_scanned": files_scanned,
            "top_files": top_files[:10],  # type: ignore
        }
        save_memory(mem)


def get_last_scan() -> dict | None:
    """Return the last scan summary."""
    mem = load_memory()
    return mem.get("last_scan")


def log_progress(action: str, details: str = ""):
    """Append to the auto-progress log. Called after every significant action."""
    with _locked_file("memory"):
        mem = load_memory()
        log = mem.get("progress_log", [])
        log.append({
            "action": action,
            "details": details,
            "timestamp": now_iso(),
        })
        # Keep last 50 entries to avoid unbounded growth
        mem["progress_log"] = log[-50:]
        save_memory(mem)


def get_progress_log() -> list[dict]:
    """Return the progress log."""
    mem = load_memory()
    return mem.get("progress_log", [])


def clear_memory():
    """Reset agent memory (used when starting fresh)."""
    with _locked_file("memory"):
        save_memory(_default_memory())
    _clear_embedding_memory()


# ── Embedding-Based Context Injection ───────────────────────────


def embed_file_context(file_path: str, context: str, *, category: str = "file_context"):
    """Embed file-specific context into ChromaDB for semantic retrieval.

    Use this to store observations, fix history, and design decisions per-file
    so that future sub-agents working on the same component automatically get
    relevant context without bloating the global prompt.
    """
    collection = _get_collection("file_contexts")
    if not collection:
        return

    doc_id = hashlib.md5(f"{file_path}:{context}".encode("utf-8")).hexdigest()
    collection.upsert(
        documents=[context],
        metadatas=[{
            "file": file_path,
            "category": category,
            "embedded_at": now_iso(),
        }],
        ids=[doc_id],
    )


def embed_fix_outcome(file_path: str, issue: str, fix: str, *, outcome: str = "resolved"):
    """Embed a fix outcome so future agents can learn from past fixes.

    This creates a semantic record: "For issue X in file Y, fix Z worked/failed."
    Future sub-agents working on similar issues get this injected automatically.
    """
    doc = f"File: {file_path}\nIssue: {issue}\nFix applied: {fix}\nOutcome: {outcome}"

    collection = _get_collection("fix_history")
    if not collection:
        return

    doc_id = hashlib.md5(doc.encode("utf-8")).hexdigest()
    collection.upsert(
        documents=[doc],
        metadatas=[{
            "file": file_path,
            "outcome": outcome,
            "embedded_at": now_iso(),
        }],
        ids=[doc_id],
    )


def query_relevant_context(query: str, *, collections: list[str] | None = None,
                           limit: int = 10) -> list[dict]:
    """Semantic search across all memory collections for relevant context.

    Searches patterns, notes, file_contexts, and fix_history unless
    specific collections are provided. Returns ranked results with metadata.
    """
    target_collections = collections or ["patterns", "notes", "file_contexts", "fix_history"]
    results: list[dict] = []

    for coll_name in target_collections:
        collection = _get_collection(coll_name)
        if not collection:
            continue

        cnt = collection.count()
        if cnt == 0:
            continue

        n = min(limit, cnt)
        try:
            search_results = collection.query(query_texts=[query], n_results=n)
        except Exception as exc:
            logger.debug("ChromaDB query failed for %s: %s", coll_name, exc)
            continue

        if not search_results or not search_results.get("documents"):
            continue

        docs = search_results["documents"][0]
        metas = search_results.get("metadatas", [[]])[0]
        distances = search_results.get("distances", [[]])[0]

        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            # Chroma default is squared L2 distance, typical range [0, 4] for normalized vectors
            # A distance of 0 means identical, 2 means orthogonal, 4 means opposite.
            # We convert this to a relevance score in [0, 1] using cosine similarity equivalent.
            distance = distances[i] if i < len(distances) else 2.0
            relevance = max(0.0, 1.0 - (distance / 2.0))
            
            # Only include results with some actual semantic relevance
            if relevance > 0.1:
                results.append({
                    "text": doc,
                    "collection": coll_name,
                    "metadata": meta if meta else {},
                    "relevance": relevance,
                })

    # Sort by relevance (highest first) and cap
    results.sort(key=lambda r: r["relevance"], reverse=True)
    return results[:limit]


def build_targeted_context(files: list[str], *, issue_text: str = "",
                           max_tokens_estimate: int = 2000) -> str:
    """Build a targeted context block by querying embeddings for files and issues.

    Instead of injecting ALL patterns and notes (which bloats prompts),
    this returns only the most relevant context for the specific files
    and issues being worked on. Keeps sub-agent prompts focused and efficient.
    """
    if not files and not issue_text:
        return ""

    # Build a composite query from file paths and issue descriptions
    query_parts = []
    for f in files[:5]:  # Cap to avoid overly long queries
        query_parts.append(Path(f).stem)
    if issue_text:
        query_parts.append(issue_text[:200])

    query = " ".join(query_parts)
    if not query.strip():
        return ""

    results = query_relevant_context(query, limit=15)
    if not results:
        return ""

    # Group by collection for clean presentation
    sections: dict[str, list[str]] = {}
    collection_labels = {
        "patterns": "Relevant Design Patterns",
        "notes": "Relevant Agent Notes",
        "file_contexts": "Prior File Observations",
        "fix_history": "Related Fix History",
    }

    char_count = 0
    # Rough estimate: ~4 chars per token
    char_limit = max_tokens_estimate * 4

    for r in results:
        if char_count >= char_limit:
            break
        coll = r["collection"]
        label = collection_labels.get(coll, coll)
        if label not in sections:
            sections[label] = []
        text = r["text"]
        rel = r["relevance"]
        entry = f"  - [{rel:.0%}] {text}"
        sections[label].append(entry)
        char_count += len(entry)

    if not sections:
        return ""

    lines = ["## Targeted Context (embedding-matched)"]
    for label, entries in sections.items():
        lines.append(f"\n### {label}")
        lines.extend(entries)

    return "\n".join(lines) + "\n"
