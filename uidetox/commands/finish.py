import subprocess
import sys

from uidetox.findings import (
    EligibilityContext,
    current_evidence_hashes,
    current_verification_fresh,
    evaluate_eligibility,
)
from uidetox.state import load_config, load_state
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
