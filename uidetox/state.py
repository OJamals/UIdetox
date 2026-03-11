"""State and Config Management for UIdetox."""

import json
import os
import tempfile
from pathlib import Path

from uidetox.utils import now_iso

UIDETOX_DIR = ".uidetox"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

def get_project_root() -> Path:
    """Finds the base path containing .uidetox or defaults to current working directory."""
    cwd = Path.cwd()
    current = cwd
    while current != current.parent:
        if (current / UIDETOX_DIR).exists():
            return current
        current = current.parent
    return cwd

def get_uidetox_dir() -> Path:
    return get_project_root() / UIDETOX_DIR

def ensure_uidetox_dir():
    d = get_uidetox_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

def _now_iso() -> str:
    return now_iso()

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
    target = d / CONFIG_FILE
    fd, tmp_path = tempfile.mkstemp(dir=d, prefix="config_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)

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
    target = d / STATE_FILE
    fd, tmp_path = tempfile.mkstemp(dir=d, prefix="state_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)

def get_issue(issue_id: str) -> dict | None:
    state = load_state()
    for item in state.get("issues", []):
        if item.get("id") == issue_id:
            return item
    return None

def remove_issue(issue_id: str, note: str = "") -> bool:
    state = load_state()
    original_len = len(state.get("issues", []))
    removed = [i for i in state.get("issues", []) if i.get("id") == issue_id]
    state["issues"] = [i for i in state.get("issues", []) if i.get("id") != issue_id]
    if len(state["issues"]) < original_len:
        # Track resolved issues
        for r in removed:
            r["resolved_at"] = _now_iso()
            if note:
                r["note"] = note
            state.setdefault("resolved", []).append(r)
        state.setdefault("stats", {})
        state["stats"]["total_resolved"] = state["stats"].get("total_resolved", 0) + len(removed)
        save_state(state)
        return True
    return False

def add_issue(issue: dict):
    state = load_state()
    issues = state.setdefault("issues", [])
    issue["created_at"] = _now_iso()
    issues.append(issue)
    state.setdefault("stats", {})
    state["stats"]["total_found"] = state["stats"].get("total_found", 0) + 1
    save_state(state)

def increment_scans():
    """Track number of scans run."""
    state = load_state()
    state.setdefault("stats", {})
    state["stats"]["scans_run"] = state["stats"].get("scans_run", 0) + 1
    state["last_scan"] = _now_iso()
    save_state(state)

def clear_issues():
    """Clear all pending issues (used by rescan)."""
    state = load_state()
    state["issues"] = []
    save_state(state)


def batch_remove_issues(issue_ids: list[str], note: str = "") -> list[dict]:
    """Remove multiple issues atomically in a single state update.

    Args:
        issue_ids: List of issue IDs to resolve.
        note: Resolution note applied to all issues.

    Returns:
        List of removed issue dicts (empty if none found).
    """
    state = load_state()
    id_set = set(issue_ids)
    removed = [i for i in state.get("issues", []) if i.get("id") in id_set]
    state["issues"] = [i for i in state.get("issues", []) if i.get("id") not in id_set]

    for r in removed:
        r["resolved_at"] = _now_iso()
        if note:
            r["note"] = note
        state.setdefault("resolved", []).append(r)

    state.setdefault("stats", {})
    state["stats"]["total_resolved"] = state["stats"].get("total_resolved", 0) + len(removed)
    save_state(state)
    return removed

