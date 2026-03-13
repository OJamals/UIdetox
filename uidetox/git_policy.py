"""Risk-aware auto-commit policy.

Enforces a safe Git commit strategy:
    1. Stage only tracked, touched files (never ``git add -A``)
    2. Run Git hooks by default (no ``--no-verify``)
    3. Abort commit if working tree has unrelated modifications
    4. Verify only expected files are staged before committing

The policy is configurable via ``.uidetox/config.json``:
    {
        "auto_commit": true,
        "commit_policy": {
            "run_hooks": true,
            "abort_on_unrelated": true,
            "max_unrelated_files": 3,
            "allow_untracked": false
        }
    }
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommitPolicy:
    """Configuration for risk-aware auto-commit."""
    run_hooks: bool = True
    abort_on_unrelated: bool = True
    max_unrelated_files: int = 3
    allow_untracked: bool = False

    @classmethod
    def from_config(cls, config: dict) -> "CommitPolicy":
        policy = config.get("commit_policy", {})
        return cls(
            run_hooks=policy.get("run_hooks", True),
            abort_on_unrelated=policy.get("abort_on_unrelated", True),
            max_unrelated_files=policy.get("max_unrelated_files", 3),
            allow_untracked=policy.get("allow_untracked", False),
        )


@dataclass
class CommitResult:
    """Result of a commit attempt."""
    success: bool
    message: str
    staged_files: list[str] = field(default_factory=list)
    aborted_reason: str = ""
    unrelated_files: list[str] = field(default_factory=list)


def _git_run(args: list[str], cwd: str | None = None, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a git command safely."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )


def get_tracked_modified_files(cwd: str | None = None) -> list[str]:
    """Get list of tracked files that have been modified in the working tree."""
    try:
        result = _git_run(["diff", "--name-only", "--diff-filter=ACMR"], cwd=cwd)
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_staged_files(cwd: str | None = None) -> list[str]:
    """Get list of currently staged files."""
    try:
        result = _git_run(["diff", "--cached", "--name-only"], cwd=cwd)
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_untracked_files(cwd: str | None = None) -> list[str]:
    """Get list of untracked files."""
    try:
        result = _git_run(["ls-files", "--others", "--exclude-standard"], cwd=cwd)
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def git_changed_paths(project_root: str) -> set[str] | None:
    """Return modified/staged/untracked paths via ``git status --porcelain``.

    Returns ``None`` when git metadata is unavailable in this environment.
    This is the canonical implementation — do **not** duplicate elsewhere.
    """
    changed: set[str] = set()
    try:
        status = _git_run(["status", "--porcelain"], cwd=project_root)
        if status.returncode != 0:
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    for line in status.stdout.splitlines():
        if not line or len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        path = path.lstrip("./")
        if path:
            changed.add(path.replace("\\", "/"))
    return changed


def classify_modifications(
    touched_files: list[str],
    cwd: str | None = None,
) -> tuple[list[str], list[str]]:
    """Classify working tree modifications as related or unrelated.

    Args:
        touched_files: Files that were intentionally modified (issue files,
            .uidetox state, etc.)

    Returns:
        (related, unrelated) — related files are the touched files that
        are actually modified, unrelated are other modified files.
    """
    all_modified = get_tracked_modified_files(cwd=cwd)
    already_staged = get_staged_files(cwd=cwd)
    all_changed = set(all_modified) | set(already_staged)

    touched_set = set(touched_files)

    # .uidetox/ files are always considered related
    related = [
        f for f in all_changed
        if f in touched_set or f.startswith(".uidetox/") or f.startswith(".uidetox\\")
    ]
    unrelated = [
        f for f in all_changed
        if f not in touched_set and not f.startswith(".uidetox/") and not f.startswith(".uidetox\\")
    ]

    return related, unrelated


def safe_stage(
    files: list[str],
    policy: CommitPolicy,
    cwd: str | None = None,
) -> tuple[list[str], str]:
    """Stage only the specified tracked files.

    Returns (staged_files, error_message). Error is empty on success.
    """
    if not files:
        return [], "No files to stage"

    staged: list[str] = []
    for f in files:
        # `git add --` handles both existing and deleted files correctly,
        # so we always attempt the same command regardless of file state.
        try:
            result = _git_run(["add", "--", f], cwd=cwd)
            if result.returncode == 0:
                staged.append(f)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return staged, ""


def safe_commit(
    *,
    touched_files: list[str],
    message: str,
    policy: CommitPolicy | None = None,
    cwd: str | None = None,
) -> CommitResult:
    """Execute a risk-aware auto-commit.

    1. Classify modifications as related vs unrelated
    2. Abort if too many unrelated modifications
    3. Stage only touched files
    4. Run hooks by default
    5. Commit with message
    """
    if policy is None:
        policy = CommitPolicy()

    # Step 1: Classify modifications
    related, unrelated = classify_modifications(touched_files, cwd=cwd)

    # Step 2: Check for unrelated modifications
    if policy.abort_on_unrelated and len(unrelated) > policy.max_unrelated_files:
        return CommitResult(
            success=False,
            message="",
            aborted_reason=f"Working tree has {len(unrelated)} unrelated modifications "
                          f"(max: {policy.max_unrelated_files}). "
                          f"Unrelated files: {', '.join(unrelated[:5])}. "
                          f"Commit manually or increase max_unrelated_files in config.",
            unrelated_files=unrelated,
        )

    # Step 3: Stage only touched files + .uidetox state
    files_to_stage = list(set(touched_files) | {".uidetox/state.json"})
    staged, stage_err = safe_stage(files_to_stage, policy, cwd=cwd)

    if not staged:
        return CommitResult(
            success=False,
            message="",
            aborted_reason=stage_err or "No files were staged",
        )

    # Step 4: Build commit command
    commit_args = ["commit", "-m", message]
    if not policy.run_hooks:
        commit_args.append("--no-verify")

    # Step 5: Execute commit
    try:
        result = _git_run(commit_args, cwd=cwd, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Hook failure is a legitimate abort
            if "hook" in stderr.lower():
                return CommitResult(
                    success=False,
                    message="",
                    aborted_reason=f"Git hook failed: {stderr[:200]}",
                    staged_files=staged,
                )
            # "nothing to commit" is not an error
            if "nothing to commit" in stderr.lower() or "nothing to commit" in result.stdout.lower():
                return CommitResult(
                    success=True,
                    message="Nothing to commit (working tree clean)",
                    staged_files=staged,
                )
            return CommitResult(
                success=False,
                message="",
                aborted_reason=f"Git commit failed: {stderr[:200]}",
                staged_files=staged,
            )

        return CommitResult(
            success=True,
            message=message,
            staged_files=staged,
            unrelated_files=unrelated,
        )
    except subprocess.TimeoutExpired:
        return CommitResult(
            success=False,
            message="",
            aborted_reason="Git commit timed out (120s)",
            staged_files=staged,
        )
    except FileNotFoundError:
        return CommitResult(
            success=False,
            message="",
            aborted_reason="git command not found",
        )
