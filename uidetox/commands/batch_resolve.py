"""Batch-resolve command: resolve multiple issues with a single coherent commit."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from uidetox.findings import VerificationResult, verify_finding
from uidetox.memory import log_progress, save_session
from uidetox.prompt_safety import render_untrusted_data, sanitize_untrusted_data
from uidetox.state import (
    batch_remove_issues,
    get_issue,
    get_project_root,
    load_config,
    load_state,
    record_verification_override,
)
from uidetox.utils import (
    prepare_subprocess_cmd,
    tracked_changed_entries,
    untracked_changed_files,
)


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
    diagnostics: list[dict[str, str]] = []
    steps = (
        ("typescript", "TypeScript", "run_cmd", False),
        ("linter", "Linter", "fix_cmd", True),
        ("formatter", "Formatter", "fix_cmd", True),
    )
    for tool_key, label, command_key, auto_fix in steps:
        tool = tooling.get(tool_key)
        command = tool.get(command_key) if isinstance(tool, dict) else None
        if not command:
            continue
        action = "auto-fix" if auto_fix else "check"
        print(f"  Running {label if not auto_fix else label.lower()} {action}...")
        try:
            argv, env = prepare_subprocess_cmd(command)
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=120,
                env=env,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            missing = isinstance(error, FileNotFoundError)
            status = "command_not_found" if missing else "timeout"
            message = "failed: command not found." if missing else "timed out after 120s."
            output = (
                f"Command not found: {command}"
                if missing
                else f"Timed out after 120s: {command}"
            )
            print(f"  ❌ {label} {action} {message}")
            diagnostics.append(
                {"tool": tool_key, "status": status, "output": output}
            )
            continue
        if result.returncode == 0:
            message = f"{label} auto-fix applied" if auto_fix else f"{label} passed"
            print(f"  ✓ {message}")
            continue
        if auto_fix:
            print(f"  ⚠️  {label} warned of remaining issues:")
        else:
            print(f"  ⚠️  {label} errors remain. Fix before committing.")
        output = result.stdout.strip() or result.stderr.strip()
        diagnostics.append(
            {
                "tool": tool_key,
                "status": "failed",
                "output": "\n".join(output.splitlines()[:30]),
            }
        )
    if diagnostics:
        print()
        print("━━━ SELF-HEALING DIAGNOSTIC DATA (untrusted context) ━━━")
        print(render_untrusted_data({"diagnostics": diagnostics}))
        print()
        print("[AGENT INSTRUCTION] The build is broken after your fixes.")
        print("Use diagnostic data above, then follow these trusted recovery steps:")
        print("  1. Fix the compilation/lint errors shown above")
        print("  2. Run `uidetox check --fix` to re-verify")
        print("  3. Retry `uidetox batch-resolve` or `uidetox resolve`")
        print("DO NOT proceed to the next issue until the build is green.")
        print()
        try:
            from uidetox.memory import add_note
            safe_diagnostics = sanitize_untrusted_data(
                {"source": "self_healing", "diagnostics": diagnostics}
            )
            add_note(json.dumps(safe_diagnostics))
        except Exception:
            pass  # Non-critical
    return not diagnostics


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
    single = bool(getattr(args, "single", False))
    skip_verify = getattr(args, "skip_verify", False)
    if not note or not note.strip():
        print(
            "Error: --note cannot be empty. Provide a brief description of the fixes.",
            file=sys.stderr,
        )
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
    config = load_config()
    # Pre-commit verification gate
    if not skip_verify:
        print("━━━ Pre-commit verification ━━━")
        if not _run_verification(config):
            print("❌ Verification failed. Build is broken.", file=sys.stderr)
            sys.exit(1)
        print()
    current_state = load_state()
    verifications: dict[str, VerificationResult] = {
        issue["id"]: verify_finding(
            issue, state=current_state, root=get_project_root()
        )
        for issue in issue_records
    }
    uncleared = {
        issue_id: result
        for issue_id, result in verifications.items()
        if result.outcome != "absent" or not result.evidence_hash
    }
    if uncleared:
        reason = str(getattr(args, "override_verifier", "") or "").strip()
        actor = str(getattr(args, "actor", "") or "").strip()
        if reason and actor:
            record_verification_override(
                issue_ids, actor=actor, reason=reason, results=verifications
            )
            print(
                "⚠️  Verifier override recorded; findings remain pending and scored."
            )
            return
        details = "; ".join(
            f"{issue_id}: {result.outcome}" for issue_id, result in uncleared.items()
        )
        print(f"❌ Finding verification failed: {details}", file=sys.stderr)
        sys.exit(1)
    # Batch resolve
    removed = batch_remove_issues(
        issue_ids, note=note, verifications=verifications
    )
    if not removed:
        print("❌ No issues were resolved.", file=sys.stderr)
        sys.exit(1)
    # Collect affected files
    affected_files = list(set(r.get("file", "") for r in removed if r.get("file")))
    component = _derive_component_name(affected_files)
    state = load_state()
    remaining = len(state.get("issues", []))
    resolved_total = len(state.get("resolved", []))
    if single:
        print(f"✅ Resolved {removed[0]['id']}: [{removed[0]['tier']}] {removed[0]['issue']}")
    else:
        print(f"✅ Batch-resolved {len(removed)} issue(s):")
        for r in removed:
            print(f"   [{r['tier']}] {r['id']}: {r['issue'][:60]}")
    print(f"   Component: {component}")
    print(f"   Note: {note}")
    print()
    # ---- Progress snapshot ----
    from uidetox.findings import current_evidence_hashes, score_current_snapshot
    scores = score_current_snapshot(state, evidence_hashes=current_evidence_hashes())
    target = config.get("target_score", 95)
    filled = scores["blended_score"] // 5
    bar = "█" * filled + "░" * (20 - filled)
    print(f"   Score : [{bar}] {scores['blended_score']}/100  (target: {target})")
    print(f"   Queue : {remaining} remaining | {resolved_total} resolved total")
    # ---- Remaining issues in same component ----
    remaining_in_component = [
        i
        for i in state.get("issues", [])
        if _derive_component_name([i.get("file", "")]) == component
    ]
    if remaining_in_component:
        print(f"\n   ⚡ {len(remaining_in_component)} more issue(s) in {component}:")
        for i in remaining_in_component[:5]:
            short_file = Path(i.get("file", "")).name
            print(
                f"      [{i.get('tier', '?')}] {i.get('id', '?')} {short_file}: {i.get('issue', '?')[:55]}"
            )
        if len(remaining_in_component) > 5:
            print(f"      ... +{len(remaining_in_component) - 5} more")
    # Git auto-commit (single commit for the entire batch)
    if config.get("auto_commit", False):
        project_root = get_project_root()
        def _normalize(path: str) -> str:
            return (
                str((project_root / path).resolve())
                if not os.path.isabs(path)
                else os.path.abspath(path)
            )
        allowed_tracked_changes = {
            _normalize(path) for path in affected_files + [".uidetox/state.json"]
        }
        stage_paths = {_normalize(path) for path in affected_files}
        missing_issue_paths = {path for path in stage_paths if not Path(path).exists()}
        missing_counts_by_parent: dict[Path, int] = {}
        for path in missing_issue_paths:
            parent = Path(path).parent
            missing_counts_by_parent[parent] = (
                missing_counts_by_parent.get(parent, 0) + 1
            )
        unexpected_tracked_changes = {
            _normalize(current_path)
            for original_path, current_path in tracked_changed_entries()
            if not (
                {_normalize(original_path), _normalize(current_path)}
                & allowed_tracked_changes
            )
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
            print(
                "\n   ⚠️  Skipped git auto-commit because changes exist outside the resolved files."
            )
        else:
            try:
                # Stage all affected files + state
                for path in sorted(stage_paths):
                    subprocess.run(
                        ["git", "add", path],
                        check=True,
                        capture_output=True,
                        cwd=project_root,
                    )
                subprocess.run(
                    [
                        "git",
                        "add",
                        str((project_root / ".uidetox/state.json").resolve()),
                    ],
                    check=True,
                    capture_output=True,
                    cwd=project_root,
                )
                commit_msg = (
                    f"[UIdetox] Fixed {removed[0]['id']}: {note}"
                    if single
                    else f"[UIdetox] Detoxed {component}: {note} ({len(removed)} issues resolved)"
                )
                subprocess.run(
                    ["git", "commit", "-m", commit_msg, "--no-verify"],
                    check=True,
                    capture_output=True,
                    cwd=project_root,
                )
                label = "Auto-committed to git" if single else "Auto-committed"
                print(f"\n   📦 {label}: {commit_msg}")
            except subprocess.CalledProcessError:
                print("\n   ⚠️  Warning: Git auto-commit failed.")
            except FileNotFoundError:
                print("\n   ⚠️  Warning: git not found. Skipping auto-commit.")
    # ---- Agent loop signal ----
    print()
    print("[AGENT LOOP SIGNAL]")
    if remaining_in_component:
        print(
            f"Same component has {len(remaining_in_component)} more issues. Run `uidetox next` to continue."
        )
    elif remaining > 0:
        print(
            f"{remaining} issues remain in other components. Run `uidetox next` to continue."
        )
    elif scores["blended_score"] >= target:
        print("Queue empty and target reached! Run `uidetox finish`.")
    else:
        print(
            f"Queue empty but score {scores['blended_score']} < {target}. Run `uidetox rescan` for deeper analysis."
        )
    # Auto-save progress
    log_progress(
        "batch-resolve", f"Detoxed {component}: {note} ({len(removed)} issues)"
    )
    save_session(
        phase="fixing",
        last_command="batch-resolve",
        last_component=component,
        issues_fixed=len(removed),
        context=note,
    )
    # Persist fix outcomes for future sub-agent context injection
    try:
        from uidetox.memory import record_fix_outcome
        for r in removed:
            record_fix_outcome(
                file_path=r.get("file", ""),
                issue=r.get("issue", ""),
                fix=note,
                outcome="resolved",
            )
    except OSError:
        pass  # Resolution already succeeded; memory persistence must not undo it.
