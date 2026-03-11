"""Run history: timestamped snapshots of each scan/rescan cycle."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uidetox.state import get_uidetox_dir, ensure_uidetox_dir, load_state


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
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": trigger,
        "design_score": _compute_score(state),
        "pending_issues": len(state.get("issues", [])),
        "resolved_issues": len(state.get("resolved", [])),
        "total_found": state.get("stats", {}).get("total_found", 0),
        "scans_run": state.get("stats", {}).get("scans_run", 0),
        "issues": state.get("issues", []),
        "resolved": state.get("resolved", []),
    }
    path = _history_dir() / f"run_{stamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    return path


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


def _compute_score(state: dict) -> int:
    """Compute design score using the same weighted slop-ratio as status.py."""
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])

    tier_weights = {"T1": 1, "T2": 3, "T3": 5, "T4": 10}
    current_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in issues)
    resolved_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in resolved)
    total_slop = current_slop + resolved_slop

    if total_slop == 0:
        objective_score = 100
    else:
        objective_score = int(100 - ((current_slop / total_slop) * 100))
        objective_score = max(0, min(100, objective_score))
        
    subjective_score = state.get("subjective", {}).get("score")
    if subjective_score is not None:
        return int(objective_score * 0.6 + subjective_score * 0.4)
    return objective_score
