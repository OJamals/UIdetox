"""Run history: timestamped snapshots of each scan/rescan cycle."""

import json
from pathlib import Path
from .state import get_uidetox_dir, ensure_uidetox_dir, load_state, _atomic_write_json
from .utils import compute_design_score, now_iso, now_iso_filename


def _history_dir() -> Path:
    d = get_uidetox_dir() / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tier_breakdown(items: list[dict]) -> dict[str, int]:
    """Return a compact tier count summary for a list of issues."""
    tiers = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for item in items:
        tier = item.get("tier", "T4")
        if tier in tiers:
            tiers[tier] += 1
    return tiers


def save_run_snapshot(*, trigger: str = "scan") -> Path:
    """Save a timestamped JSON snapshot of the current state.

    Args:
        trigger: What caused this snapshot (scan, rescan, loop, manual).

    Returns:
        Path to the saved snapshot file.
    """
    state = load_state()
    stamp = now_iso_filename()
    scores = compute_design_score(state)
    pending = state.get("issues", [])
    resolved = state.get("resolved", [])
    snapshot = {
        "timestamp": now_iso(),
        "trigger": trigger,
        "design_score": scores["blended_score"],
        "objective_score": scores["objective_score"],
        "subjective_score": scores["subjective_score"],
        "pending_issues": len(pending),
        "resolved_issues": len(resolved),
        "total_found": state.get("stats", {}).get("total_found", 0),
        "scans_run": state.get("stats", {}).get("scans_run", 0),
        # Compact summaries instead of full issue/resolution lists to keep
        # snapshots lightweight while preserving useful trend information.
        "pending_tiers": _tier_breakdown(pending),
        "resolved_tiers": _tier_breakdown(resolved),
    }
    target = _history_dir() / f"run_{stamp}.json"
    _atomic_write_json(target, snapshot, dir=_history_dir())

    # Rotate history to prevent unbounded growth — keep at most 100 snapshots
    _rotate_history(max_snapshots=100)

    return target


def _rotate_history(max_snapshots: int = 100) -> None:
    """Delete oldest snapshots when the count exceeds *max_snapshots*."""
    history_dir = _history_dir()
    snapshots = sorted(history_dir.glob("run_*.json"))
    if len(snapshots) <= max_snapshots:
        return
    for old in snapshots[: len(snapshots) - max_snapshots]:
        try:
            old.unlink()
        except OSError:
            pass


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
            "trigger": r.get("trigger", "unknown"),
            "score": r.get("design_score") or 0,
            "pending": r.get("pending_issues", 0),
            "resolved": r.get("resolved_issues", 0),
        }
        for r in runs
    ]
