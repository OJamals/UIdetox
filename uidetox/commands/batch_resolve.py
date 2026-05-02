"""Batch-resolve command: resolve multiple issues with a single coherent commit."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from uidetox.state import batch_remove_issues, get_issue, get_project_root, load_state, load_config
from uidetox.memory import save_session, log_progress
from uidetox.utils import prepare_subprocess_cmd, tracked_changed_entries, untracked_changed_files


def _run_verification(config: dict) -> bool:
    """Run tsc → lint --fix → format --fix as a pre-commit quality gate.

    Returns True if all checks pass (or no tooling detected).
    Implements self-healing: captures error output and injects it into
    agent context so the repo is never left in an unbuildable state.
    """
    tooling = config.get("tooling", {})
    if not tooling:
        return True

    project_root = get_project_root()

    passed = True
    error_context: list[str] = []

    # TypeScript
    if tooling.get("typescript"):
        cmd = tooling["typescript"].get("run_cmd")
        if cmd:
            print("  Running TypeScript check...")
            try:
                argv, env = prepare_subprocess_cmd(cmd)
                res = subprocess.run(argv, capture_output=True, text=True, cwd=project_root, timeout=120, env=env)
                if res.returncode != 0:
                    print(f"  ⚠️  TypeScript errors remain. Fix before committing.")
                    errors = res.stdout.strip() or res.stderr.strip()
                    if errors:
                        # Truncate to avoid context overflow but keep actionable info
                        truncated = "\n".join(errors.splitlines()[:30])
                        print(f"\n{truncated}\n")
                        error_context.append(f"## TypeScript Errors\n```\n{truncated}\n```")
                    passed = False
                else:
                    print("  ✓ TypeScript passed")
            except FileNotFoundError:
                print("  ❌ TypeScript check failed: command not found.")
                error_context.append(f"## TypeScript Errors\n```\nCommand not found: {cmd}\n```")
                passed = False
            except subprocess.TimeoutExpired:
                print("  ❌ TypeScript check timed out after 120s.")
                error_context.append(f"## TypeScript Errors\n```\nTimed out after 120s: {cmd}\n```")
                passed = False

    # Lint (auto-fix)
    if tooling.get("linter"):
        fix_cmd = tooling["linter"].get("fix_cmd")
        if fix_cmd:
            print("  Running linter auto-fix...")
            try:
                argv, env = prepare_subprocess_cmd(fix_cmd)
                res = subprocess.run(argv, capture_output=True, text=True, cwd=project_root, timeout=120, env=env)
                print("  ✓ Linter auto-fix applied")
                if res.returncode != 0:
                    errors = res.stdout.strip() or res.stderr.strip()
                    if errors:
                        truncated = "\n".join(errors.splitlines()[:30])
                        print(f"  ⚠️  Linter warned of remaining issues:")
                        print(f"\n{truncated}\n")
                        error_context.append(f"## Linter Errors\n```\n{truncated}\n```")
                    passed = False
            except FileNotFoundError:
                print("  ❌ Linter auto-fix failed: command not found.")
                error_context.append(f"## Linter Errors\n```\nCommand not found: {fix_cmd}\n```")
                passed = False
            except subprocess.TimeoutExpired:
                print("  ❌ Linter auto-fix timed out after 120s.")
                error_context.append(f"## Linter Errors\n```\nTimed out after 120s: {fix_cmd}\n```")
                passed = False

    # Format (auto-fix)
    if tooling.get("formatter"):
        fix_cmd = tooling["formatter"].get("fix_cmd")
        if fix_cmd:
            print("  Running formatter auto-fix...")
            try:
                argv, env = prepare_subprocess_cmd(fix_cmd)
                res = subprocess.run(argv, capture_output=True, text=True, cwd=project_root, timeout=120, env=env)
                print("  ✓ Formatter auto-fix applied")
                if res.returncode != 0:
                    errors = res.stdout.strip() or res.stderr.strip()
                    if errors:
                        truncated = "\n".join(errors.splitlines()[:30])
                        print(f"  ⚠️  Formatter warned of remaining issues:")
                        print(f"\n{truncated}\n")
                        error_context.append(f"## Formatter Errors\n```\n{truncated}\n```")
                    passed = False
            except FileNotFoundError:
                print("  ❌ Formatter auto-fix failed: command not found.")
                error_context.append(f"## Formatter Errors\n```\nCommand not found: {fix_cmd}\n```")
                passed = False
            except subprocess.TimeoutExpired:
                print("  ❌ Formatter auto-fix timed out after 120s.")
                error_context.append(f"## Formatter Errors\n```\nTimed out after 120s: {fix_cmd}\n```")
                passed = False

    # ── Self-Healing: inject error context for agent recovery ──
    if not passed and error_context:
        print()
        print("━━━ SELF-HEALING CONTEXT (fix these errors before proceeding) ━━━")
        print()
        for block in error_context:
            print(block)
        print()
        print("[AGENT INSTRUCTION] The build is broken after your fixes.")
        print("Read the errors above, fix them in the affected files, then retry:")
        print("  1. Fix the compilation/lint errors shown above")
        print("  2. Run `uidetox check --fix` to re-verify")
        print("  3. Retry `uidetox batch-resolve` or `uidetox resolve`")
        print("DO NOT proceed to the next issue until the build is green.")
        print()

        # Persist the error context to memory so sub-agents can see it
        try:
            from uidetox.memory import add_note
            error_summary = "; ".join(
                line.strip() for block in error_context
                for line in block.splitlines()
                if line.strip() and not line.startswith("```") and not line.startswith("##")
            )[:500]
            add_note(f"[SELF-HEAL] Build broken after fix attempt: {error_summary}")
        except Exception:
            pass  # Non-critical

    return passed


def _derive_component_name(files: list[str]) -> str:
    """Derive a human-readable component name from a list of file paths."""
    if not files:
        return "unknown"

    # Find common directory
    dirs = [str(Path(f).parent) for f in files]
    if len(set(dirs)) == 1:
        # All in same directory
        d = dirs[0]
        parts = d.replace("\\", "/").split("/")
        # Use last meaningful directory name
        for part in reversed(parts):
            if part and part != ".":
                return part
        return "root"

    # Multiple directories — find deepest common ancestor using proper path semantics
    try:
        common_path = os.path.commonpath(dirs)
        name = Path(common_path).name or "project"
    except ValueError:
        name = "project"
    return name


def run(args: argparse.Namespace):
    issue_ids = args.issue_ids
    note = args.note
    skip_verify = getattr(args, "skip_verify", False)

    if not note or not note.strip():
        print("Error: --note cannot be empty. Provide a brief description of the fixes.", file=sys.stderr)
        sys.exit(1)

    # Validate all IDs exist
    missing = []
    issue_records = []
    for iid in issue_ids:
        issue = get_issue(iid)
        if not issue:
            missing.append(iid)
        else:
            issue_records.append(issue)
    if missing:
        print(f"Error: Issue(s) not found: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    affected_files = list({issue.get("file", "") for issue in issue_records if issue.get("file")})

    config = load_config()

    # Pre-commit verification gate
    if not skip_verify:
        print("━━━ Pre-commit verification ━━━")
        if not _run_verification(config):
            print("❌ Verification failed. Build is broken.", file=sys.stderr)
            sys.exit(1)
        print()

    # Batch resolve
    removed = batch_remove_issues(issue_ids, note=note)
    if not removed:
        print("❌ No issues were resolved.", file=sys.stderr)
        sys.exit(1)

    # Collect affected files
    affected_files = list(set(r.get("file", "") for r in removed if r.get("file")))
    component = _derive_component_name(affected_files)

    state = load_state()
    remaining = len(state.get("issues", []))
    resolved_total = len(state.get("resolved", []))

    print(f"✅ Batch-resolved {len(removed)} issue(s):")
    for r in removed:
        print(f"   [{r['tier']}] {r['id']}: {r['issue'][:60]}")
    print(f"   Component: {component}")
    print(f"   Note: {note}")
    print()

    # ---- Progress snapshot ----
    from uidetox.utils import compute_design_score
    scores = compute_design_score(state)
    target = config.get("target_score", 95)
    filled = scores["blended_score"] // 5
    bar = "█" * filled + "░" * (20 - filled)
    print(f"   Score : [{bar}] {scores['blended_score']}/100  (target: {target})")
    print(f"   Queue : {remaining} remaining | {resolved_total} resolved total")

    # ---- Remaining issues in same component ----
    remaining_in_component = [
        i for i in state.get("issues", [])
        if _derive_component_name([i.get("file", "")]) == component
    ]
    if remaining_in_component:
        print(f"\n   ⚡ {len(remaining_in_component)} more issue(s) in {component}:")
        for i in remaining_in_component[:5]:
            short_file = Path(i.get("file", "")).name
            print(f"      [{i.get('tier', '?')}] {i.get('id', '?')} {short_file}: {i.get('issue', '?')[:55]}")
        if len(remaining_in_component) > 5:
            print(f"      ... +{len(remaining_in_component) - 5} more")

    # Git auto-commit (single commit for the entire batch)
    if config.get("auto_commit", False):
        project_root = get_project_root()

        def _normalize(path: str) -> str:
            return str((project_root / path).resolve()) if not os.path.isabs(path) else os.path.abspath(path)

        allowed_tracked_changes = {
            _normalize(path)
            for path in affected_files + [".uidetox/state.json"]
        }
        stage_paths = {_normalize(path) for path in affected_files}
        missing_issue_paths = {path for path in stage_paths if not Path(path).exists()}
        missing_counts_by_parent: dict[Path, int] = {}
        for path in missing_issue_paths:
            parent = Path(path).parent
            missing_counts_by_parent[parent] = missing_counts_by_parent.get(parent, 0) + 1
        unexpected_tracked_changes = {
            _normalize(current_path)
            for original_path, current_path in tracked_changed_entries()
            if not ({_normalize(original_path), _normalize(current_path)} & allowed_tracked_changes)
        }
        untracked_paths = {_normalize(path) for path in untracked_changed_files()}
        untracked_by_parent: dict[Path, set[str]] = {}
        for path in untracked_paths:
            untracked_by_parent.setdefault(Path(path).parent, set()).add(path)
        allowed_untracked_changes: set[str] = set()
        for parent, missing_count in missing_counts_by_parent.items():
            sibling_untracked_paths = untracked_by_parent.get(parent, set())
            if len(sibling_untracked_paths) == missing_count:
                allowed_untracked_changes.update(sibling_untracked_paths)
        unexpected_untracked_changes = untracked_paths - allowed_untracked_changes
        for original_path, current_path in tracked_changed_entries():
            normalized_paths = {_normalize(original_path), _normalize(current_path)}
            if normalized_paths & allowed_tracked_changes:
                stage_paths.update(normalized_paths)
        stage_paths.update(allowed_untracked_changes)
        if unexpected_tracked_changes or unexpected_untracked_changes:
            print("\n   ⚠️  Skipped git auto-commit because changes exist outside the resolved files.")
        else:
            try:
                # Stage all affected files + state
                for path in sorted(stage_paths):
                    subprocess.run(["git", "add", path], check=True, capture_output=True, cwd=project_root)
                subprocess.run(["git", "add", str((project_root / ".uidetox/state.json").resolve())], check=True, capture_output=True, cwd=project_root)

                commit_msg = f"[UIdetox] Detoxed {component}: {note} ({len(removed)} issues resolved)"
                subprocess.run(
                    ["git", "commit", "-m", commit_msg, "--no-verify"],
                    check=True, capture_output=True, cwd=project_root,
                )
                print(f"\n   📦 Auto-committed: {commit_msg}")
            except subprocess.CalledProcessError:
                print("\n   ⚠️  Warning: Git auto-commit failed.")
            except FileNotFoundError:
                print("\n   ⚠️  Warning: git not found. Skipping auto-commit.")

    # ---- Agent loop signal ----
    print()
    print("[AGENT LOOP SIGNAL]")
    if remaining_in_component:
        print(f"Same component has {len(remaining_in_component)} more issues. Run `uidetox next` to continue.")
    elif remaining > 0:
        print(f"{remaining} issues remain in other components. Run `uidetox next` to continue.")
    elif scores["blended_score"] >= target:
        print("Queue empty and target reached! Run `uidetox finish`.")
    else:
        print(f"Queue empty but score {scores['blended_score']} < {target}. Run `uidetox rescan` for deeper analysis.")

    # Auto-save progress
    log_progress("batch-resolve", f"Detoxed {component}: {note} ({len(removed)} issues)")
    save_session(phase="fixing", last_command="batch-resolve",
                 last_component=component,
                 issues_fixed=len(removed), context=note)

    # Embed fix outcomes for future sub-agent context injection
    try:
        from uidetox.memory import embed_fix_outcome
        for r in removed:
            embed_fix_outcome(
                file_path=r.get("file", ""),
                issue=r.get("issue", ""),
                fix=note,
                outcome="resolved",
            )
    except Exception:
        pass  # ChromaDB is optional — never block on embedding failure
