"""Autofix command: automatically apply safe T1 fixes with rollback safety."""

import argparse
import os
import subprocess
from pathlib import Path

from uidetox.state import (  # pyre-ignore[21]
    load_state,
    load_config,
    save_config,
    batch_remove_issues,
    get_project_root,
)
from uidetox.tooling import detect_all  # pyre-ignore[21]
from uidetox.utils import categorize_issue, run_tool, safe_split_cmd  # pyre-ignore[21]


_CATEGORY_GUIDANCE: dict[str, str] = {
    "typography": "Replace with Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale. Use rem/Tailwind scale instead of px. Use Medium (500) and SemiBold (600).",
    "color": "Replace pure black with zinc-950/#0f0f0f. Replace purple-blue gradients with a single accent on neutral base. Extract repeated hex literals to CSS variables. See reference/color-palettes.md.",
    "layout": "Replace h-screen with min-h-[100dvh]. Use asymmetric grids. Vary spacing scale. Use 'grid place-items-center' instead of verbose flex centering.",
    "motion": "Replace animate-bounce/pulse/spin with CSS transitions (150-300ms ease-out-quart). Add transition-colors/transition-all to hover elements.",
    "materiality": "Use shadow-sm/shadow-md. Replace glassmorphism with solid surfaces + subtle borders. Reduce border-radius to rounded-lg/rounded-xl max. Remove neon glows and gradient text.",
    "states": "Add hover:, focus:ring, active: states to all interactive elements. Add disabled:cursor-not-allowed disabled:opacity-50 to disabled elements.",
    "content": "Write real draft copy. Use diverse, realistic names. Use organic numbers. Replace Unsplash URLs with picsum.photos. Remove exclamation marks from status messages.",
    "code quality": "Create semantic z-index scale (10/20/30/40/50). Replace divs with semantic HTML5. Extract inline styles. Fix lint/type suppressions instead of disabling.",
    "components": "Replace lucide-react with Phosphor/Heroicons. Replace pill badges with squared (rounded-md). Replace hero dashboards with inline metrics.",
    "duplication": "Extract repeated className strings to cn()/cva() utilities. Extract copy-pasted markup into shared components. Merge duplicate media queries. Deduplicate event handlers.",
    "dead code": "Delete commented-out code (git has history). Remove unused imports via linter. Remove empty handlers. Delete dead CSS classes. Resolve TODOs or convert to tracked issues.",
    "accessibility": "Add htmlFor to labels. Use opacity on borders for softer blending. Style or hide scrollbars. Add ARIA labels to icon-only buttons.",
}

_TRANSFORM_MAP: dict[str, str] = {
    "typography": "typography.js",
    "color": "color.js",
    "materiality": "color.js",
    "layout": "spacing.js",
    "motion": "typography.js",
    "states": "spacing.js",
    "code quality": "spacing.js",
}

class _FixPhaseStats:
    """Execution stats for a mechanical fix phase."""

    def __init__(self):
        self.attempted = 0
        self.succeeded = 0
        self.failed = 0

    @property
    def ran(self) -> bool:
        return self.attempted > 0

    @property
    def clean(self) -> bool:
        return self.attempted > 0 and self.failed == 0


def _ensure_tooling(config: dict) -> dict:
    """Load tooling from config, auto-detecting if missing."""
    tooling = config.get("tooling")
    if not tooling:
        profile = detect_all()
        tooling = profile.to_dict()
        config["tooling"] = tooling
        save_config(config)
    return tooling


def _run_lint_fixes(
    tooling: dict,
    project_root: str,
    *,
    dedupe_set: set[str] | None = None,
) -> _FixPhaseStats:
    """Run all detected linters with --fix and return phase stats."""
    linters = tooling.get("all_linters") or []
    if not linters and tooling.get("linter"):
        linters = [tooling["linter"]]

    seen = dedupe_set if dedupe_set is not None else set()
    stats = _FixPhaseStats()
    for linter in linters:
        cmd = linter.get("fix_cmd")
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        stats.attempted += 1
        print(f"  Running: {cmd}")
        try:
            result = run_tool(cmd, cwd=project_root, timeout=120)
            if result.returncode == 0:
                stats.succeeded += 1
                print(f"    ✓ {linter['name']}: fixes applied successfully.")
            else:
                stats.failed += 1
                print(f"    ⚠️  {linter['name']}: fix pass completed with non-zero exit.")
        except FileNotFoundError:
            stats.failed += 1
            print(f"    ⚠️  {linter['name']} command not found ({cmd})")
        except subprocess.TimeoutExpired:
            stats.failed += 1
            print(f"    ⚠️  {linter['name']} timed out after 120s")
    return stats


def _run_format_fixes(
    tooling: dict,
    project_root: str,
    *,
    dedupe_set: set[str] | None = None,
) -> _FixPhaseStats:
    """Run all detected formatters with --fix/--write and return phase stats."""
    formatters = tooling.get("all_formatters") or []
    if not formatters and tooling.get("formatter"):
        formatters = [tooling["formatter"]]

    seen = dedupe_set if dedupe_set is not None else set()
    stats = _FixPhaseStats()
    for formatter in formatters:
        cmd = formatter.get("fix_cmd")
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        stats.attempted += 1
        print(f"  Running: {cmd}")
        try:
            result = run_tool(cmd, cwd=project_root, timeout=120)
            if result.returncode == 0:
                stats.succeeded += 1
                print(f"    ✓ {formatter['name']}: formatting applied successfully.")
            else:
                stats.failed += 1
                print(f"    ⚠️  {formatter['name']}: format pass completed with non-zero exit.")
        except FileNotFoundError:
            stats.failed += 1
            print(f"    ⚠️  {formatter['name']} command not found ({cmd})")
        except subprocess.TimeoutExpired:
            stats.failed += 1
            print(f"    ⚠️  {formatter['name']} timed out after 120s")
    return stats


def _run_jscodeshift_transforms(grouped: dict[str, list[dict]]) -> set[str]:
    """Run jscodeshift transforms for design-pattern categories. Returns set of fixed file paths."""
    transforms_dir = Path(__file__).parent.parent / "data" / "transforms"
    if not transforms_dir.exists():
        return set()

    applied_files: set[str] = set()
    transforms_run: set[str] = set()

    for cat_name in grouped:
        transform_name = _TRANSFORM_MAP.get(cat_name)
        if not transform_name:
            continue
        transform_file = transforms_dir / transform_name
        if not transform_file.exists():
            continue

        transform_key = str(transform_file)
        if transform_key in transforms_run:
            continue

        files_to_fix: list[str] = []
        for cn, ci in grouped.items():
            mapped = _TRANSFORM_MAP.get(cn)
            if mapped == transform_name:
                files_to_fix.extend(i["file"] for i in ci)
        files_to_fix = list(set(files_to_fix))

        js_exts = {".tsx", ".jsx", ".ts", ".js"}
        files_to_fix = [f for f in files_to_fix if Path(f).suffix.lower() in js_exts]
        if not files_to_fix:
            continue

        print(f"\n  Applying {transform_name} via jscodeshift on {len(files_to_fix)} file(s)...")
        transforms_run.add(transform_key)

        try:
            result = subprocess.run(
                ["npx", "jscodeshift", "-t", str(transform_file), "--parser", "tsx", *files_to_fix],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                applied_files.update(files_to_fix)
                print(f"    ✓ Transformed {len(files_to_fix)} file(s).")
            else:
                stderr = result.stderr.strip()
                if stderr:
                    print(f"    ⚠️  Transform returned errors (files may be partially fixed).")
        except FileNotFoundError:
            print("    ⚠️  npx not found — skipping jscodeshift transforms.")
            break
        except subprocess.TimeoutExpired:
            print(f"    ⚠️  Timeout on batch of {len(files_to_fix)} files.")

    return applied_files


def _normalize_repo_path(path: str, project_root: str) -> str | None:
    """Normalize *path* to a repo-relative path if it belongs to the project."""
    p = Path(path)
    root = Path(project_root).resolve()
    try:
        if p.is_absolute():
            return str(p.resolve().relative_to(root))
        return str(Path(path))
    except ValueError:
        return None


def _git_modified_paths(project_root: str) -> set[str]:
    """Return worktree/staged/untracked paths for git-scoped commit safety."""
    changed: set[str] = set()
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=project_root,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return changed

    for line in status.stdout.splitlines():
        if not line or len(line) < 4:
            continue
        code = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if not path:
            continue
        if code != "  ":
            changed.add(path)
    return changed


def _auto_commit(fixed_files: set[str], project_root: str, label: str) -> None:
    """Stage only *fixed_files* and commit (hooks enabled by default)."""
    if not fixed_files:
        return
    try:
        changed = _git_modified_paths(project_root)
        scoped = []
        for f in sorted(fixed_files):
            rel = _normalize_repo_path(f, project_root)
            if rel and rel in changed:
                scoped.append(rel)

        if not scoped:
            return

        for f in scoped:
            subprocess.run(["git", "add", "--", f], cwd=project_root, capture_output=True, check=True)

        subprocess.run(
            ["git", "commit", "-m", f"[UIdetox] Autofix: {label} ({len(scoped)} files)"],
            check=True, stdout=subprocess.DEVNULL, cwd=project_root,
        )
        print(f"   Auto-committed {label} to git.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"   ⚠️  Git auto-commit failed.")


def _is_repo_wide_fix_cmd(cmd: str) -> bool:
    """Heuristic: detect fix commands likely to mutate files beyond issue paths."""
    parts = safe_split_cmd(cmd)
    return (
        "." in parts
        or any("*" in p for p in parts)
        or "--write" in parts
        or "--fix" in parts
    )


def _collect_snapshot_files(t1_issues: list[dict], tooling: dict, project_root: str) -> list[str]:
    """Capture issue files plus tracked repo files for repo-wide fix commands."""
    files = {str(i.get("file")) for i in t1_issues if i.get("file")}

    fix_cmds: list[str] = []
    for tool in (tooling.get("all_linters") or []):
        cmd = tool.get("fix_cmd")
        if cmd:
            fix_cmds.append(cmd)
    for tool in (tooling.get("all_formatters") or []):
        cmd = tool.get("fix_cmd")
        if cmd:
            fix_cmds.append(cmd)
    if tooling.get("linter"):
        cmd = tooling["linter"].get("fix_cmd")
        if cmd:
            fix_cmds.append(cmd)
    if tooling.get("formatter"):
        cmd = tooling["formatter"].get("fix_cmd")
        if cmd:
            fix_cmds.append(cmd)

    if any(_is_repo_wide_fix_cmd(cmd) for cmd in fix_cmds):
        try:
            tracked = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                cwd=project_root,
                check=True,
            )
            for line in tracked.stdout.splitlines():
                rel = line.strip()
                if rel:
                    files.add(rel)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Git may be unavailable; keep issue-file snapshot fallback.
            pass

    return sorted(files)


# ── Snapshot / Rollback infrastructure ─────────────────────────────
class _FileSnapshot:
    """In-memory snapshot of files that can be restored on failure.

    This is the autofix failsafe. Before any transform modifies files,
    we capture their content.  If the transform or post-verification
    fails, we restore the originals so the repo never lands in a broken
    state.  Works even if git is not available.
    """

    def __init__(self, project_root: str):
        self._root = project_root
        self._snapshots: dict[str, bytes | None] = {}

    def capture(self, files: list[str]) -> None:
        """Capture current content of *files* for later restoration."""
        for f in files:
            path = os.path.join(self._root, f) if not os.path.isabs(f) else f
            try:
                with open(path, "rb") as fh:
                    self._snapshots[path] = fh.read()
            except OSError:
                # Track non-existent files too, so rollback can delete them if created.
                self._snapshots[path] = None

    def restore(self) -> int:
        """Restore all captured files to their snapshotted content.

        Returns the number of files restored.
        """
        restored = 0
        for path, content in self._snapshots.items():
            try:
                if content is None:
                    if os.path.exists(path):
                        os.remove(path)
                    restored += 1
                    continue
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(content)
                restored += 1
            except OSError:
                pass
        return restored

    @property
    def file_count(self) -> int:
        return len(self._snapshots)


def _verify_no_regressions(tooling: dict, project_root: str) -> bool:
    """Quick verification pass to detect regressions introduced by autofix.

    Runs TypeScript check + linter (without --fix) to see if the codebase
    still compiles cleanly.  Returns True if clean, False if regressions.
    """
    # TypeScript check (compile errors are the most critical regression)
    ts = tooling.get("typescript", {})
    ts_cmd = ts.get("run_cmd") if ts else None
    if ts_cmd:
        try:
            result = run_tool(ts_cmd, cwd=project_root, timeout=120)
            if result.returncode != 0:
                errors = (result.stdout + result.stderr).strip()
                if errors and "error TS" in errors:
                    return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # Tool missing — not a regression

    # Lint check (without --fix — just diagnostic)
    linter = tooling.get("linter", {})
    lint_cmd = linter.get("run_cmd") if linter else None
    if lint_cmd:
        try:
            result = run_tool(lint_cmd, cwd=project_root, timeout=120)
            if result.returncode != 0:
                errors = (result.stdout + result.stderr).strip()
                # Check for new hard errors (not just warnings)
                error_lines = [l for l in errors.splitlines() if "error" in l.lower() and "warning" not in l.lower()]
                if len(error_lines) > 5:
                    return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return True


def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])
    t1_issues = [i for i in issues if i.get("tier") == "T1"]

    if not t1_issues:
        print("No T1 (quick fix) issues found. Nothing to autofix.")
        return

    dry_run = getattr(args, "dry_run", False)

    # Partition issues by fix strategy
    lint_issues = [i for i in t1_issues if i.get("command") == "lint-fix"]
    format_issues = [i for i in t1_issues if i.get("command") in ("format-fix", "format")]
    tsc_issues = [i for i in t1_issues if i.get("command") == "tsc-fix"]
    mechanical_ids = {i["id"] for i in lint_issues + format_issues + tsc_issues}
    design_issues = [i for i in t1_issues if i["id"] not in mechanical_ids]

    # Group design issues by category for jscodeshift + guidance
    design_grouped: dict[str, list[dict]] = {}
    for issue in design_issues:
        desc = issue.get("issue", "") + " " + issue.get("command", "")
        cat = categorize_issue(desc)
        design_grouped.setdefault(cat, []).append(issue)

    print("==============================")
    print(" UIdetox Autofix")
    print("==============================")
    print(f"Found {len(t1_issues)} T1 issue(s) eligible for autofix:\n")

    if lint_issues:
        print(f"  --- LINT ({len(lint_issues)} issues) → will run linter --fix ---")
        for issue in lint_issues[:5]:
            print(f"    [{issue['id']}] {issue['file']}: {issue['issue'][:80]}")
        if len(lint_issues) > 5:
            print(f"    ... and {len(lint_issues) - 5} more")
        print()

    if format_issues:
        print(f"  --- FORMAT ({len(format_issues)} issues) → will run formatter --write ---")
        for issue in format_issues[:5]:
            print(f"    [{issue['id']}] {issue['file']}: {issue['issue'][:80]}")
        if len(format_issues) > 5:
            print(f"    ... and {len(format_issues) - 5} more")
        print()

    if tsc_issues:
        print(f"  --- TSC ({len(tsc_issues)} issues) → no auto-fix (requires code changes) ---")
        for issue in tsc_issues[:5]:
            print(f"    [{issue['id']}] {issue['file']}: {issue['issue'][:80]}")
        if len(tsc_issues) > 5:
            print(f"    ... and {len(tsc_issues) - 5} more")
        print()

    for cat_name, cat_issues in design_grouped.items():
        has_transform = cat_name in _TRANSFORM_MAP
        label = "jscodeshift" if has_transform else "agent-assisted"
        guidance = _CATEGORY_GUIDANCE.get(cat_name, "Apply fix as described.")
        print(f"  --- {cat_name.upper()} ({len(cat_issues)} issues) → {label} ---")
        print(f"  Guidance: {guidance}")
        for issue in cat_issues[:5]:
            print(f"    [{issue['id']}] {issue['file']}: {issue['issue'][:80]}")
        if len(cat_issues) > 5:
            print(f"    ... and {len(cat_issues) - 5} more")
        print()

    if dry_run:
        print("[DRY RUN] No changes applied. Remove --dry-run to apply.")
        return

    config = load_config()
    tooling = _ensure_tooling(config)
    project_root = str(get_project_root())
    auto_commit = config.get("auto_commit", False)
    resolved_ids: list[str] = []
    total_fixed = 0

    # ── Create file snapshot BEFORE any modifications ──
    # Captures issue files + tracked repo files when fix commands are repo-wide.
    all_affected_files = _collect_snapshot_files(t1_issues, tooling, project_root)
    snapshot = _FileSnapshot(project_root)
    snapshot.capture(all_affected_files)
    if snapshot.file_count > 0:
        print(f"  📸 Captured snapshot of {snapshot.file_count} file(s) for rollback safety.")
        print()

    # ── Phase 1: Lint fixes ──
    phase_dedupe: set[str] = set()
    if lint_issues:
        print("━━━ Phase 1: Lint Auto-Fix ━━━")
        stats = _run_lint_fixes(tooling, project_root, dedupe_set=phase_dedupe)
        if stats.clean:
            resolved_ids.extend(i["id"] for i in lint_issues)
            total_fixed += len(lint_issues)
            if auto_commit:
                _auto_commit({str(i.get("file")) for i in lint_issues if i.get("file")}, project_root, "lint fixes")
        elif stats.ran:
            print("  ⚠️  Lint fix phase had failures — keeping lint issues in queue.")
        print()

    # ── Phase 2: Format fixes ──
    if format_issues:
        print("━━━ Phase 2: Format Auto-Fix ━━━")
        stats = _run_format_fixes(tooling, project_root, dedupe_set=phase_dedupe)
        if stats.clean:
            resolved_ids.extend(i["id"] for i in format_issues)
            total_fixed += len(format_issues)
            if auto_commit:
                _auto_commit({str(i.get("file")) for i in format_issues if i.get("file")}, project_root, "format fixes")
        elif stats.ran:
            print("  ⚠️  Format fix phase had failures — keeping format issues in queue.")
        print()

    # ── Phase 3: Design-pattern transforms (jscodeshift) ──
    transformable = {
        cat: issues for cat, issues in design_grouped.items()
        if cat in _TRANSFORM_MAP
    }
    if transformable:
        print("━━━ Phase 3: Design-Pattern Transforms ━━━")
        fixed_files = _run_jscodeshift_transforms(transformable)
        if fixed_files:
            # Verify transforms didn't break lint/format before committing
            print("  Running post-transform verification (lint → format)...")
            verify_dedupe: set[str] = set()
            _run_lint_fixes(tooling, project_root, dedupe_set=verify_dedupe)
            _run_format_fixes(tooling, project_root, dedupe_set=verify_dedupe)

            # ── Regression check after transforms ──
            print("  Verifying no regressions introduced...")
            if not _verify_no_regressions(tooling, project_root):
                print("  ❌ REGRESSION DETECTED after jscodeshift transforms!")
                print("  🔄 Rolling back to pre-transform state...")
                restored = snapshot.restore()
                print(f"  ✅ Rolled back {restored} file(s). Transforms discarded.")
                print("  [AGENT INSTRUCTION] Transforms introduced errors.")
                print("  Apply these fixes manually using `uidetox next` instead.")
                print()
            else:
                print("  ✓ No regressions detected — transforms are safe.")
                for cat_issues in transformable.values():
                    for issue in cat_issues:
                        if issue["file"] in fixed_files:
                            resolved_ids.append(issue["id"])
                            total_fixed += 1
                if auto_commit:
                    _auto_commit(fixed_files, project_root, "design-pattern transforms")
        print()

    # ── Phase 4: Final verification pass ──
    if total_fixed > 0:
        print("━━━ Phase 4: Final Verification ━━━")
        final_verify_dedupe: set[str] = set()
        _run_lint_fixes(tooling, project_root, dedupe_set=final_verify_dedupe)
        _run_format_fixes(tooling, project_root, dedupe_set=final_verify_dedupe)
        ts_cmd = (tooling.get("typescript") or {}).get("run_cmd")
        if ts_cmd:
            print(f"  Running TypeScript check: {ts_cmd}")
            try:
                result = run_tool(ts_cmd, cwd=project_root, timeout=120)
                if result.returncode == 0:
                    print("    ✓ TypeScript check passed")
                else:
                    output = (result.stdout + result.stderr).strip()
                    if output:
                        error_lines = output.splitlines()[:10]
                        print(f"    ⚠️  TypeScript errors remain:\n{chr(10).join(error_lines)}")
                        # Check if these are new errors introduced by autofix
                        if "error TS" in output:
                            print()
                            print("    ❌ TypeScript compilation broken after autofix!")
                            print("    🔄 Rolling back ALL autofix changes...")
                            restored = snapshot.restore()
                            print(f"    ✅ Rolled back {restored} file(s).")
                            print("    [AGENT INSTRUCTION] Autofix introduced TypeScript errors.")
                            print("    Fix these issues manually using `uidetox next` instead.")
                            # Clear resolved_ids since we rolled back
                            resolved_ids.clear()
                            total_fixed = 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("    ⚠️  TypeScript check skipped (not found or timed out)")
        if auto_commit and total_fixed > 0:
            _auto_commit({str(i.get("file")) for i in t1_issues if i.get("file")}, project_root, "final verification cleanup")
        print()

    # ── Resolve fixed issues from the queue ──
    if resolved_ids:
        removed = batch_remove_issues(resolved_ids, note="autofix: mechanical T1 fix applied")
        print(f"✅ Auto-fixed and resolved {len(removed)} issue(s).")

    # ── Report remaining issues that need agent assistance ──
    remaining = []
    if tsc_issues:
        remaining.extend(tsc_issues)
    for cat, cat_issues in design_grouped.items():
        if cat not in _TRANSFORM_MAP:
            remaining.extend(cat_issues)
    # Add design issues in transformed categories whose files weren't actually fixed
    resolved_set = set(resolved_ids)
    if transformable:
        for cat_issues in transformable.values():
            for issue in cat_issues:
                if issue["id"] not in resolved_set:
                    remaining.append(issue)

    if remaining:
        print(f"\n[AGENT INSTRUCTION]")
        print(f"{len(remaining)} T1 issue(s) require agent-assisted fixing:")
        for issue in remaining[:15]:
            desc = issue.get("issue", "")[:60]
            print(f"  [{issue['id']}] {issue['file']}: {desc}")
            print(f"    → Fix: {issue.get('command', 'manual')}")
        if len(remaining) > 15:
            print(f"  ... and {len(remaining) - 15} more")
        print(f"\nFor each fix:")
        print(f"  1. Open the file")
        print(f"  2. Apply the fix using the category guidance above")
        print(f"  3. Run `uidetox resolve <issue_id> --note \"what you changed\"` when done")
        if auto_commit:
            print(f"\n  AUTO-COMMIT is ON — each `resolve` will atomically commit the fix to git.")
    elif total_fixed > 0:
        print(f"\nAll {total_fixed} T1 issues resolved automatically.")
        print("Run `uidetox rescan` to verify, or `uidetox next` to continue with T2+ issues.")
    else:
        print("\nNo mechanical fixes could be applied.")
        print("Run `uidetox next` to start fixing issues manually.")
