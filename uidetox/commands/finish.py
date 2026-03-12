import argparse
import subprocess
import sys

from uidetox.state import load_state, load_config, save_config
from uidetox.utils import compute_design_score, get_score_freshness


def _ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _local_branch_exists(branch: str) -> bool:
    return _ref_exists(f"refs/heads/{branch}")


def _remote_branch_exists(branch: str) -> bool:
    return _ref_exists(f"refs/remotes/origin/{branch}")


def _detect_main_branch() -> str:
    """Detect the primary branch (main, master, develop) reliably.

    Instead of using 'git checkout -' which goes to the last-visited branch
    (unreliable if user has switched branches), we detect the actual default branch.
    """
    # Try remote HEAD (most reliable)
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    except subprocess.CalledProcessError:
        pass

    # Fall back to checking common branch names
    try:
        result = subprocess.run(
            ["git", "branch", "--list"], capture_output=True, text=True, check=True,
        )
        branches = [b.strip().removeprefix("* ").strip() for b in result.stdout.splitlines()]
        for candidate in ("main", "master", "develop", "dev"):
            if candidate in branches:
                return candidate
    except subprocess.CalledProcessError:
        pass

    return "main"  # Last-resort default


def _branch_exists(branch: str) -> bool:
    """Return True when branch exists locally or on origin."""
    return _local_branch_exists(branch) or _remote_branch_exists(branch)


def _checkout_target_branch(branch: str) -> None:
    """Checkout merge target, creating a local tracking branch if needed."""
    if _local_branch_exists(branch):
        subprocess.run(["git", "checkout", branch], check=True)
        return

    if _remote_branch_exists(branch):
        subprocess.run(["git", "checkout", "-b", branch, f"origin/{branch}"], check=True)
        return

    raise subprocess.CalledProcessError(1, ["git", "checkout", branch])


def _dirty_worktree_paths() -> list[str]:
    """Return file paths from git porcelain status (tracked + untracked)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.rstrip()
        if len(line) < 4:
            continue
        # Format: XY <path> OR XY <old> -> <new> (rename)
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1].strip()
        if path_part:
            paths.append(path_part)
    return list(dict.fromkeys(paths))


def _resolve_target_branch(current_branch: str, config: dict) -> tuple[str, str]:
    """Resolve merge target branch.

    Prefer the branch that the current session was created from. Fall back to
    default-branch detection for older sessions that lack metadata.
    """
    session_meta = config.get("git_session", {})
    if isinstance(session_meta, dict):
        active_branch = str(session_meta.get("active_branch", "")).strip()
        base_branch = str(session_meta.get("base_branch", "")).strip()
        if base_branch and (not active_branch or active_branch == current_branch):
            if _branch_exists(base_branch):
                return base_branch, "recorded session base branch"

    return _detect_main_branch(), "detected default branch"


def _clear_session_metadata(session_branch: str) -> None:
    """Clear stale git-session metadata after a successful finish."""
    try:
        config = load_config()
        session_meta = config.get("git_session")
        if not isinstance(session_meta, dict):
            return

        active_branch = str(session_meta.get("active_branch", "")).strip()
        if active_branch and active_branch != session_branch:
            return

        config.pop("git_session", None)
        save_config(config)
    except Exception:
        # Never block finish cleanup on metadata writes.
        pass


def run(args: argparse.Namespace):
    """
    Squash merge the current UIdetox session branch back into its base branch,
    commit the squashed changes, and delete the temporary session branch.
    """
    try:
        current_branch = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except subprocess.CalledProcessError:
        print("❌ Error: Could not determine current branch or git is not initialized.")
        sys.exit(1)

    if not current_branch.startswith("uidetox-session-"):
        print(f"⚠️  Not currently on a UIdetox session branch. (Current branch: {current_branch})")
        print("Run 'uidetox finish' only when you are on a branch created by 'uidetox loop'.")
        sys.exit(1)

    # ── Score validation gate ──
    force = getattr(args, "force", False)
    state = load_state()
    config = load_config()
    target_branch, target_reason = _resolve_target_branch(current_branch, config)
    scores = compute_design_score(state)
    freshness = get_score_freshness(state)
    blended = scores["blended_score"]
    target = config.get("target_score", 95)
    queue_size = len(state.get("issues", []))

    if not force:
        blocked = False
        if blended < target:
            print(f"⚠️  Design Score {blended}/100 has NOT reached target {target}.")
            blocked = True
        if queue_size > 0:
            print(f"⚠️  Queue still has {queue_size} pending issue(s).")
            blocked = True
        if not freshness["target_ready"]:
            print("⚠️  Score is stale — needs fresh scan + review.")
            for r in freshness.get("reasons", [])[:3]:
                print(f"     - {r}")
            blocked = True
        if blocked:
            print()
            print("Run `uidetox loop` to reach the target, or `uidetox finish --force` to override.")
            sys.exit(1)

    # Check for uncommitted changes before switching branches
    try:
        dirty_paths = _dirty_worktree_paths()
    except subprocess.CalledProcessError:
        dirty_paths = []

    if dirty_paths:
        print("⚠️  You have uncommitted changes. Committing them before finishing...")
        try:
            from uidetox.git_policy import CommitPolicy, safe_commit

            policy = CommitPolicy.from_config(config)
            result = safe_commit(
                touched_files=dirty_paths,
                message="[UIdetox] Auto-commit before finish",
                policy=policy,
                cwd=".",
            )
            if not result.success:
                print(f"❌ Auto-commit before finish failed: {result.aborted_reason}")
                print("Resolve the working tree and run `uidetox finish` again.")
                sys.exit(1)
        except Exception as exc:
            print(f"❌ Auto-commit before finish failed: {exc}")
            print("Resolve the working tree and run `uidetox finish` again.")
            sys.exit(1)

    print(f"📦 Finishing UIdetox session on branch: {current_branch}")
    print(f"▶️  Target merge branch: {target_branch} ({target_reason})")

    try:
        # Switch to the detected main branch
        _checkout_target_branch(target_branch)
        print(f"▶️  Switched to target branch: {target_branch}")

        # Squash merge
        print("▶️  Squashing changes...")
        subprocess.run(["git", "merge", "--squash", current_branch], check=True)

        # Commit squashed changes
        print("▶️  Committing aesthetic fixes...")
        subprocess.run([
            "git", "commit", "-m", "[UIdetox] Detoxing complete: Resolved issues and improved Design Score."
        ], check=True)

        # Delete the session branch
        print("▶️  Cleaning up temporary branch...")
        subprocess.run(["git", "branch", "-D", current_branch], check=True)
        _clear_session_metadata(current_branch)

        # Compact ChromaDB embeddings to prevent unbounded growth
        try:
            from uidetox.memory import compact_embeddings
            trimmed = compact_embeddings()
            if trimmed:
                print(f"▶️  Compacted embeddings: {trimmed}")
        except Exception:
            pass  # Non-critical in finish flow

        print("✅ UIdetox aesthetics successfully merged to your workspace!")
        print()
        print("╔══════════════════════════════════════════════════════╗")
        print("║  SESSION COMPLETE — UIdetox autonomous loop done.   ║")
        print("║  All fixes merged. Design quality target achieved.  ║")
        print("╚══════════════════════════════════════════════════════╝")
        print()
        # Final score summary
        obj = scores.get("objective_score")
        raw_sub = scores.get("subjective_score")
        eff_sub = scores.get("effective_subjective")
        print("  ─── Final Score Summary ───")
        print(f"  Blended Design Score : {blended}/100  (target: {target})")
        if obj is not None:
            print(f"  Objective            : {obj}/100  (static analysis — 30%)")
        if raw_sub is not None and eff_sub is not None:
            if eff_sub != raw_sub:
                print(f"  Subjective           : {eff_sub}/100 effective  (raw {raw_sub} → curve + penalties)")
                print(f"  Compression          : -{raw_sub - eff_sub} pts")
            else:
                print(f"  Subjective           : {raw_sub}/100  (LLM review — 70%)")
        elif raw_sub is not None:
            print(f"  Subjective           : {raw_sub}/100  (LLM review — 70%)")
        print(f"  Queue                : {queue_size} pending issue(s)")
        print()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during finish operation: {e}")
        print(f"   You may need to manually resolve the merge and delete branch '{current_branch}'.")
        print(f"   To abort a failed merge:  git merge --abort")
        print(f"   To return to session:     git checkout {current_branch}")
        print(f"   To retry:                 uidetox finish")
        sys.exit(1)
