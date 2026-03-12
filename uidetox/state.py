"""State and Config Management for UIdetox."""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl  # type: ignore[attr-defined]
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

from uidetox.utils import now_iso

UIDETOX_DIR = ".uidetox"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
_TIER_PRIORITY = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}


def _atomic_write_json(target: Path, data: dict, *, dir: Path | None = None) -> None:
    """Write *data* to *target* atomically via temp-file + rename.

    On serialisation failure the temp file is cleaned up so it never
    leaks on disk.
    """
    write_dir = dir or target.parent
    fd, tmp_path = tempfile.mkstemp(dir=write_dir, prefix=target.stem + "_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        # Clean up the leaked temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── File-based locking for safe concurrent state mutations ──────

@contextmanager
def _locked_file(lock_name: str) -> Iterator[None]:
    """Acquire an exclusive POSIX file lock for read-modify-write cycles.

    Uses ``fcntl.flock`` which is safe across multiple processes (e.g.
    when ``uidetox loop`` spawns several ``uidetox`` sub-processes).
    """
    lock_path = get_uidetox_dir() / f".{lock_name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDONLY)
    try:
        if _HAS_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_EX)  # type: ignore[union-attr]
        yield
    finally:
        if _HAS_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[union-attr]
        os.close(fd)


# ── Cached project root ─────────────────────────────────────────

_project_root_cache: Path | None = None


def get_project_root() -> Path:
    """Finds the base path containing .uidetox or defaults to cwd.

    The result is cached per-process so repeated calls avoid filesystem
    traversal on every state load/save.
    """
    global _project_root_cache
    if _project_root_cache is not None:
        return _project_root_cache
    cwd = Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / UIDETOX_DIR).exists():
            _project_root_cache = current
            return current
        current = current.parent
    _project_root_cache = cwd
    return cwd


def get_uidetox_dir() -> Path:
    return get_project_root() / UIDETOX_DIR

def ensure_uidetox_dir():
    d = get_uidetox_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_config() -> dict:
    config_path = get_uidetox_dir() / CONFIG_FILE
    default_config = {
        "DESIGN_VARIANCE": 8,
        "MOTION_INTENSITY": 6,
        "VISUAL_DENSITY": 4
    }
    if not config_path.exists():
        return default_config
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default_config

def save_config(config: dict):
    d = ensure_uidetox_dir()
    _atomic_write_json(d / CONFIG_FILE, config, dir=d)

def load_state() -> dict:
    """
    State format:
    {
      "last_scan": "2024-01-01T00:00:00Z",
      "issues": [...],
      "resolved": [...],
      "stats": { "total_found": 0, "total_resolved": 0, "scans_run": 0 }
    }
    """
    state_path = get_uidetox_dir() / STATE_FILE
    if not state_path.exists():
        return _default_state()
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = _default_state()
        
    # Ensure new fields exist for backwards compat
    data.setdefault("resolved", [])
    data.setdefault("stats", {"total_found": 0, "total_resolved": 0, "scans_run": 0})
    data.setdefault("subjective", {})
    return data

def _default_state() -> dict:
    return {
        "last_scan": None,
        "issues": [],
        "resolved": [],
        "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
    }

def save_state(state: dict):
    d = ensure_uidetox_dir()
    _atomic_write_json(d / STATE_FILE, state, dir=d)


def _normalize_issue_text(value: str) -> str:
    return " ".join(str(value).split()).strip().lower()


def _issue_signature(issue: dict, *, phase_scoped: bool = False) -> str:
    """Create a stable signature for deduplicating pending issues.

    When *phase_scoped* is True the phase tag (e.g. ``"check"``,
    ``"scan"``, ``"review"``) is included in the key so that
    lint/format can run once per phase while still avoiding duplicate
    issues within a single phase.

    Backward compatible: omitting ``phase`` or setting *phase_scoped*
    to False produces the same global signature as before.
    """
    parts = [
        _normalize_issue_text(issue.get("file", "")),
        _normalize_issue_text(issue.get("issue", "")),
    ]
    if phase_scoped:
        phase = _normalize_issue_text(issue.get("phase", ""))
        if phase:
            parts.append(phase)
    return "::".join(parts)


def _merge_issue(existing: dict, incoming: dict) -> bool:
    """Merge a duplicate issue into an existing queue entry.

    Returns True if the existing item was updated.
    """
    changed = False

    existing_tier = existing.get("tier", "T4")
    incoming_tier = incoming.get("tier", existing_tier)
    if _TIER_PRIORITY.get(incoming_tier, 99) < _TIER_PRIORITY.get(existing_tier, 99):
        existing["tier"] = incoming_tier
        changed = True

    incoming_command = str(incoming.get("command", "") or "").strip()
    existing_command = str(existing.get("command", "") or "").strip()
    if incoming_command and incoming_command != existing_command:
        if not existing_command or len(incoming_command) >= len(existing_command):
            existing["command"] = incoming_command
            changed = True

    return changed

def get_issue(issue_id: str) -> dict | None:
    state = load_state()
    for item in state.get("issues", []):
        if item.get("id") == issue_id:
            return item
    return None

def remove_issue(issue_id: str, note: str = "") -> bool:
    with _locked_file("state"):
        state = load_state()
        original_len = len(state.get("issues", []))
        removed = [i for i in state.get("issues", []) if i.get("id") == issue_id]
        state["issues"] = [i for i in state.get("issues", []) if i.get("id") != issue_id]
        if len(state["issues"]) < original_len:
            # Track resolved issues
            for r in removed:
                r["resolved_at"] = now_iso()
                if note:
                    r["note"] = note
                state.setdefault("resolved", []).append(r)
            state.setdefault("stats", {})
            state["stats"]["total_resolved"] = state["stats"].get("total_resolved", 0) + len(removed)
            save_state(state)
            return True
        return False

def add_issue(issue: dict, *, phase: str = "") -> str:
    """Add a single issue to the queue with optional phase-scoped dedup.

    When *phase* is provided it is stored on the issue and used as part
    of the dedup signature so identical lint/format findings from
    different phases are kept separate while true duplicates within one
    phase are still suppressed.
    """
    if phase:
        issue["phase"] = phase
    phase_scoped = bool(issue.get("phase"))
    with _locked_file("state"):
        state = load_state()
        issues = state.setdefault("issues", [])
        signature = _issue_signature(issue, phase_scoped=phase_scoped)
        for existing in issues:
            if _issue_signature(existing, phase_scoped=phase_scoped) != signature:
                continue
            if _merge_issue(existing, issue):
                save_state(state)
                return "updated"
            return "skipped"
        issue["created_at"] = now_iso()
        issues.append(issue)
        state.setdefault("stats", {})
        state["stats"]["total_found"] = state["stats"].get("total_found", 0) + 1
        save_state(state)
        return "added"


def batch_add_issues(new_issues: list[dict], *, phase: str = "") -> dict[str, int]:
    """Add multiple issues in a single load/save cycle.

    Significantly more efficient than calling add_issue() in a loop
    during scans that may produce hundreds of issues.

    When *phase* is provided it is stored on every issue and used for
    phase-scoped deduplication.
    """
    if not new_issues:
        return {"added": 0, "updated": 0, "skipped": 0}
    if phase:
        for issue in new_issues:
            issue["phase"] = phase
    # Determine whether any issue carries a phase tag
    phase_scoped = any(issue.get("phase") for issue in new_issues)
    with _locked_file("state"):
        state = load_state()
        issues = state.setdefault("issues", [])
        existing_by_signature = {
            _issue_signature(issue, phase_scoped=phase_scoped): issue
            for issue in issues
        }
        ts = now_iso()
        added = 0
        updated = 0
        skipped = 0
        for issue in new_issues:
            signature = _issue_signature(issue, phase_scoped=phase_scoped)
            existing = existing_by_signature.get(signature)
            if existing is not None:
                if _merge_issue(existing, issue):
                    updated += 1
                else:
                    skipped += 1
                continue
            issue["created_at"] = ts
            issues.append(issue)
            existing_by_signature[signature] = issue
            added += 1
        state.setdefault("stats", {})
        state["stats"]["total_found"] = state["stats"].get("total_found", 0) + added
        save_state(state)
        return {"added": added, "updated": updated, "skipped": skipped}

def increment_scans():
    """Track number of scans run."""
    with _locked_file("state"):
        state = load_state()
        state.setdefault("stats", {})
        state["stats"]["scans_run"] = state["stats"].get("scans_run", 0) + 1
        state["last_scan"] = now_iso()
        save_state(state)

def clear_issues(*, keep_resolved: bool = True):
    """Clear all pending issues (used by rescan).

    Args:
        keep_resolved: If True (default), preserves the resolved list for
            historical reference. Set to False for a full reset.
    """
    with _locked_file("state"):
        state = load_state()
        state["issues"] = []
        if not keep_resolved:
            state["resolved"] = []
        save_state(state)


def batch_remove_issues(issue_ids: list[str], note: str = "") -> list[dict]:
    """Remove multiple issues atomically in a single state update.

    Args:
        issue_ids: List of issue IDs to resolve.
        note: Resolution note applied to all issues.

    Returns:
        List of removed issue dicts (empty if none found).
    """
    with _locked_file("state"):
        state = load_state()
        id_set = set(issue_ids)
        removed = [i for i in state.get("issues", []) if i.get("id") in id_set]
        state["issues"] = [i for i in state.get("issues", []) if i.get("id") not in id_set]

        for r in removed:
            r["resolved_at"] = now_iso()
            if note:
                r["note"] = note
            state.setdefault("resolved", []).append(r)

        state.setdefault("stats", {})
        state["stats"]["total_resolved"] = state["stats"].get("total_resolved", 0) + len(removed)
        save_state(state)
        return removed

