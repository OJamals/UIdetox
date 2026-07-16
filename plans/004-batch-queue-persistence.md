# Plan 004: Batch scan queue persistence

> **Executor instructions**: Preserve locking, deduplication, timestamps, and stats
> exactly. Run targeted tests after every step. Update `plans/README.md` when done.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- uidetox/state.py uidetox/commands/scan.py uidetox/commands/rescan.py tests/test_state_persistence.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: perf
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

Scan and rescan call `add_issue()` once per finding. Each call acquires a lock,
reloads full state, scans the existing queue, writes formatted JSON, flushes, and
fsyncs. N findings therefore cause N durable rewrites and approximately quadratic
dedup work after analysis already completed. Batch persistence should perform one
atomic state transaction without weakening crash safety.

## Current state

```python
# uidetox/state.py:366-377
with _state_lock():
    state = load_state()
    issues = state.setdefault("issues", [])
    new_key = issue_dedup_key(issue)
    if any(issue_dedup_key(existing) == new_key for existing in issues):
        return False
    ...
    save_state(state)
```

- `uidetox/commands/scan.py:198-214` loops over findings and calls `add_issue`.
- `uidetox/commands/rescan.py:105-121` repeats the pattern.
- `_save_json()` at `uidetox/state.py:257-265` correctly uses temp file, fsync, replace; preserve it.
- Existing regression pattern: `tests/test_regressions.py:43-66` verifies scan dedup.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_state_persistence.py tests/test_regressions.py -k 'scan or rescan or state or dedup'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/state.py`
- `uidetox/commands/scan.py`
- `uidetox/commands/rescan.py`
- `tests/test_state_persistence.py`
- `tests/test_regressions.py`

**Out of scope**:
- Changing state JSON schema or dedup-key fields.
- Replacing JSON persistence with a database.
- Weakening fsync/atomic replace.
- Batching interactive `add-issue` CLI behavior across processes.

## Git workflow

- Branch: `codex/004-batch-queue-persistence`
- Commit: `perf: batch scan issue persistence`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add a locked batch state API

Add `add_issues(issues: Iterable[dict]) -> int`. Acquire `_state_lock()` once, load
state once, precompute existing dedup keys into a set, and deduplicate both against
existing state and earlier items in the same batch. Stamp each accepted dict with
`created_at`, append in input order, increment `total_found` by accepted count, and
save exactly once when count > 0. Do not save an unchanged state.

Keep `add_issue(issue) -> bool` as compatibility wrapper with identical caller-visible
mutation/timestamp behavior.

**Verify**: state tests cover empty batch, all-new, existing duplicate, intra-batch duplicate, malformed normalized state.

### Step 2: Batch scan persistence

Build the list of unsuppressed `new_issue` dicts first. Preserve `triggered_rules`
tracking for every analyzer hit, including duplicate queue entries. Call `add_issues`
once; use its return count for `queued_count`.

**Verify**: monkeypatch `save_state` and assert one call for a multi-finding scan.

### Step 3: Batch rescan persistence

Apply the same API to rescan while preserving recurrence counting and resolved-item
semantics. Update tests that monkeypatch module-local `add_issue` to target the batch
API without weakening assertions.

**Verify**: targeted command → all pass.

### Step 4: Prove complexity-sensitive behavior

Add a regression test with at least 100 generated unique issues. Instrument
`load_state` and `save_state`; assert one call each, accepted count 100, input order
preserved, and one duplicate discarded. Do not assert wall-clock timing.

**Verify**: new test passes deterministically.

## Test plan

- `add_issue` compatibility: new/duplicate return values and timestamp mutation.
- `add_issues`: empty, unique, existing duplicates, batch duplicates, stats.
- Scan/rescan: one persistence transaction, suppression, triggered rules, recurrence.
- Atomic save tests remain unchanged and green.

## Done criteria

- [ ] Multi-finding scan/rescan loads and saves state once.
- [ ] Dedup semantics and queue order unchanged.
- [ ] Atomic fsync/replace untouched.
- [ ] Full suite passes.
- [ ] Only in-scope files plus plan index changed.
- [ ] Plan status updated.

## STOP conditions

- Existing callers depend on undocumented multiple intermediate state writes.
- Locking cannot cover normalization plus save without deadlock.
- Batch change requires a state-schema migration.
- Targeted tests reveal differing scan/rescan dedup definitions.

## Maintenance notes

All bulk producers should use `add_issues`; interactive single inserts retain
`add_issue`. Reviewers should scrutinize duplicate handling inside the incoming batch
and confirm no save occurs when nothing is accepted.
