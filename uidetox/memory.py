"""Persistent agent memory: tracks reviewed files, learned patterns, session progress, and continuation state."""

import json
from pathlib import Path

from uidetox.state import get_uidetox_dir, ensure_uidetox_dir
from uidetox.utils import now_iso


MEMORY_FILE = "memory.json"


def _memory_path() -> Path:
    return get_uidetox_dir() / MEMORY_FILE


def _now_iso() -> str:
    return now_iso()


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
    """Save agent memory to disk."""
    ensure_uidetox_dir()
    with open(_memory_path(), "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


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
    """Record a learned pattern (e.g., 'this codebase uses Tailwind, not vanilla CSS')."""
    mem = load_memory()
    mem["patterns"].append({
        "pattern": pattern,
        "category": category,
        "learned_at": _now_iso(),
    })
    save_memory(mem)


def get_patterns() -> list[dict]:
    """Return all learned patterns."""
    mem = load_memory()
    return mem.get("patterns", [])


def add_note(note: str):
    """Store a free-form agent note for future reference."""
    mem = load_memory()
    mem["notes"].append({
        "note": note,
        "created_at": _now_iso(),
    })
    save_memory(mem)


def get_notes() -> list[dict]:
    """Return all agent notes."""
    mem = load_memory()
    return mem.get("notes", [])


# ── Session & Progress (auto-save) ─────────────────────────────


def save_session(*, phase: str, last_command: str, last_component: str = "",
                 issues_fixed: int = 0, context: str = ""):
    """Auto-save session checkpoint for continuation.

    Called automatically by scan, resolve, batch-resolve, rescan.
    Allows the agent to resume from the exact point it left off.
    """
    mem = load_memory()
    mem["session"] = {
        "phase": phase,
        "last_command": last_command,
        "last_component": last_component,
        "issues_fixed_this_session": mem.get("session", {}).get("issues_fixed_this_session", 0) + issues_fixed,
        "saved_at": _now_iso(),
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
    mem = load_memory()
    mem["last_scan"] = {
        "timestamp": _now_iso(),
        "total_found": total_found,
        "by_tier": by_tier,
        "by_category": by_category,
        "files_scanned": files_scanned,
        "top_files": top_files[:10],  # Top 10 most affected files
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
    log.append({
        "action": action,
        "details": details,
        "timestamp": _now_iso(),
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
    save_memory(_default_memory())
