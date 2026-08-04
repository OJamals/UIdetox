"""Check command: runs tsc → lint → format in sequence."""

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from uidetox.commands import format_cmd
from uidetox.commands import lint as lint_cmd
from uidetox.commands import tsc as tsc_cmd
from uidetox.mechanical import run_mechanical_command
from uidetox.state import get_project_root, load_config, save_config
from uidetox.tooling import detect_all
from uidetox.utils import tracked_changed_files


@dataclass(frozen=True)
class AutoCommitResult:
    staged_paths: tuple[str, ...]


class AutoCommitError(RuntimeError):
    """A mechanical git auto-commit command failed."""


def _safe_git_error_summary(output: str) -> str:
    """Return concise git output with common secret assignments redacted."""
    summary = " ".join(output.split()) or "no error output"
    summary = re.sub(
        r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b(\s*[:=]\s*|\s+)([^\s,;]+)",
        r"\1\2[REDACTED]",
        summary,
    )
    summary = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", summary)
    return summary if len(summary) <= 240 else f"{summary[:237]}..."


def _auto_commit_changed_files(files: set[str], message: str) -> AutoCommitResult:
    """Stage specific changed files and commit them."""
    project_root = get_project_root()
    paths = []

    for f in files:
        path = Path(f)
        if not path.is_absolute():
            path = project_root / path
        paths.append(str(path.resolve()))

    sorted_paths = tuple(sorted(paths))
    add_cmd = ["git", "add", "--", *sorted_paths]
    try:
        add_result = subprocess.run(
            add_cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=project_root,
        )
    except FileNotFoundError as exc:
        raise AutoCommitError("git add failed: git executable not found") from exc
    if add_result.returncode != 0:
        detail = _safe_git_error_summary(add_result.stderr or add_result.stdout)
        raise AutoCommitError(
            f"git add failed (exit {add_result.returncode}): {detail}"
        )

    commit_cmd = ["git", "commit", "-m", message, "--no-verify"]
    try:
        commit_result = subprocess.run(
            commit_cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=project_root,
        )
    except FileNotFoundError as exc:
        raise AutoCommitError("git commit failed: git executable not found") from exc
    if commit_result.returncode != 0:
        detail = _safe_git_error_summary(commit_result.stderr or commit_result.stdout)
        raise AutoCommitError(
            f"git commit failed (exit {commit_result.returncode}): {detail}"
        )

    return AutoCommitResult(staged_paths=sorted_paths)


def _tracked_changed_files() -> set[str]:
    """Return tracked files with staged or unstaged changes."""
    return tracked_changed_files()


def run(args: argparse.Namespace):
    # First, ensure tooling is detected
    project_root = get_project_root()
    config = load_config()
    if not config.get("tooling"):
        profile = detect_all(project_root)
        config["tooling"] = profile.to_dict()
        save_config(config)
        print("Auto-detected project tooling.\n")

    tooling = config.get("tooling", {})

    print("╔══════════════════════════════╗")
    print("║   UIdetox Mechanical Check   ║")
    print("╚══════════════════════════════╝")
    print()

    fix = getattr(args, "fix", False)
    steps_run = 0
    checks_passed = True
    fix_phase_failed = False
    pre_existing_changes: set[str] = set()

    if fix and config.get("auto_commit", False):
        pre_existing_changes = _tracked_changed_files()

    if fix and (tooling.get("linter") or tooling.get("formatter")):
        print("━━━ Phase 1: Iterative Auto-Fix ━━━")
        fix_commands = []
        if tooling.get("formatter") and tooling["formatter"].get("fix_cmd"):
            fix_commands.append(
                ("Formatter", tooling["formatter"]["fix_cmd"], ("fixed", "formatted"))
            )
        if tooling.get("linter") and tooling["linter"].get("fix_cmd"):
            fix_commands.append(("Linter", tooling["linter"]["fix_cmd"], ("fixed",)))

        for iteration in range(1, 4):
            print(f"Iteration {iteration}...")
            changed = False
            retryable_commands = []

            for label, cmd, convergence_signals in fix_commands:
                result = run_mechanical_command(cmd, project_root)
                if result.returncode != 0:
                    fix_phase_failed = True
                    checks_passed = False
                    if result.error == "command_not_found":
                        print(f"Warning: {label} command not found ({cmd})")
                    elif result.error == "timeout":
                        print(f"Warning: {label} command timed out ({cmd})")
                    else:
                        print(
                            f"Warning: {label} command failed "
                            f"(exit {result.returncode}) ({cmd})"
                        )
                    continue

                retryable_commands.append((label, cmd, convergence_signals))
                output = result.output.lower()
                if any(signal in output for signal in convergence_signals):
                    changed = True

            fix_commands = retryable_commands

            if not changed:
                if not fix_phase_failed:
                    print("Code is clean or no more auto-fixes available.\n")
                break
        print("Auto-fix phase complete.\n")

        if config.get("auto_commit", False) and not fix_phase_failed:
            try:
                post_fix_changes = _tracked_changed_files()
                if pre_existing_changes:
                    print(
                        "  ⚠️  Skipped git auto-commit because tracked changes already existed before mechanical fixes.\n"
                    )
                else:
                    new_changes = post_fix_changes - pre_existing_changes
                    if new_changes:
                        _auto_commit_changed_files(
                            new_changes,
                            "[UIdetox] Mechanical auto-fix (formatting/linting)",
                        )
                        print("  📦 Auto-committed mechanical fixes to git.\n")
            except Exception as e:  # noqa: BLE001 - optional auto-commit failure must not hide completed mechanical checks
                print(
                    f"  ⚠️  Warning: Git auto-commit failed during mechanical check: {e}\n"
                )

    print("━━━ Phase 2: Diagnostic Checks ━━━")

    # Step 1: TypeScript
    if tooling.get("typescript"):
        print("  Running TypeScript check...")
        tsc_args = argparse.Namespace(fix=False)
        if tsc_cmd.run(tsc_args) is False:
            checks_passed = False
        steps_run += 1
        print()
    else:
        print("  TypeScript: skipped (not detected)\n")

    # Step 2: Lint
    if tooling.get("linter"):
        print("  Running Linter check...")
        lint_args = argparse.Namespace(fix=False)
        if lint_cmd.run(lint_args) is False:
            checks_passed = False
        steps_run += 1
        print()
    else:
        print("  Linter: skipped (not detected)\n")

    # Step 3: Format
    if tooling.get("formatter"):
        print("  Running Formatter check...")
        fmt_args = argparse.Namespace(fix=False)
        if format_cmd.run(fmt_args) is False:
            checks_passed = False
        steps_run += 1
        print()
    else:
        print("  Formatter: skipped (not detected)\n")

    if steps_run == 0:
        print("No tooling detected. Run 'uidetox detect' to configure tooling.")
        return

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Ran {steps_run} mechanical check(s).")
    print("Run 'uidetox status' to see the updated health score.")
    print("Run 'uidetox next' to start fixing any queued issues.")
    if not checks_passed:
        raise RuntimeError("Mechanical checks failed.")
