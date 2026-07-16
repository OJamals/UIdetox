# Plan 008: Make `scan --since` truly incremental

> **Executor instructions**: Preserve full-scan behavior and machine-output semantics.
> Normalize all Git paths before analysis. Update plan index after verification.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- uidetox/analyzer.py uidetox/commands/scan.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: perf
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

`scan --since` computes changed paths and prints `scanning N file(s)`, but still calls
`analyze_directory()` for the entire tree and filters results afterward. A one-file
change pays almost full traversal, file reads, AST parsing, 218-rule evaluation, and
project color audit. Incremental mode must bound actual analyzer work.

## Current state

```python
# uidetox/commands/scan.py:167-177
slop_issues = analyze_directory(scan_path, ...)
if since_files is not None:
    since_abs = {os.path.abspath(os.path.join(since_root, f)) for f in since_files}
    slop_issues = [i for i in slop_issues if os.path.abspath(i.get("file", "")) in since_abs]
```

`uidetox/analyzer.py:3289-3307` submits every walked file to ThreadPoolExecutor.
Existing Git-root tests: `tests/test_regressions.py:410-453` and `:6755-6816`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_regressions.py -k 'scan and since'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/analyzer.py`
- `uidetox/commands/scan.py`
- `tests/test_regressions.py`

**Out of scope**:
- General file-discovery consolidation; plan 009 owns it.
- Git rename history beyond paths returned by `git diff --name-only`.
- Incremental queue reconciliation of deleted files.
- Caching analyzer results between processes.

## Git workflow

- Branch: `codex/008-true-incremental-scan`
- Commit: `perf: analyze changed files in incremental scans`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add explicit analyzer targets

Extend directory analysis with an optional `target_files` input or add a focused
`analyze_files` entry point. When targets exist: normalize with `Path.resolve()`,
require containment under scan root, keep existing zone/exclude semantics, ignore
missing/deleted paths and unsupported extensions, and submit only accepted targets.
Full scans must retain current walk/concurrency behavior.

**Verify**: analyzer unit test passes 3 targets and asserts `analyze_file` called exactly 3 times.

### Step 2: Normalize Git-relative changed paths before analysis

Convert `git diff --name-only` output from repository root to absolute paths, then
filter to current scan root. Preserve subdirectory invocation behavior. Pass targets
to analyzer rather than post-filtering issue list.

**Verify**: existing Git-root tests stay green; new test proves unchanged file is never analyzed.

### Step 3: Define color-audit semantics

Run project color audit in incremental mode only when a detected color/theme config
source changed. Otherwise skip it. Document this in code because color findings are
project-wide, unlike file findings.

**Verify**: tests cover ordinary component change (no color audit) and theme config change (one color audit).

### Step 4: Cover empty/deleted/out-of-scope sets

Zero existing changed frontend files must return zero issues without falling back to
full scan. Deleted files and paths outside scan root must not be opened. Invalid Git
operation may retain current explicit full-scan fallback warning.

**Verify**: targeted tests pass.

## Test plan

- One changed frontend file among many: one analyzer call.
- Changed unsupported file: zero analyzer calls.
- Deleted file: zero analyzer calls, no crash.
- Subdirectory scan: repository-relative paths normalized correctly.
- Theme config change: project color audit behavior explicit.
- Full scan without `--since`: unchanged behavior.

## Done criteria

- [ ] Incremental analyzer call count equals accepted changed targets.
- [ ] No full-tree analyze then filter remains.
- [ ] Full scan behavior unchanged.
- [ ] Git-root/subdirectory tests pass.
- [ ] Full suite passes and plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Existing public API consumers rely on exact `analyze_directory` signature and no compatible optional parameter is possible.
- Correct path handling requires changing Git diff semantics beyond `--name-only`.
- Project color audit cannot identify its config sources deterministically.
- Incremental changes conflict with plan 005 machine-output contract in live code.

## Maintenance notes

Plan 009 will centralize discovery after this target API exists. Reviewers should
inspect containment checks, deleted paths, and zero-target behavior carefully.
