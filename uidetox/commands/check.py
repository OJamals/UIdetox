"""Check command: runs tsc → lint → format in sequence."""

import argparse
import subprocess
from uidetox.tooling import detect_all  # type: ignore
from uidetox.state import load_config, save_config, get_project_root  # type: ignore
from uidetox.utils import run_tool  # type: ignore
from uidetox.commands import tsc as tsc_cmd  # type: ignore
from uidetox.commands import lint as lint_cmd  # type: ignore
from uidetox.commands import format_cmd  # type: ignore

# Patterns that indicate a formatter/linter actually changed files.
# Avoids false positives from output like "0 files formatted".
import re
_CHANGE_PATTERNS = re.compile(
    r'\b(?:[1-9]\d*)\s+(?:file|error|warning)s?\s+(?:fixed|formatted|changed)'
    r'|\bsuccessfully\s+(?:fixed|formatted)'
    r'|\bformatting\s+\d+\s+file'
    r'|\bfixed\s+\d+\s+(?:error|warning|issue)',
    re.IGNORECASE,
)


def _tool_made_changes(output: str) -> bool:
    """Return True if tool output indicates files were actually modified."""
    return bool(_CHANGE_PATTERNS.search(output))


def _git_changed_paths(project_root: str) -> set[str]:
    """Return staged, unstaged, and untracked repo paths."""
    changed: set[str] = set()
    commands = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    for cmd in commands:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        if res.returncode != 0:
            raise subprocess.CalledProcessError(res.returncode, cmd, output=res.stdout, stderr=res.stderr)
        for line in res.stdout.splitlines():
            path = line.strip()
            if path:
                changed.add(path)
    return changed


def run(args: argparse.Namespace):
    # First, ensure tooling is detected
    config = load_config()
    if not config.get("tooling"):
        profile = detect_all()
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
    project_root = str(get_project_root())
    pre_fix_changed: set[str] | None = None

    # Build tool lists with fallback: prefer all_linters/all_formatters,
    # fall back to single linter/formatter if the lists are empty.
    fix_formatters = tooling.get("all_formatters") or []
    if not fix_formatters and tooling.get("formatter"):
        fix_formatters = [tooling["formatter"]]
    fix_linters = tooling.get("all_linters") or []
    if not fix_linters and tooling.get("linter"):
        fix_linters = [tooling["linter"]]

    if fix and (fix_linters or fix_formatters):
        if config.get("auto_commit", False):
            try:
                pre_fix_changed = _git_changed_paths(project_root)
            except Exception as e:
                print(f"  ⚠️  Warning: Could not establish git baseline for scoped auto-commit: {e}")
                pre_fix_changed = None

        print("━━━ Phase 1: Iterative Auto-Fix ━━━")

        # Deduplicate: when biome is both linter and formatter, the same
        # fix command would run twice per iteration. Track by command string.
        seen_cmds: set[str] = set()
        deduped_tools: list[dict] = []
        for tool in fix_formatters + fix_linters:
            cmd = tool.get("fix_cmd")
            if cmd and cmd not in seen_cmds:
                seen_cmds.add(cmd)
                deduped_tools.append(tool)

        for iteration in range(1, 4):
            print(f"Iteration {iteration}...")
            changed = False

            for tool in deduped_tools:
                cmd = tool.get("fix_cmd")
                if not cmd:
                    continue
                try:
                    res = run_tool(cmd, cwd=project_root)
                    combined = (res.stdout + res.stderr).lower()
                    if res.returncode != 0 or _tool_made_changes(combined):
                        changed = True
                except FileNotFoundError:
                    print(f"Warning: Command not found ({cmd})")

            if not changed:
                print("Code is clean or no more auto-fixes available.\n")
                break
        print("Auto-fix phase complete.\n")

        if config.get("auto_commit", False):
            try:
                if pre_fix_changed is None:
                    raise RuntimeError("missing pre-fix git baseline")
                post_fix_changed = _git_changed_paths(project_root)
                changed_files = sorted(post_fix_changed - pre_fix_changed)
                if changed_files:
                    from uidetox.git_policy import CommitPolicy, safe_commit
                    policy = CommitPolicy.from_config(config)
                    result = safe_commit(
                        touched_files=list(changed_files),
                        message="[UIdetox] Mechanical auto-fix (formatting/linting)",
                        policy=policy,
                        cwd=project_root,
                    )
                    if result.success:
                        print("  📦 Auto-committed mechanical fixes to git.\n")
                    else:
                        print(f"  ⚠️  Auto-commit aborted: {result.aborted_reason}\n")
            except Exception as e:
                print(f"  ⚠️  Warning: Git auto-commit failed during mechanical check: {e}\n")

    print("━━━ Phase 2: Diagnostic Checks ━━━")

    # Step 1: TypeScript
    if tooling.get("typescript"):
        print("  Running TypeScript check...")
        tsc_args = argparse.Namespace(fix=False)
        tsc_cmd.run(tsc_args)
        steps_run += 1
        print()
    else:
        print("  TypeScript: skipped (not detected)\n")

    # Step 2: Lint
    if fix_linters:
        print("  Running Linter check...")
        lint_args = argparse.Namespace(fix=False)
        lint_cmd.run(lint_args)
        steps_run += 1
        print()
    else:
        print("  Linter: skipped (not detected)\n")

    # Step 3: Format
    if fix_formatters:
        print("  Running Formatter check...")
        fmt_args = argparse.Namespace(fix=False)
        format_cmd.run(fmt_args)
        steps_run += 1
        print()
    else:
        print("  Formatter: skipped (not detected)\n")

    if steps_run == 0:
        print("No tooling detected. Run 'uidetox detect' to configure tooling.")
        return

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Ran {steps_run} mechanical check(s).")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("Mechanical checks complete. Continue the autonomous loop:")
    print("  → Run `uidetox next` to fix the next batch of issues.")
    print("  → Or run `uidetox loop` to re-enter the full autonomous cycle.")
    print("DO NOT STOP.")
