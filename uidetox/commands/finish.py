import subprocess
import sys
import tempfile
from pathlib import Path

from uidetox.findings import (
    EligibilityContext,
    current_evidence_hashes,
    current_verification_fresh,
    evaluate_eligibility,
)
from uidetox.state import load_config, load_state
from uidetox.visual_semantics import project_visual_evidence_status

_FINISH_COMMIT_MESSAGE = (
    "[UIdetox] Detoxing complete: Resolved issues and improved Design Score."
)


def _detect_main_branch() -> str:
    """Detect the primary branch (main, master, develop) reliably.

    Instead of using 'git checkout -' which goes to the last-visited branch
    (unreliable if user has switched branches), we detect the actual default branch.
    """
    # Try remote HEAD (most reliable)
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fall back to checking common branch names
    try:
        result = subprocess.run(
            ["git", "branch", "--list"],
            capture_output=True,
            text=True,
            check=True,
        )
        branches = [b.strip().lstrip("*+ ") for b in result.stdout.splitlines()]
        for candidate in ("main", "master", "develop", "dev"):
            if candidate in branches:
                return candidate
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return "main"  # Last-resort default


def _workspace_dirty() -> bool:
    try:
        return bool(subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return True


def _worktree_for_branch(repository: Path, branch_ref: str) -> Path | None:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    worktree: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            worktree = Path(line.removeprefix("worktree ")).resolve()
        elif line == f"branch {branch_ref}" and worktree is not None:
            return worktree
        elif not line:
            worktree = None
    return None


def _restore_target_ref(
    repository: Path,
    target_ref: str,
    target_head: str,
    candidate: str,
) -> bool:
    """Restore a published target only if it still points at our candidate."""
    try:
        subprocess.run(
            ["git", "update-ref", target_ref, target_head, candidate],
            cwd=repository,
            check=True,
        )
        restored_head = subprocess.run(
            ["git", "rev-parse", target_ref],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return restored_head == target_head


def _worktree_index_matches_commit(worktree: Path, commit: str) -> bool:
    """Return whether a linked worktree's index matches a specific commit."""
    command = ["git", "diff", "--cached", "--quiet", commit, "--"]
    result = subprocess.run(
        command,
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result.returncode == 0


def _remove_temporary_worktree(
    repository: Path,
    worktree: Path,
    *,
    added: bool,
) -> Exception | None:
    if not added:
        try:
            worktree.rmdir()
        except FileNotFoundError:
            return None
        except OSError as exc:
            return exc
        return None

    try:
        subprocess.run(
            ["git", "worktree", "remove", str(worktree)],
            cwd=repository,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        print(f"⚠️  Temporary worktree cleanup failed: {worktree}")
        print("▶️  Retrying cleanup for that command-owned worktree with --force...")
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=repository,
                check=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"❌ Manual cleanup required for temporary worktree: {worktree}")
            return exc
    return None


def _prepare_squash_candidate(
    repository: Path,
    session_head: str,
    target_head: str,
) -> str:
    temporary_worktree = Path(
        tempfile.mkdtemp(prefix="uidetox-finish-")
    ).resolve()
    worktree_added = False
    candidate: str | None = None
    operation_error: Exception | None = None

    try:
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(temporary_worktree),
                target_head,
            ],
            cwd=repository,
            check=True,
        )
        worktree_added = True

        print("▶️  Squashing changes in isolated worktree...")
        subprocess.run(
            ["git", "merge", "--squash", session_head],
            cwd=temporary_worktree,
            check=True,
        )

        print("▶️  Committing aesthetic fixes in isolated worktree...")
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                _FINISH_COMMIT_MESSAGE,
                "--no-verify",
            ],
            cwd=temporary_worktree,
            check=True,
        )
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temporary_worktree,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError) as exc:
        operation_error = exc
    finally:
        cleanup_error = _remove_temporary_worktree(
            repository,
            temporary_worktree,
            added=worktree_added,
        )

    if operation_error is not None:
        raise operation_error
    if cleanup_error is not None:
        raise cleanup_error
    if not candidate:
        raise RuntimeError("Isolated finish worktree produced no candidate commit.")
    return candidate


def run(args):
    """
    Squash merges the current UIdetox session branch back into the main branch,
    commits the squashed changes, and deletes the temporary session branch.
    """
    try:
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: Could not determine current branch or git is not initialized.")
        sys.exit(1)

    config = load_config()
    visual_status = project_visual_evidence_status(
        config,
        required=(True if getattr(args, "require_visual_evidence", False) else None),
        manifest_path=getattr(args, "visual_evidence_file", None),
    )
    eligibility = evaluate_eligibility(
        load_state(),
        EligibilityContext(
            target_score=int(config.get("target_score", 95)),
            current_branch=current_branch,
            session_branch=(
                current_branch
                if current_branch.startswith("uidetox-session-")
                else "uidetox-session-*"
            ),
            dirty=_workspace_dirty(),
            verification_fresh=(
                current_verification_fresh()
                and (not visual_status.required or visual_status.ready)
            ),
            require_session_branch=True,
            evidence_hashes=current_evidence_hashes(),
        ),
    )
    if not eligibility.eligible:
        print("❌ Finalization blocked:")
        for blocker in eligibility.blockers:
            print(f"   - {blocker.code}: {blocker.message}")
        raise SystemExit(1)

    target_branch = _detect_main_branch()

    print(f"📦 Finishing UIdetox session on branch: {current_branch}")
    print(f"▶️  Target merge branch: {target_branch}")

    try:
        repository = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        ).resolve()
        target_ref = f"refs/heads/{target_branch}"
        session_ref = f"refs/heads/{current_branch}"
        target_head = subprocess.run(
            ["git", "rev-parse", target_ref],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        session_head = subprocess.run(
            ["git", "rev-parse", session_ref],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        target_worktree = _worktree_for_branch(repository, target_ref)
        if target_worktree is not None:
            print(
                f"❌ Target branch '{target_branch}' is checked out at: "
                f"{target_worktree}"
            )
            print("   Remove that linked worktree or check out another branch, then retry.")
            raise SystemExit(1)
        candidate = _prepare_squash_candidate(
            repository,
            session_head,
            target_head,
        )
        target_worktree = _worktree_for_branch(repository, target_ref)
        if target_worktree is not None:
            print(
                f"❌ Target branch '{target_branch}' became checked out at: "
                f"{target_worktree}"
            )
            print("   Target was not published; the session branch remains intact.")
            raise SystemExit(1)
    except SystemExit:
        raise
    except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
        print(f"❌ Error during finish operation: {e}")
        print(
            f"   Original worktree remains on '{current_branch}'. "
            "Resolve the reported Git error, then retry."
        )
        raise SystemExit(1) from e

    print("▶️  Publishing squash commit...")
    try:
        subprocess.run(
            ["git", "update-ref", target_ref, candidate, target_head],
            cwd=repository,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"❌ Error publishing target branch with compare-and-swap: {e}")
        print(
            f"   Target '{target_branch}' was not overwritten. "
            f"Session branch '{current_branch}' remains intact."
        )
        raise SystemExit(1) from e

    try:
        target_worktree = _worktree_for_branch(repository, target_ref)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"❌ Target worktree verification failed after publication: {e}")
        print(
            f"   Target '{target_branch}' remains published at {candidate}. "
            "No rollback was attempted because linked-worktree ownership is unknown; "
            f"session branch '{current_branch}' remains intact."
        )
        raise SystemExit(1) from e
    if target_worktree is not None:
        print(
            f"❌ Target branch '{target_branch}' became checked out during publication at: "
            f"{target_worktree}"
        )
        try:
            index_matches_candidate = _worktree_index_matches_commit(
                target_worktree,
                candidate,
            )
            index_matches_target = _worktree_index_matches_commit(
                target_worktree,
                target_head,
            )
        except (subprocess.CalledProcessError, OSError) as e:
            print(
                f"   Could not classify the linked worktree index: {e}. "
                "No rollback was attempted; inspect the target ref before retrying. "
                f"Session branch '{current_branch}' remains intact."
            )
            raise SystemExit(1) from e
        if index_matches_candidate:
            print(
                f"   Target remains safely published at {candidate}; the linked worktree "
                f"is clean at that commit. Session branch '{current_branch}' remains intact."
            )
            raise SystemExit(1)
        if index_matches_target and _restore_target_ref(
            repository,
            target_ref,
            target_head,
            candidate,
        ):
            print(
                f"   Target was restored to {target_head}; "
                f"session branch '{current_branch}' remains intact."
            )
            raise SystemExit(1)
        print(
            "   Linked worktree index did not prove safe rollback ownership, or the "
            "target changed again. No forced update was attempted; inspect the target "
            f"ref before retrying. Session branch '{current_branch}' remains intact."
        )
        raise SystemExit(1)

    try:
        subprocess.run(
            ["git", "checkout", target_branch],
            cwd=repository,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"❌ Target published, but checkout failed: {e}")
        print(
            f"   Session branch '{current_branch}' remains intact. "
            f"Recover with: git checkout {target_branch}"
        )
        raise SystemExit(1) from e

    try:
        checked_out_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"❌ Target checkout verification failed: {e}")
        print(f"   Session branch '{current_branch}' remains intact.")
        raise SystemExit(1) from e
    if checked_out_head != candidate:
        print(
            "❌ Target checkout verification failed: "
            f"expected {candidate}, found {checked_out_head}."
        )
        print(f"   Session branch '{current_branch}' remains intact.")
        raise SystemExit(1)

    print(f"▶️  Switched to published target branch: {target_branch}")
    print("▶️  Cleaning up temporary session branch...")
    try:
        subprocess.run(
            ["git", "update-ref", "-d", session_ref, session_head],
            cwd=repository,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"❌ Target published, but session branch deletion failed: {e}")
        print(
            f"   Target '{target_branch}' is complete. "
            f"Session branch '{current_branch}' changed or could not be deleted; "
            "it was retained."
        )
        raise SystemExit(1) from e

    print("✅ UIdetox aesthetics successfully merged to your workspace!")
