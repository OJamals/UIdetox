"""Run history: timestamped snapshots of each scan/rescan cycle."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .state import get_uidetox_dir, ensure_uidetox_dir, load_state
from .utils import compute_design_score


def _history_dir() -> Path:
    d = get_uidetox_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def save_run_snapshot(*, trigger: str = "scan") -> Path:
    """Save a timestamped JSON snapshot of the current state.

    Args:
        trigger: What caused this snapshot (scan, rescan, loop, manual).

    Returns:
        Path to the saved snapshot file.
    """
    state = load_state()
    stamp = _stamp()
    scores = compute_design_score(state)
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": trigger,
        "design_score": scores["blended_score"],
        "objective_score": scores["objective_score"],
        "subjective_score": scores["subjective_score"],
        "pending_issues": len(state.get("issues", [])),
        "resolved_issues": len(state.get("resolved", [])),
        "total_found": state.get("stats", {}).get("total_found", 0),
        "scans_run": state.get("stats", {}).get("scans_run", 0),
        "issues": state.get("issues", []),
        "resolved": state.get("resolved", []),
    }
    target = _history_dir() / f"run_{stamp}.json"
    fd, tmp_path = tempfile.mkstemp(dir=_history_dir(), prefix="run_", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)
    return target


def load_run_history() -> list[dict]:
    """Return all run snapshots sorted by timestamp (oldest first)."""
    history_dir = _history_dir()
    runs = []
    for p in sorted(history_dir.glob("run_*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_file"] = str(p.name)
            runs.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return runs


def compare_runs() -> list[dict]:
    """Return a simplified list of (timestamp, score, pending, resolved) for progression tracking."""
    runs = load_run_history()
    return [
        {
            "timestamp": r.get("timestamp", ""),
            "trigger": r.get("trigger", "?"),
            "score": r.get("design_score", 0),
            "pending": r.get("pending_issues", 0),
            "resolved": r.get("resolved_issues", 0),
        }
        for r in runs
    ]
