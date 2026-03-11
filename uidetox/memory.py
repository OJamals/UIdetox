"""Persistent agent memory: tracks reviewed files, learned patterns, and agent notes."""

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
        data.setdefault("reviewed_files", {})
        data.setdefault("patterns", [])
        data.setdefault("notes", [])
        data.setdefault("exclusions", [])
        return data
    except (json.JSONDecodeError, OSError):
        return _default_memory()


def _default_memory() -> dict:
    return {
        "reviewed_files": {},
        "patterns": [],
        "notes": [],
        "exclusions": [],
    }


def save_memory(memory: dict):
    """Save agent memory to disk."""
    ensure_uidetox_dir()
    with open(_memory_path(), "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


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


def clear_memory():
    """Reset agent memory (used when starting fresh)."""
    save_memory(_default_memory())
