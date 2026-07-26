# Plan 018: Replace initial-frame capture with efficient scenario observation

> **Executor instructions**: Extend the existing observer into one scenario
> engine; do not retain separate initial-state and scenario capture paths.
> Consolidate viewport, writing-mode, geometry, readiness, and coverage policy.
> Delete superseded passes. Do not modify `plans/` or `.codebase-memory/`;
> the advisor owns those files.
>
> **Drift check (run first)**:
> `git diff --stat d0ec3b0..HEAD -- uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/frontend_map.py uidetox/commands/map.py uidetox/commands/capture.py uidetox/workflow.py tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_capture.py tests/test_visual_evidence.py tests/test_calibration_matrix.py`

## Status

- **State**: DONE on isolated branch `codex/018-scenario-runtime-observation`
- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/015-unified-findings-and-verified-closure.md`, `plans/016-application-semantics-and-source-ownership.md`
- **Category**: direction
- **Planned at**: commit `d0ec3b0`, 2026-07-26
- **Execution base**: approved Plan 017 commit `d0ec3b0`, which already
  contains Plans 015 and 016. Plan 018 overlaps Plan 017 runtime/map seams and
  must not be rebuilt from the older dependency commits.
- **Delivered at**: commits `b256651`, `049bb07`, `d5e6c25`, `4ecf44c`,
  and `43596ae`
- **Acceptance evidence**: fresh `tree-sitter==0.25.2` environments completed
  blocker-focused tests and 1,376 full tests with warnings as errors. Scoped
  Ruff, `compileall`, wheel build/install/metadata, CLI smoke, diff checks,
  graph review, and orphan-process checks passed.
- **Production delta**: `+2,194/-410` lines versus `d0ec3b0` (net `+1,784`).
  The replacement removed the silent 20-peer cap and old capture path, shrank
  `commands/capture.py` by 17 net lines, and retained one browser engine,
  geometry cache, viewport policy, and finding model. The 6,301-node benchmark
  improved from 11.0799 s to 5.7205 s (48.4%).

## Why this matters

The observer samples only initial rendered state. A swallowed network-idle
timeout plus a default 250 ms wait can capture skeleton/hydrating content, yet
any successful page marks runtime evidence current. Large DOMs are silently
capped. Alignment drops valid zero-deviation anchors. Repeated descendant,
ancestor, style, and rectangle scans increase cost on the complex applications
UIdetox most needs to understand.

## Current state

- `uidetox/runtime_observer.py:180-258` documents and executes initial-state
  observation across URL × viewport.
- `uidetox/runtime_observer.py:279-291` catches network-idle timeout, waits the
  fixed settle interval, and measures anyway.
- `uidetox/frontend_map.py:756-769` marks any non-empty runtime page set
  `current` while separately storing errors.
- `uidetox/runtime_observer.py:421-422` and `:1091-1096` silently cap DOM
  candidates at 3,000 and 1,500.
- `uidetox/runtime_observer.py:1009-1038` discards zero anchor deviations before
  selecting the smallest remaining peer deviation.
- `uidetox/runtime_observer.py:744-837` repeatedly walks ancestors and
  descendants with layout reads.
- `uidetox/runtime_observer.py:44-48` and
  `uidetox/commands/capture.py:43-48` define different viewport sets.
- `uidetox/findings.py:650-660` and
  `uidetox/commands/scan.py:335-364` reject only `stale` runtime status, so
  `degraded`, `partial`, and `failed` evidence would incorrectly qualify as
  current unless the canonical trust gates are tightened.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Runtime | `python -m pytest -q -W error tests/test_runtime_observer.py tests/test_frontend_mapping.py` | all pass |
| Capture | `python -m pytest -q -W error tests/test_capture.py tests/test_visual_evidence.py` | all pass |
| Browser | `python -m pytest -q -W error -m browser` | deterministic pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | runtime TP/FP/FN stable |
| Full | `python -m pytest -q -W error` | exit 0 |
| Ruff | `python -m ruff check --select E4,E7,E9,F,I uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/frontend_map.py uidetox/findings.py uidetox/commands/map.py uidetox/commands/capture.py uidetox/commands/scan.py uidetox/workflow.py tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_capture.py tests/test_visual_evidence.py tests/test_finding_resolution.py tests/test_regressions.py tests/test_calibration_matrix.py` | exit 0 |
| Compile | `python -m compileall -q uidetox tests` | exit 0 |

Use a fresh virtual environment. Before tests, prove
`tree-sitter>=0.25,<0.26`; do not reuse the project `.venv` if it still
contains 0.26. Build a wheel, install it into a second clean virtual
environment, inspect wheel metadata, and smoke `uidetox --help`,
`uidetox map --help`, and `uidetox capture --help`.

## Scope

**In scope**:
- `uidetox/runtime_observer.py`
- `uidetox/runtime_scenarios.py` (create only if extracting pure contracts,
  policy, and serialization materially reduces observer cognitive load; it
  must not contain a second execution path)
- `uidetox/runtime_layout.py`
- `uidetox/frontend_map.py`
- `uidetox/findings.py`
- `uidetox/commands/map.py`
- `uidetox/commands/capture.py`
- `uidetox/commands/scan.py`
- `uidetox/workflow.py`
- `tests/test_runtime_observer.py`
- `tests/test_frontend_mapping.py`
- `tests/test_capture.py`
- `tests/test_visual_evidence.py`
- `tests/test_finding_resolution.py`
- `tests/test_regressions.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/runtime-scenarios.md` (create)

**Out of scope**:
- A general autonomous web crawler.
- Storing passwords/tokens in scenario files.
- Mutating production application state without explicit scenario steps.
- Aesthetic scoring from screenshot difference.

## Cleanup and replacement constraints

- Initial observation becomes the default one-step scenario, not a legacy path.
- Keep Playwright orchestration in `runtime_observer.py`; if the observer grows
  materially, move pure scenario/readiness/viewport contracts and validation
  together into `runtime_scenarios.py` rather than growing one mixed module or
  creating multiple policy modules.
- One viewport registry serves map, capture, screenshots, and evidence metadata.
- One writing-mode/logical-axis helper serves measurement and finding policy.
- Replace repeated DOM geometry/style walks with one cached measurement pass.
- Remove silent array slicing; bounded traversal must expose coverage.
- Record benchmark duration and production JavaScript/Python line deltas.

## Git workflow

- Branch: `codex/018-scenario-runtime-observation`
- Create the isolated worktree and branch at `d0ec3b0`.
- Commit by behavior: policy/types, readiness/status, scenarios/diagnostics,
  geometry/detectors, cleanup.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Characterize present defects and performance

Add browser fixtures for slow hydration, streaming/polling, failed requests,
console/page errors, DOM defects beyond both current caps, top-aligned
variable-height cards, sideways/RTL layout, breakpoint boundaries, and a
deep/wide DOM benchmark. Capture exact current status and false finding behavior
without accepting it as correct.

**Verify**: targeted regression tests fail on current readiness/cap/alignment
behavior; benchmark records a baseline.

### Step 2: Define scenario and readiness contracts

Create immutable scenario types for route, viewport policy, readiness policy,
ordered actions, expected state, and capture points. Supported actions should
remain deliberately small: click, fill, key, wait-for-selector/state, and
capture. Readiness supports explicit selector/app hook, mutation-idle, bounded
request-idle, and settle fallback with recorded degradation.

Scenario secrets are environment-variable references only and are redacted by
plan 013. Default invocation creates one initial-state scenario.

**Verify**: scenario parsing rejects unknown actions, path escapes, inline
secrets, and unbounded waits.

### Step 3: Make runtime status reflect completeness

Replace binary current/absent with `current`, `degraded`, `partial`, `failed`,
and `absent`. Persist requested/completed route × viewport × state matrix,
readiness outcome, navigation/tool errors, candidate/eligible/emitted counts,
cap/truncation details, and timestamps. Plan 015 scoring/finalization must reject
degraded/partial/failed required evidence. Tighten the canonical finding and
scan trust gates to accept runtime evidence only when status is exactly
`current`; do not couple runtime completeness to source-manifest freshness.

**Verify**: one success plus one failed capture is partial, never current;
network-idle timeout without alternate readiness is degraded; degraded,
partial, failed, and stale maps cannot qualify finding verification or scan
findings.

### Step 4: Capture browser diagnostics and interaction states

Collect console errors, page errors, failed requests, relevant HTTP failures,
and action failures with scenario/source provenance. Drive mapped routes and
explicit scenarios for loading, empty, error, success, modal, focus, disabled,
and authenticated states where fixtures declare them. Do not guess credentials
or click destructive controls automatically.

**Verify**: each fixture state and diagnostic produces a typed finding or
explicit coverage record.

### Step 5: Replace silent caps with prioritized bounded traversal

Prioritize interactive, text, structural, clipped/scrolling, visible, and
source-owned elements. Persist total/candidate/selected counts and a coverage
finding when budget is exceeded. Allow configurable budgets with safe maximums;
do not claim full coverage after truncation.

**Verify**: defects before and after former cap boundaries are found or the
artifact explicitly reports uncovered evidence.

### Step 6: Consolidate geometry and fix alignment

Measure rect/style/scroll/ancestor relationships once per element. Build cached
parent/child and clipping chains; compute bottom-up aggregate geometry. Preserve
zero peer-anchor deviation: if top, center, or bottom forms a valid aligned
cluster, suppress misalignment for that axis. Share logical-axis handling for
horizontal, vertical, sideways, and RTL modes.

**Verify**: variable-height top-aligned cards are clean; true outlier remains a
finding; benchmark improves materially or at minimum does not regress.

### Step 7: Unify responsive policy

Replace map/capture constants with one configurable viewport registry. Add
adversarial widths immediately below/above discovered media/container-query
boundaries plus text zoom and long-localization fixtures. Preserve existing
viewport aliases during state migration only.

**Verify**: map and capture consume identical viewport metadata and breakpoint
cases.

### Step 8: Delete legacy paths and document the contract

Remove duplicated observer/capture viewport logic, repeated geometry scans,
binary status assumptions, and dead initial-state-only helpers. Document
scenario safety, readiness, coverage, and status semantics.

**Verify**: grep confirms one observer engine, viewport registry, axis helper,
and geometry cache; browser/calibration/full suites pass. Report production
line additions/deletions against `d0ec3b0`; justify any net growth and prove
superseded code was deleted.

## Test plan

- Scenario schema/action safety and environment-only secrets.
- Readiness outcomes and partial/degraded status.
- Exact-current trust gates for finding verification and scan findings.
- Browser console/page/network diagnostics.
- Loading/empty/error/modal/focus/auth state captures.
- DOM budget coverage.
- Alignment, clipping, spacing, sideways/RTL correctness.
- Responsive boundary/text-zoom/long-text cases.
- Deep/wide DOM performance and no orphan browser/server processes.

## Done criteria

- [x] Initial capture is implemented as the default scenario.
- [x] Runtime status proves matrix/readiness/coverage completeness.
- [x] Browser and interaction failures become typed findings.
- [x] No silent DOM truncation remains.
- [x] Valid zero-deviation alignment is preserved.
- [x] Geometry/styles are measured through one cached pass.
- [x] One viewport and writing-mode policy remains.
- [x] Production delta and benchmark are reported.
- [x] Focused, browser, calibration, full, Ruff, compile, wheel, install, and
      CLI smoke gates pass.
- [x] No orphan browser/server processes remain after verification.

## STOP conditions

- Plans 015 or 016 are incomplete.
- Approved Plan 017 commit `d0ec3b0` is unavailable or its runtime/map
  contracts cannot be preserved.
- Scenario execution needs real credentials or public network.
- A generic state crawler cannot avoid destructive actions; retain explicit
  scenarios and report the limitation.
- Geometry rewrite changes qualified clipping/spacing behavior without corpus
  evidence.

## Maintenance notes

New runtime detectors consume scenario evidence and cached measurements. They
must expose coverage and readiness, not infer trust from page count.
