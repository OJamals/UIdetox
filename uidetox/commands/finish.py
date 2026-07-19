import subprocess
import sys

from uidetox.state import load_config
from uidetox.visual_semantics import project_visual_evidence_status


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
        branches = [b.strip().lstrip("* ") for b in result.stdout.splitlines()]
        for candidate in ("main", "master", "develop", "dev"):
            if candidate in branches:
                return candidate
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return "main"  # Last-resort default


def _ensure_clean_workspace() -> None:
    """Refuse to finish if unrelated changes could be swept into the squash commit."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: Could not inspect git status.")
        sys.exit(1)

    if result.stdout.strip():
        print("❌ Refusing to finish: workspace has uncommitted changes.")
        print(
            "   Commit, stash, or remove unrelated changes before running `uidetox finish`."
        )
        print()
        print(result.stdout.strip())
        sys.exit(1)


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

    if not current_branch.startswith("uidetox-session-"):
        print(
            f"⚠️  Not currently on a UIdetox session branch. (Current branch: {current_branch})"
        )
        print(
            "Run 'uidetox finish' only when you are on a branch created by 'uidetox loop'."
        )
        sys.exit(1)

    visual_status = project_visual_evidence_status(
        load_config(),
        required=(True if getattr(args, "require_visual_evidence", False) else None),
        manifest_path=getattr(args, "visual_evidence_file", None),
    )
    if visual_status.required and not visual_status.ready:
        print(f"❌ Visual evidence is {visual_status.state}.")
        for reason in visual_status.reasons:
            print(f"   - {reason}")
        sys.exit(1)

    target_branch = _detect_main_branch()
    _ensure_clean_workspace()

    print(f"📦 Finishing UIdetox session on branch: {current_branch}")
    print(f"▶️  Target merge branch: {target_branch}")

    try:
        # Switch to the detected main branch
        subprocess.run(["git", "checkout", target_branch], check=True)
        print(f"▶️  Switched to target branch: {target_branch}")

        # Squash merge
        print("▶️  Squashing changes...")
        subprocess.run(["git", "merge", "--squash", current_branch], check=True)

        # Commit squashed changes
        print("▶️  Committing aesthetic fixes...")
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "[UIdetox] Detoxing complete: Resolved issues and improved Design Score.",
                "--no-verify",
            ],
            check=True,
        )

        # Delete the session branch
        print("▶️  Cleaning up temporary branch...")
        subprocess.run(["git", "branch", "-D", current_branch], check=True)

        print("✅ UIdetox aesthetics successfully merged to your workspace!")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"❌ Error during finish operation: {e}")
        print(
            f"   You may need to manually resolve the merge and delete branch '{current_branch}'."
        )
        sys.exit(1)
