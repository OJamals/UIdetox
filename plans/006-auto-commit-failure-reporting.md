# Plan 006: Report mechanical auto-commit failures accurately

> **Executor instructions**: Preserve dirty-worktree protection and exact-file staging.
> Never run this plan against valuable uncommitted work. Use temporary git repos in
> tests. Update plan index after completion.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- uidetox/commands/check.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: bug
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

Mechanical auto-fix calls `git add` and `git commit` with `check=False`, discards
return codes, then prints success. Missing Git, hooks/config problems, invalid author
identity, or commit rejection can leave fixes uncheckpointed while autonomous loop
believes a recovery point exists.

## Current state

```python
# uidetox/commands/check.py:18-24
for f in sorted(files):
    subprocess.run(["git", "add", str(path)], check=False, cwd=project_root)
subprocess.run(["git", "commit", "-m", message, "--no-verify"], check=False, cwd=project_root)

# lines 98-100
_auto_commit_changed_files(new_changes, "[UIdetox] Mechanical auto-fix (formatting/linting)")
print("  Auto-committed mechanical fixes to git.")
```

Other resolve/batch-resolve tests at `tests/test_regressions.py:1219-1625` demonstrate
the repo's expected dirty-worktree and exact-file staging conventions.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_regressions.py -k 'check and commit'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/commands/check.py`
- `tests/test_regressions.py`

**Out of scope**:
- Changing auto-commit default or `--no-verify` policy.
- Committing pre-existing changes.
- Rolling back formatter/linter edits after commit failure.
- Refactoring resolve or batch-resolve commit paths.

## Git workflow

- Branch: `codex/006-auto-commit-failure-reporting`
- Commit: `fix: report mechanical auto-commit failures`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Make helper outcome explicit

Change `_auto_commit_changed_files` to either return a structured success result or
raise a specific exception on failed staging/commit. Stage all selected paths in one
`git add -- <paths...>` invocation to avoid ignoring partial per-file failures. Capture
stdout/stderr, require return code 0, preserve `cwd=project_root` and sorted paths.

**Verify**: unit tests simulate failed add and failed commit; helper never returns success.

### Step 2: Print success only after verified commit

Caller prints success only when helper confirms commit. Failure warning must include
safe stderr summary and nonzero code without exposing environment secrets. Return a
nonzero command status only if that matches current `check` command conventions;
otherwise clearly warn and leave later verification behavior unchanged.

**Verify**: capsys tests assert success absent on failure and present once on success.

### Step 3: Preserve dirty-worktree protection

Retain skip when tracked changes existed before mechanical fixes. Verify only files
newly changed by the fix phase are staged. Do not stage untracked/unrelated files.

**Verify**: temporary-repo tests cover clean success, pre-dirty skip, add failure,
commit failure, and exact staged path list.

## Test plan

- Monkeypatch subprocess for isolated return-code behavior.
- Add at least one real temporary git repository test with local user config.
- Assert failure messages and staged file set.
- Full suite confirms no effect on resolve/batch-resolve behavior.

## Done criteria

- [ ] Every git subprocess return code is checked.
- [ ] Success printed only after successful commit.
- [ ] Pre-existing changes remain untouched.
- [ ] Failure tests cover add and commit.
- [ ] Full suite passes and plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Accurate failure handling requires staging unrelated files.
- Existing command contract mandates silent commit failure.
- Tests cannot isolate Git operations in temporary repositories.
- Fix requires changing auto-commit policy outside `check.py`.

## Maintenance notes

Reviewers should confirm absolute paths are passed after `--`, no shell is introduced,
and captured stderr is concise. Future auto-commit paths should share a common helper
only through a separate, explicitly scoped refactor.
