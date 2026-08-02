"""State and Config Management for UIdetox."""

import contextlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

from uidetox.findings import (
    FINDING_SCHEMA_VERSION,
    Finding,
    VerificationResult,
    coerce_finding,
)
from uidetox.persistence import atomic_replace_text
from uidetox.prompt_safety import sanitize_untrusted_data
from uidetox.utils import _normalize_dict_entries, now_iso

try:
    import fcntl as _locking
except ImportError:
    import msvcrt as _locking


@contextlib.contextmanager
def _persistence_lock():
    """Serialize project persistence mutations across processes."""
    lock_path = ensure_uidetox_dir() / "state.lock"
    with open(lock_path, "a+b") as lock_file:
        lock_file.seek(0)
        if os.name == "nt":
            _locking.locking(lock_file.fileno(), _locking.LK_LOCK, 1)
        else:
            _locking.flock(lock_file.fileno(), _locking.LOCK_EX)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                _locking.locking(lock_file.fileno(), _locking.LK_UNLCK, 1)
            else:
                _locking.flock(lock_file.fileno(), _locking.LOCK_UN)


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
    1. A git root nested below unrelated ancestor state
    2. A current working directory with an explicit project marker
    3. Existing `.uidetox` ancestor (persisted project state already established)
    4. Nearest git/project root marker ancestor for cold starts from subdirectories
    5. Current working directory as a last resort
    """
    cwd = Path.cwd().resolve()
    uidetox_root = _find_ancestor_with_markers(cwd, (UIDETOX_DIR,))
    git_root = _find_ancestor_with_markers(cwd, (".git",))
    if (
        uidetox_root is not None
        and git_root is not None
        and uidetox_root in git_root.parents
    ):
        return git_root
    if uidetox_root != cwd and any(
        (cwd / marker).exists() for marker in _PROJECT_ROOT_MARKERS
    ):
        return cwd
    if uidetox_root is not None:
        return uidetox_root
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


def _load_json_object(input_path: Path, artifact: str) -> dict:
    try:
        value = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{artifact} not found: {input_path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{artifact} is unreadable: {input_path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{artifact} must contain a JSON object: {input_path}")
    return value


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
    return [
        coerce_finding(issue).to_dict()
        for issue in value
        if isinstance(issue, (Finding, dict))
    ]


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


def _normalize_tooling_config(tooling: object) -> dict:
    if not isinstance(tooling, dict):
        return {}
    normalized = dict(tooling)
    for key in ("typescript", "linter", "formatter"):
        if key in normalized:
            normalized[key] = _normalize_tool_entry(normalized[key])
    for key in ("frontend", "backend", "database", "api"):
        if key in normalized:
            normalized[key] = _normalize_dict_entries(
                normalized[key], _normalize_tool_entry
            )
    if "package_manager" in normalized and not isinstance(
        normalized["package_manager"], str
    ):
        normalized["package_manager"] = None
    return normalized


def load_config(root: str | Path | None = None) -> dict:
    config_path = (
        Path(root).resolve() / UIDETOX_DIR if root is not None else get_uidetox_dir()
    ) / CONFIG_FILE
    default_config = {"DESIGN_VARIANCE": 8, "MOTION_INTENSITY": 6, "VISUAL_DENSITY": 4}
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
        data["ignore_patterns"] = [
            pattern for pattern in data["ignore_patterns"] if isinstance(pattern, str)
        ]
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
    content = json.dumps(data, indent=2)
    d = ensure_uidetox_dir()
    atomic_replace_text(d / filename, content, temp_prefix=temp_prefix)


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
        data["schema_version"] = FINDING_SCHEMA_VERSION
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
    data.setdefault("schema_version", FINDING_SCHEMA_VERSION)
    data.setdefault("current_snapshot", {"qualified_coverage": 0.0})
    data.setdefault("overrides", [])
    return sanitize_untrusted_data(data)


def _default_state() -> dict:
    return {
        "schema_version": FINDING_SCHEMA_VERSION,
        "last_scan": None,
        "diff_baseline": [],
        "issues": [],
        "resolved": [],
        "subjective": {},
        "current_snapshot": {"qualified_coverage": 0.0},
        "overrides": [],
        "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
    }


def save_state(state: dict):
    canonical = dict(state)
    canonical["schema_version"] = FINDING_SCHEMA_VERSION
    for key in ("issues", "resolved", "diff_baseline"):
        canonical[key] = _normalize_issue_collection(canonical.get(key))
    _save_json(sanitize_untrusted_data(canonical), STATE_FILE, "state_")


def get_issue(issue_id: str) -> dict | None:
    state = load_state()
    for item in state.get("issues", []):
        if item.get("id") == issue_id:
            return item
    return None


def remove_issue(
    issue_id: str,
    note: str = "",
    *,
    verification: VerificationResult | None = None,
) -> bool:
    return bool(
        verification
        and batch_remove_issues(
            [issue_id], note=note, verifications={issue_id: verification}
        )
    )


def issue_dedup_key(issue: dict) -> str:
    """Return a stable key for detecting duplicate pending issues."""
    return coerce_finding(issue).fingerprint


def add_issues(
    issues: Iterable[Finding | dict], *, qualified_complete: bool | None = None
) -> int:
    """Add unique pending issues in one locked persistence transaction."""
    with _persistence_lock():
        state = load_state()
        pending = state.setdefault("issues", [])
        dedup_keys = {issue_dedup_key(existing) for existing in pending}
        accepted_count = 0
        for issue in issues:
            finding = coerce_finding(issue)
            new_key = finding.fingerprint
            if new_key in dedup_keys:
                continue
            created_at = now_iso()
            if isinstance(issue, dict):
                issue["created_at"] = created_at
            payload = finding.to_dict()
            payload["created_at"] = created_at
            pending.append(payload)
            dedup_keys.add(new_key)
            accepted_count += 1
        if qualified_complete is not None:
            state["current_snapshot"] = {
                "qualified_coverage": 1.0 if qualified_complete else 0.0,
                "scanned_at": now_iso(),
            }
        if accepted_count == 0 and qualified_complete is None:
            return 0
        state.setdefault("stats", {})
        state["stats"]["total_found"] = (
            state["stats"].get("total_found", 0) + accepted_count
        )
        save_state(state)
        return accepted_count


def add_issue(issue: Finding | dict) -> bool:
    return add_issues((issue,)) == 1


def increment_scans():
    """Track number of scans run."""
    with _persistence_lock():
        state = load_state()
        state.setdefault("stats", {})
        state["stats"]["scans_run"] = state["stats"].get("scans_run", 0) + 1
        state["last_scan"] = now_iso()
        save_state(state)


def clear_issues():
    """Clear all pending issues (used by rescan)."""
    with _persistence_lock():
        state = load_state()
        state["issues"] = []
        save_state(state)


def batch_remove_issues(
    issue_ids: list[str],
    note: str = "",
    *,
    verifications: dict[str, VerificationResult] | None = None,
) -> list[dict]:
    """Remove multiple issues atomically in a single state update.
    Args:
        issue_ids: List of issue IDs to resolve.
        note: Resolution note applied to all issues.
    Returns:
        List of removed issue dicts (empty if none found).
    """
    verifications = verifications or {}
    if any(
        issue_id not in verifications
        or verifications[issue_id].outcome != "absent"
        or not verifications[issue_id].evidence_hash
        for issue_id in issue_ids
    ):
        return []
    with _persistence_lock():
        state = load_state()
        id_set = set(issue_ids)
        removed = [i for i in state.get("issues", []) if i.get("id") in id_set]
        if len(removed) != len(id_set):
            return []
        state["issues"] = [
            i for i in state.get("issues", []) if i.get("id") not in id_set
        ]
        for r in removed:
            verification = verifications[r["id"]]
            r["status"] = "verified_resolved"
            r["last_verification"] = verification.to_dict()
            r["resolved_at"] = now_iso()
            if note:
                r["note"] = note
            state.setdefault("resolved", []).append(r)
        state.setdefault("stats", {})
        state["stats"]["total_resolved"] = state["stats"].get(
            "total_resolved", 0
        ) + len(removed)
        save_state(state)
        return removed


def record_verification_override(
    issue_ids: list[str],
    *,
    actor: str,
    reason: str,
    results: dict[str, VerificationResult],
) -> None:
    """Audit an explicit verifier override without resolving the findings."""
    if not actor.strip() or not reason.strip():
        raise ValueError("Verifier overrides require both actor and reason.")
    with _persistence_lock():
        state = load_state()
        ids = set(issue_ids)
        for issue in state.get("issues", []):
            if issue.get("id") in ids:
                issue["status"] = "overridden"
                result = results.get(issue["id"])
                issue["last_verification"] = result.to_dict() if result else None
        state.setdefault("overrides", []).append(
            {
                "issue_ids": list(issue_ids),
                "actor": actor.strip(),
                "reason": reason.strip(),
                "timestamp": now_iso(),
                "results": {
                    issue_id: result.to_dict() for issue_id, result in results.items()
                },
            }
        )
        save_state(state)
