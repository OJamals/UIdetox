"""Persistent agent memory: tracks reviewed files, learned patterns, session progress, and continuation state."""

import json
import math
import os
import re
import tempfile
from pathlib import Path

from uidetox.state import get_uidetox_dir, ensure_uidetox_dir
from uidetox.utils import now_iso


MEMORY_FILE = "memory.json"
_SEARCH_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _memory_path() -> Path:
    return get_uidetox_dir() / MEMORY_FILE


def _now_iso() -> str:
    return now_iso()


def _normalize_pattern_entries(entries: object) -> list[dict]:
    if not isinstance(entries, list):
        return []

    normalized: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("pattern")
        if not isinstance(pattern, str):
            continue
        clean_entry = {"pattern": pattern}
        if isinstance(entry.get("category"), str):
            clean_entry["category"] = entry["category"]
        if isinstance(entry.get("learned_at"), str):
            clean_entry["learned_at"] = entry["learned_at"]
        normalized.append(clean_entry)
    return normalized


def _normalize_note_entries(entries: object) -> list[dict]:
    if not isinstance(entries, list):
        return []

    normalized: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        note = entry.get("note")
        if not isinstance(note, str):
            continue
        clean_entry = {"note": note}
        if isinstance(entry.get("created_at"), str):
            clean_entry["created_at"] = entry["created_at"]
        normalized.append(clean_entry)
    return normalized


def _normalize_fix_history(entries: object) -> list[dict]:
    if not isinstance(entries, list):
        return []

    normalized: list[dict] = []
    required_fields = ("file", "issue", "fix")
    optional_fields = ("outcome", "recorded_at")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if any(not isinstance(entry.get(field), str) for field in required_fields):
            continue
        clean_entry = {field: entry[field] for field in required_fields}
        for field in optional_fields:
            if isinstance(entry.get(field), str):
                clean_entry[field] = entry[field]
        normalized.append(clean_entry)
    return normalized


def _rank_memory_entries(
    entries: list[dict],
    *,
    query: str | None,
    text_fields: tuple[str, ...],
    limit: int,
) -> list[dict]:
    """Return deterministic token-overlap matches from newest local memory."""
    if limit <= 0 or not entries:
        return []
    if not query or not query.strip():
        return entries[-limit:]

    query_text = query.casefold()
    query_tokens = set(_SEARCH_TOKEN_RE.findall(query_text))
    if not query_tokens:
        return entries[-limit:]

    ranked: list[tuple[int, float, int, dict]] = []
    for index, entry in enumerate(entries):
        searchable = " ".join(
            entry.get(field, "")
            for field in text_fields
            if isinstance(entry.get(field), str)
        ).casefold()
        entry_tokens = set(_SEARCH_TOKEN_RE.findall(searchable))
        overlap = len(query_tokens & entry_tokens)
        phrase_match = int(query_text in searchable)
        if not overlap and not phrase_match:
            continue
        ranked.append(
            (
                phrase_match,
                overlap / len(query_tokens),
                index,
                entry,
            )
        )

    ranked.sort(key=lambda item: item[:3], reverse=True)
    return [entry for _, _, _, entry in ranked[:limit]]


def _normalize_counter(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return 0
        return int(value)
    return 0


def _normalize_count_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, int] = {}
    for key, raw_value in value.items():
        normalized[key if isinstance(key, str) else str(key)] = _normalize_counter(
            raw_value
        )
    return normalized


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _normalize_last_scan(value: object) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None

    normalized = dict(value)
    normalized["timestamp"] = (
        normalized.get("timestamp")
        if isinstance(normalized.get("timestamp"), str)
        else ""
    )
    normalized["total_found"] = _normalize_counter(normalized.get("total_found"))
    normalized["files_scanned"] = _normalize_counter(normalized.get("files_scanned"))
    normalized["by_tier"] = _normalize_count_mapping(normalized.get("by_tier"))
    normalized["by_category"] = _normalize_count_mapping(normalized.get("by_category"))
    normalized["top_files"] = _normalize_string_list(normalized.get("top_files"))
    return normalized


def _normalize_session(value: object) -> dict:
    if not isinstance(value, dict):
        return {}

    normalized = dict(value)
    issues_fixed = _normalize_counter(normalized.get("issues_fixed_this_session", 0))
    has_explicit_counter = "issues_fixed_this_session" in normalized
    has_display_context = any(
        isinstance(normalized.get(key), str) and bool(normalized.get(key))
        for key in ("phase", "last_command", "last_component", "saved_at", "context")
    )

    if has_explicit_counter:
        normalized["issues_fixed_this_session"] = issues_fixed
    elif has_display_context:
        normalized["issues_fixed_this_session"] = 0

    known_session_keys = {
        "phase",
        "last_command",
        "last_component",
        "issues_fixed_this_session",
        "saved_at",
        "context",
    }
    if (
        not has_display_context
        and issues_fixed == 0
        and set(normalized).issubset(known_session_keys)
    ):
        return {}

    return normalized


def _normalize_progress_entry(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None

    action = entry.get("action")
    details = entry.get("details")
    timestamp = entry.get("timestamp")
    if not any(isinstance(value, str) for value in (action, details, timestamp)):
        return None

    normalized = dict(entry)
    normalized["action"] = action if isinstance(action, str) else ""
    normalized["details"] = details if isinstance(details, str) else ""
    normalized["timestamp"] = timestamp if isinstance(timestamp, str) else ""
    return normalized


def _normalize_progress_log(entries: object) -> list[dict]:
    if not isinstance(entries, list):
        return []

    normalized: list[dict] = []
    for entry in entries:
        clean_entry = _normalize_progress_entry(entry)
        if clean_entry is not None:
            normalized.append(clean_entry)
    return normalized


def load_memory() -> dict:
    """Load persistent agent memory, creating defaults if missing."""
    path = _memory_path()
    if not path.exists():
        return _default_memory()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return _default_memory()

    if not isinstance(data, dict):
        return _default_memory()

    # Ensure all fields exist with correct types.
    defaults = _default_memory()
    for key, default in defaults.items():
        if key not in data:
            data[key] = default
        elif default is None:
            if data[key] is not None and not isinstance(data[key], dict):
                data[key] = None
        elif not isinstance(data[key], type(default)):
            # Reset to default if type is wrong (e.g., list corrupted to string)
            data[key] = default

    data["patterns"] = _normalize_pattern_entries(data.get("patterns"))
    data["notes"] = _normalize_note_entries(data.get("notes"))
    data["fix_history"] = _normalize_fix_history(data.get("fix_history"))
    data["last_scan"] = _normalize_last_scan(data.get("last_scan"))
    data["session"] = _normalize_session(data.get("session"))
    data["progress_log"] = _normalize_progress_log(data.get("progress_log"))
    return data


def _default_memory() -> dict:
    return {
        "reviewed_files": {},
        "patterns": [],
        "notes": [],
        "fix_history": [],
        "exclusions": [],
        "session": {},
        "last_scan": None,
        "progress_log": [],
    }


def save_memory(memory: dict):
    """Save agent memory to disk atomically to prevent corruption."""
    d = ensure_uidetox_dir()
    target = _memory_path()
    fd, tmp_path = tempfile.mkstemp(dir=d, prefix="memory_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)


# ── Reviewed Files ──────────────────────────────────────────────


def mark_file_reviewed(file_path: str, *, verdict: str = "clean"):
    """Mark a file as reviewed with a verdict (clean, has_issues, skipped)."""
    mem = load_memory()
    mem["reviewed_files"][file_path] = {
        "reviewed_at": _now_iso(),
        "verdict": verdict,
    }
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

    Patterns are capped at 50 entries in local JSON state.
    """
    mem = load_memory()
    mem["patterns"].append(
        {
            "pattern": pattern,
            "category": category,
            "learned_at": _now_iso(),
        }
    )
    # Cap at 50 patterns — evict oldest
    mem["patterns"] = mem["patterns"][-50:]
    save_memory(mem)


def get_patterns(
    query: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """Return learned patterns, filtered by local token relevance when queried."""
    mem = load_memory()
    patterns = mem.get("patterns", [])
    return _rank_memory_entries(
        patterns,
        query=query,
        text_fields=("pattern", "category"),
        limit=limit,
    )


def add_note(note: str):
    """Store a free-form agent note for future reference.

    Notes are capped at 30 entries in JSON.
    """
    mem = load_memory()
    mem["notes"].append(
        {
            "note": note,
            "created_at": _now_iso(),
        }
    )
    # Cap at 30 notes — evict oldest
    mem["notes"] = mem["notes"][-30:]
    save_memory(mem)


def get_notes(
    query: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return agent notes, filtered by local token relevance when queried."""
    mem = load_memory()
    notes = mem.get("notes", [])
    return _rank_memory_entries(
        notes,
        query=query,
        text_fields=("note",),
        limit=limit,
    )


def record_fix_outcome(
    file_path: str,
    issue: str,
    fix: str,
    *,
    outcome: str = "resolved",
):
    """Persist a fix outcome so future agents can reuse relevant project history."""
    mem = load_memory()
    mem["fix_history"].append(
        {
            "file": file_path,
            "issue": issue,
            "fix": fix,
            "outcome": outcome,
            "recorded_at": _now_iso(),
        }
    )
    mem["fix_history"] = mem["fix_history"][-100:]
    save_memory(mem)


def get_fix_history(
    query: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return fix outcomes, filtered by local token relevance when queried."""
    mem = load_memory()
    fix_history = mem.get("fix_history", [])
    return _rank_memory_entries(
        fix_history,
        query=query,
        text_fields=("file", "issue", "fix", "outcome"),
        limit=limit,
    )


# ── Session & Progress (auto-save) ─────────────────────────────


def save_session(
    *,
    phase: str,
    last_command: str,
    last_component: str = "",
    issues_fixed: int = 0,
    context: str = "",
):
    """Auto-save session checkpoint for continuation.

    Called automatically by scan, resolve, batch-resolve, rescan.
    Allows the agent to resume from the exact point it left off.
    """
    mem = load_memory()
    mem["session"] = {
        "phase": phase,
        "last_command": last_command,
        "last_component": last_component,
        "issues_fixed_this_session": mem.get("session", {}).get(
            "issues_fixed_this_session", 0
        )
        + issues_fixed,
        "saved_at": _now_iso(),
        "context": context,
    }
    save_memory(mem)


def get_session() -> dict:
    """Return the current session state for continuation."""
    mem = load_memory()
    return mem.get("session", {})


def save_scan_summary(
    *,
    total_found: int,
    by_tier: dict,
    by_category: dict,
    files_scanned: int,
    top_files: list[str],
):
    """Auto-save the last scan summary for quick review without re-scanning."""
    mem = load_memory()
    mem["last_scan"] = {
        "timestamp": _now_iso(),
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
    mem = load_memory()
    log = mem.get("progress_log", [])
    log.append(
        {
            "action": action,
            "details": details,
            "timestamp": _now_iso(),
        }
    )
    # Keep last 50 entries to avoid unbounded growth
    mem["progress_log"] = log[-50:]
    save_memory(mem)


def get_progress_log() -> list[dict]:
    """Return the progress log."""
    mem = load_memory()
    return mem.get("progress_log", [])


def clear_memory():
    """Reset agent memory (used when starting fresh)."""
    save_memory(_default_memory())
