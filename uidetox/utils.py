"""Shared utilities for UIdetox."""

import shlex
from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def safe_split_cmd(cmd: str) -> list[str]:
    """Split a shell command string safely, handling paths with spaces.

    Falls back to simple split if shlex parsing fails (e.g. Windows paths).
    """
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def compute_design_score(state: dict) -> dict:
    """Compute the blended design score from state.

    Returns a dict with:
      - objective_score: int (0-100) from static analysis slop ratio
      - subjective_score: int | None from LLM review
      - blended_score: int (0-100) final blended score
      - current_slop: weighted slop points remaining
      - resolved_slop: weighted slop points resolved
      - total_slop: total weighted slop points
    """
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    stats = state.get("stats", {})
    scans_run = stats.get("scans_run", 0)

    tier_weights = {"T1": 1, "T2": 3, "T3": 5, "T4": 10}

    current_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in issues)
    resolved_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in resolved)
    total_slop = current_slop + resolved_slop

    if scans_run == 0 and total_slop == 0:
        objective_score = 50  # Unknown quality — haven't scanned yet
    elif total_slop == 0:
        objective_score = 100
    else:
        objective_score = int(100 - ((current_slop / total_slop) * 100))
        objective_score = max(0, min(100, objective_score))

    subjective_score = state.get("subjective", {}).get("score")

    if subjective_score is not None:
        blended = int(objective_score * 0.6 + subjective_score * 0.4)
    else:
        blended = objective_score

    return {
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "blended_score": blended,
        "current_slop": current_slop,
        "resolved_slop": resolved_slop,
        "total_slop": total_slop,
    }
