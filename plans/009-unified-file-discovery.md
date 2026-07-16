# Plan 009: Unify frontend file discovery and exclusion semantics

> **Executor instructions**: Implement one shared discovery policy, then migrate
> consumers without changing analyzer rules. This plan is reconciled through completed
> plans 002, 007, and 008; preserve their prompt isolation, animation matching, and
> explicit-target behavior. Any later unrelated mismatch is a STOP condition. Update
> plan index when done.
>
> **Drift check (run first)**: `git diff --stat 103da49..HEAD -- uidetox/fileset.py uidetox/analyzer.py uidetox/commands/loop.py uidetox/subagent.py uidetox/commands/watch.py uidetox/commands/diff.py tests/test_regressions.py`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/008-true-incremental-scan.md`
- **Category**: tech-debt
- **Planned at**: commit `103da49`, 2026-07-15

## Why this matters

Scan, orchestrator sizing, subagent sharding, watch, and diff independently decide
which files belong to the project. They disagree on root, ignored directories,
extensions, configured excludes, and zones. Worse, scan collapses a configured path
to its final basename, so excluding one nested subtree hides every same-named folder.
One project-root-aware policy prevents hidden findings and agent work on vendor/generated files.

## Current state

```python
# uidetox/analyzer.py:3295-3298
skip_dirs = set(IGNORE_DIRS)
for ep in exclude_paths:
    skip_dirs.add(ep.strip("/").split("/")[-1] if "/" in ep else ep)

# uidetox/subagent.py:253-264
for dirpath, dirnames, filenames in os.walk("."):
    ...
```

- `uidetox/commands/loop.py:51-62` uses project-root `rglob`, its own ignores, and includes `.sass`.
- `uidetox/subagent.py:253-264` uses current directory, omits config/zones and `.sass`.
- `uidetox/analyzer.py:3301-3305` handles vendor/generated zone overrides separately.
- Config key is `exclude`; preserve it. Existing pattern: `tests/test_regressions.py:5727-5750`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_regressions.py -k 'exclude or zone or frontend_files or subdirectory or watch or diff'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/fileset.py` (create)
- `uidetox/analyzer.py`
- `uidetox/commands/loop.py`
- `uidetox/subagent.py`
- `uidetox/commands/watch.py`
- `uidetox/commands/diff.py`
- `tests/test_regressions.py`

**Out of scope**:
- Analyzer rule definitions or issue scoring.
- Queue persistence.
- Following symlinks outside project root.
- Changing zone names or config schema.

## Git workflow

- Branch: `codex/009-unified-file-discovery`
- Commit: `refactor: unify frontend file discovery`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Define canonical file-set policy

Create `uidetox/fileset.py` with:

- one immutable `FRONTEND_EXTENSIONS` set including `.tsx`, `.jsx`, `.ts`, `.js`,
  `.vue`, `.svelte`, `.html`, `.css`, `.scss`, `.sass`;
- canonical built-in ignored directory names;
- `ProjectFileSet` or equivalent typed discovery API accepting project root,
  configured excludes, zone overrides, and optional explicit targets;
- root containment and normalized root-relative paths.

Exclusion semantics: an entry containing a path separator excludes exactly that
root-relative subtree; a simple basename remains a global directory-name exclusion.
Vendor/generated zone entries exclude exact files or subtrees. Hidden directories
and symlink escapes remain excluded.

**Verify**: unit tests build two same-named nested folders and prove path-specific exclusion removes only requested subtree.

### Step 2: Migrate analyzer discovery

Make `analyze_directory` consume shared file set and plan 008 explicit targets. Keep
ThreadPoolExecutor and project color audit behavior. Remove basename-collapsing logic.

**Verify**: analyzer exclusion/zone tests pass.

### Step 3: Migrate orchestrator and subagent discovery

Loop sizing and `get_frontend_files` must use project root plus loaded config. Return
stable sorted project-relative paths for prompts. Orchestrator threshold and sharding
must derive from same file set scan sees, including `.sass`.

**Verify**: invoke from nested cwd in test; scan count, loop count, and subagent list match.

### Step 4: Migrate watch and diff

Use canonical extensions/ignore policy. Watch may still snapshot mtimes, but must not
watch excluded/zoned files. Diff explicit changed paths must use the same acceptance
predicate and project-relative normalization.

**Verify**: targeted watch/diff tests pass.

### Step 5: Remove duplicated policy constants

Delete consumer-local frontend extension and ignore sets now owned by `fileset.py`.
Keep command-specific non-frontend ignores only when documented by test.

**Verify**: `rtk rg -n 'frontend_exts|_WATCH_EXTS|exclude_dirs' uidetox` → no duplicated discovery policy outside `fileset.py`, except explicitly justified aliases.

## Test plan

- Same basename in two subtrees; path-specific exclude affects one.
- Simple basename exclude affects all matching directories.
- Vendor/generated zone file and directory exclusions.
- Nested cwd produces project-root-stable results.
- Extension parity including `.sass`.
- Explicit targets outside root, symlink escapes, missing files rejected.
- Scan/loop/subagent/watch/diff accept same fixture set.

## Done criteria

- [ ] One canonical extensions/ignore/exclusion implementation exists.
- [ ] All five consumers use it.
- [ ] Path-specific exclusions preserve unrelated same-named directories.
- [ ] Nested-cwd and zone tests pass.
- [ ] Full suite passes and plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Plan 008 target API is absent or materially different.
- Existing config intentionally defines all excludes as global basenames.
- Consumer requires files outside project root.
- Migration requires changing public issue path format without compatibility layer.

## Maintenance notes

All future commands that enumerate frontend files must consume `fileset.py`. Reviewers
should reject new local extension/ignore sets and scrutinize root containment on macOS,
Linux, and Windows path separators.
