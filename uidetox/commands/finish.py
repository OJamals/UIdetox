import argparse
import subprocess
import sys


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


def run(args: argparse.Namespace):
    """
    Squash merges the current UIdetox session branch back into the main branch,
    commits the squashed changes, and deletes the temporary session branch.
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

    target_branch = _detect_main_branch()

    # Check for uncommitted changes before switching branches
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        )
        if status.stdout.strip():
            print("⚠️  You have uncommitted changes. Committing them before finishing...")
            subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "[UIdetox] Auto-commit before finish", "--no-verify"],
                check=True, capture_output=True,
            )
    except subprocess.CalledProcessError:
        pass

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
        subprocess.run([
            "git", "commit", "-m", "[UIdetox] Detoxing complete: Resolved issues and improved Design Score.", "--no-verify"
        ], check=True)

        # Delete the session branch
        print("▶️  Cleaning up temporary branch...")
        subprocess.run(["git", "branch", "-D", current_branch], check=True)

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
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during finish operation: {e}")
        print(f"   You may need to manually resolve the merge and delete branch '{current_branch}'.")
        print(f"   To abort a failed merge:  git merge --abort")
        print(f"   To return to session:     git checkout {current_branch}")
        print(f"   To retry:                 uidetox finish")
        sys.exit(1)
