import subprocess
import sys

def run(args):
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

    print(f"📦 Finishing UIdetox session on branch: {current_branch}")

    try:
        # Switch back to previous branch
        subprocess.run(["git", "checkout", "-"], check=True)
        
        target_branch = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, text=True, check=True
        ).stdout.strip()
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

        print("✅ UIdetox aesthetics successfully merged to your workspace!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during finish operation: {e}")
        sys.exit(1)
