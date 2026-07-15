"""Shared utilities for UIdetox."""

import os
import re
import shlex
import subprocess
from datetime import datetime, timezone


_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


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


def prepare_subprocess_cmd(cmd: str) -> tuple[list[str], dict[str, str] | None]:
    """Return argv and optional env overrides for a command string.

    Supports leading shell-style env assignments such as:
    `CI=1 NODE_OPTIONS=--max-old-space-size=4096 npm test`
    without resorting to shell=True.
    """
    parts = safe_split_cmd(cmd)
    env_updates: dict[str, str] = {}
    argv: list[str] = []

    for index, part in enumerate(parts):
        if _ENV_ASSIGNMENT_RE.match(part):
            key, value = part.split("=", 1)
            env_updates[key] = value
            continue

        argv = parts[index:]
        break

    if not argv:
        argv = parts

    env = None
    if env_updates:
        env = os.environ.copy()
        env.update(env_updates)

    return argv, env


def _parse_tracked_status_line(line: str) -> tuple[str, str] | None:
    """Parse a porcelain status line into (original_path, current_path)."""
    if len(line) < 4:
        return None

    status_code = line[:2]
    path = line[3:]

    def _parse_status_path(path_fragment: str) -> str:
        try:
            parsed_path = shlex.split(path_fragment)
        except ValueError:
            parsed_path = []
        return parsed_path[0] if parsed_path else path_fragment

    try:
        parsed_path = shlex.split(path)
    except ValueError:
        parsed_path = []

    if " -> " in path and ("R" in status_code or "C" in status_code):
        if "->" in parsed_path:
            arrow_index = parsed_path.index("->")
            old_path = parsed_path[arrow_index - 1] if arrow_index > 0 else path.split(" -> ", 1)[0]
            new_path = parsed_path[arrow_index + 1] if arrow_index + 1 < len(parsed_path) else path.split(" -> ", 1)[1]
            return old_path, new_path

        old_path, new_path = path.split(" -> ", 1)
        try:
            old_parts = shlex.split(old_path)
            if old_parts:
                old_path = old_parts[0]
        except ValueError:
            pass
        try:
            new_parts = shlex.split(new_path)
            if new_parts:
                new_path = new_parts[0]
        except ValueError:
            pass
        return old_path, new_path

    if parsed_path:
        return parsed_path[0], parsed_path[0]
    return path, path


def untracked_changed_files() -> set[str]:
    """Return untracked file paths reported by git status."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            cwd=".",
            check=False,
        )
    except FileNotFoundError:
        return set()
    if status.returncode != 0:
        return set()

    untracked: set[str] = set()
    for line in status.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        path = line[3:]
        try:
            parsed_path = shlex.split(path)
        except ValueError:
            parsed_path = []
        untracked.add(parsed_path[0] if parsed_path else path)
    return untracked


def tracked_changed_entries() -> list[tuple[str, str]]:
    """Return tracked changed paths as (original_path, current_path) tuples."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            cwd=".",
            check=False,
        )
    except FileNotFoundError:
        return []
    if status.returncode != 0:
        return []

    entries: list[tuple[str, str]] = []
    for line in status.stdout.splitlines():
        parsed = _parse_tracked_status_line(line)
        if parsed:
            entries.append(parsed)
    return entries


def tracked_changed_files() -> set[str]:
    """Return tracked files with staged or unstaged changes.

    Untracked files are intentionally ignored so auto-commit guards only react
    to modifications of files already under version control.
    """
    return {current_path for _, current_path in tracked_changed_entries()}


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
