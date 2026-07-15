"""State and Config Management for UIdetox."""

import contextlib
import json
import os
import tempfile
from pathlib import Path

from uidetox.utils import now_iso

try:
    import fcntl as _fcntl
    _HAS_FLOCK = True
except ImportError:
    _HAS_FLOCK = False  # Windows — locking is best-effort only


@contextlib.contextmanager
def _state_lock():
    """Advisory POSIX file lock to serialize concurrent state mutations.

    On platforms without fcntl (Windows), this is a no-op — concurrent
    writes are still possible but won't crash.
    """
    if not _HAS_FLOCK:
        yield
        return
    lock_path = get_uidetox_dir() / "state.lock"
    ensure_uidetox_dir()
    with open(lock_path, "a") as lf:
        try:
            _fcntl.flock(lf.fileno(), _fcntl.LOCK_EX)
            yield
        finally:
            _fcntl.flock(lf.fileno(), _fcntl.LOCK_UN)

UIDETOX_DIR = ".uidetox"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
_PROJECT_ROOT_MARKERS = (
    "pyproject.toml",
    "package.json",
    "pnpm-workspace.yaml",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
)


def _find_ancestor_with_markers(start: Path, markers: tuple[str, ...]) -> Path | None:
    """Return the nearest ancestor containing any marker file or directory."""
    current = start
    while True:
        if any((current / marker).exists() for marker in markers):
            return current
        if current == current.parent:
            return None
        current = current.parent

def get_project_root() -> Path:
    """Find the project root from the current working directory.

    Preference order:
    1. Existing `.uidetox` ancestor (persisted project state already established)
    2. Nearest git/project root marker ancestor for cold starts from subdirectories
    3. Current working directory as a last resort
    """
    cwd = Path.cwd().resolve()

    uidetox_root = _find_ancestor_with_markers(cwd, (UIDETOX_DIR,))
    if uidetox_root is not None:
        return uidetox_root

    git_root = _find_ancestor_with_markers(cwd, (".git",))
    if git_root is not None:
        return git_root

    project_root = _find_ancestor_with_markers(cwd, _PROJECT_ROOT_MARKERS)
    if project_root is not None:
        return project_root

    return cwd

def get_uidetox_dir() -> Path:
    return get_project_root() / UIDETOX_DIR

def ensure_uidetox_dir():
    d = get_uidetox_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

def _now_iso() -> str:
    return now_iso()


def _is_numeric_config_value(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalize_counter(value: object) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return 0


def _normalize_bounded_score(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, min(100, int(value)))
    return None


def _normalize_issue_collection(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [issue for issue in value if isinstance(issue, dict)]


def _normalize_subjective_history_entry(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None

    score = _normalize_bounded_score(entry.get("score"))
    if score is None:
        return None

    normalized = dict(entry)
    timestamp = entry.get("timestamp")
    normalized["score"] = score
    normalized["timestamp"] = timestamp if isinstance(timestamp, str) else ""
    return normalized


def _normalize_subjective_state(value: object) -> dict:
    if not isinstance(value, dict):
        return {}

    normalized = dict(value)

    score = _normalize_bounded_score(value.get("score"))
    if score is None:
        normalized.pop("score", None)
    else:
        normalized["score"] = score

    history = value.get("history")
    if not isinstance(history, list):
        normalized["history"] = []
    else:
        normalized_history: list[dict] = []
        for entry in history:
            clean_entry = _normalize_subjective_history_entry(entry)
            if clean_entry is not None:
                normalized_history.append(clean_entry)
        normalized["history"] = normalized_history

    return normalized


def _normalize_tool_entry(tool: object) -> dict | None:
    if not isinstance(tool, dict):
        return None

    name = tool.get("name")
    run_cmd = tool.get("run_cmd")
    if not isinstance(name, str) or not isinstance(run_cmd, str):
        return None

    normalized = {"name": name, "run_cmd": run_cmd}
    config_file = tool.get("config_file")
    if isinstance(config_file, str):
        normalized["config_file"] = config_file
    fix_cmd = tool.get("fix_cmd")
    if isinstance(fix_cmd, str):
        normalized["fix_cmd"] = fix_cmd
    return normalized


def _normalize_tool_collection(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []

    normalized: list[dict] = []
    for entry in value:
        clean_entry = _normalize_tool_entry(entry)
        if clean_entry is not None:
            normalized.append(clean_entry)
    return normalized


def _normalize_tooling_config(tooling: object) -> dict:
    if not isinstance(tooling, dict):
        return {}

    normalized = dict(tooling)
    for key in ("typescript", "linter", "formatter"):
        if key in normalized:
            normalized[key] = _normalize_tool_entry(normalized[key])

    for key in ("frontend", "backend", "database", "api"):
        if key in normalized:
            normalized[key] = _normalize_tool_collection(normalized[key])

    if "package_manager" in normalized and not isinstance(normalized["package_manager"], str):
        normalized["package_manager"] = None

    return normalized

def load_config() -> dict:
    config_path = get_uidetox_dir() / CONFIG_FILE
    default_config = {
        "DESIGN_VARIANCE": 8,
        "MOTION_INTENSITY": 6,
        "VISUAL_DENSITY": 4
    }
    if not config_path.exists():
        return default_config.copy()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return default_config.copy()

    if not isinstance(data, dict):
        return default_config.copy()

    # Ensure numeric dials have correct types to prevent TypeError in comparisons.
    for key, default in default_config.items():
        if not _is_numeric_config_value(data.get(key)):
            data[key] = default

    if not _is_numeric_config_value(data.get("target_score")):
        data["target_score"] = 95

    if "tooling" in data:
        data["tooling"] = _normalize_tooling_config(data["tooling"])
    if "ignore_patterns" in data and not isinstance(data["ignore_patterns"], list):
        data["ignore_patterns"] = []
    elif "ignore_patterns" in data:
        data["ignore_patterns"] = [pattern for pattern in data["ignore_patterns"] if isinstance(pattern, str)]
    if "exclude" in data and not isinstance(data["exclude"], list):
        data["exclude"] = []
    elif "exclude" in data:
        data["exclude"] = [path for path in data["exclude"] if isinstance(path, str)]
    if "zone_overrides" in data and not isinstance(data["zone_overrides"], dict):
        data["zone_overrides"] = {}
    if "auto_commit" in data and not isinstance(data["auto_commit"], bool):
        data["auto_commit"] = False
    if "dev_server" in data and not isinstance(data["dev_server"], str):
        data.pop("dev_server", None)

    return data

def _save_json(data: dict, filename: str, temp_prefix: str) -> None:
    d = ensure_uidetox_dir()
    target = d / filename
    fd, tmp_path = tempfile.mkstemp(dir=d, prefix=temp_prefix, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target)


def save_config(config: dict):
    _save_json(config, CONFIG_FILE, "config_")


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
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        data = _default_state()

    # Validate expected types — a corrupted or hand-edited state.json can contain
    # wrong types for critical fields, causing cryptic AttributeError crashes downstream.
    if not isinstance(data, dict):
        data = _default_state()
    else:
        data["issues"] = _normalize_issue_collection(data.get("issues"))
        data["resolved"] = _normalize_issue_collection(data.get("resolved"))
        data["diff_baseline"] = _normalize_issue_collection(data.get("diff_baseline"))
        data["subjective"] = _normalize_subjective_state(data.get("subjective"))

        stats = data.get("stats")
        if not isinstance(stats, dict):
            stats = {"total_found": 0, "total_resolved": 0, "scans_run": 0}
        else:
            stats = dict(stats)
            stats["total_found"] = _normalize_counter(stats.get("total_found"))
            stats["total_resolved"] = _normalize_counter(stats.get("total_resolved"))
            stats["scans_run"] = _normalize_counter(stats.get("scans_run"))
        data["stats"] = stats

    # Ensure new fields exist for backwards compat
    data.setdefault("diff_baseline", [])
    data.setdefault("resolved", [])
    data.setdefault("subjective", {})
    data.setdefault("stats", {"total_found": 0, "total_resolved": 0, "scans_run": 0})
    return data

def _default_state() -> dict:
    return {
        "last_scan": None,
        "diff_baseline": [],
        "issues": [],
        "resolved": [],
        "subjective": {},
        "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
    }

def save_state(state: dict):
    _save_json(state, STATE_FILE, "state_")

def get_issue(issue_id: str) -> dict | None:
    state = load_state()
    for item in state.get("issues", []):
        if item.get("id") == issue_id:
            return item
    return None

def remove_issue(issue_id: str, note: str = "") -> bool:
    with _state_lock():
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


def issue_dedup_key(issue: dict) -> str:
    """Return a stable key for detecting duplicate pending issues."""
    return "::".join(
        str(issue.get(field, "")).strip()
        for field in ("file", "issue", "command")
    )


def add_issue(issue: dict):
    with _state_lock():
        state = load_state()
        issues = state.setdefault("issues", [])
        new_key = issue_dedup_key(issue)
        if any(issue_dedup_key(existing) == new_key for existing in issues):
            return False
        issue["created_at"] = _now_iso()
        issues.append(issue)
        state.setdefault("stats", {})
        state["stats"]["total_found"] = state["stats"].get("total_found", 0) + 1
        save_state(state)
        return True

def increment_scans():
    """Track number of scans run."""
    with _state_lock():
        state = load_state()
        state.setdefault("stats", {})
        state["stats"]["scans_run"] = state["stats"].get("scans_run", 0) + 1
        state["last_scan"] = _now_iso()
        save_state(state)

def clear_issues():
    """Clear all pending issues (used by rescan)."""
    with _state_lock():
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
    with _state_lock():
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
