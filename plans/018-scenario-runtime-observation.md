# Plan 018: Replace initial-frame capture with efficient scenario observation

> **Executor instructions**: Extend the existing observer into one scenario
> engine; do not retain separate initial-state and scenario capture paths.
> Consolidate viewport, writing-mode, geometry, readiness, and coverage policy.
> Delete superseded passes. Update `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/frontend_map.py uidetox/commands/map.py uidetox/commands/capture.py uidetox/workflow.py tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_capture.py tests/test_calibration_matrix.py`

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/015-unified-findings-and-verified-closure.md`, `plans/016-application-semantics-and-source-ownership.md`
- **Category**: direction
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

The observer samples only initial rendered state. A swallowed network-idle
timeout plus a default 250 ms wait can capture skeleton/hydrating content, yet
any successful page marks runtime evidence current. Large DOMs are silently
capped. Alignment drops valid zero-deviation anchors. Repeated descendant,
ancestor, style, and rectangle scans increase cost on the complex applications
UIdetox most needs to understand.

## Current state

- `uidetox/runtime_observer.py:145-223` documents and executes initial-state
  observation across URL × viewport.
- `uidetox/runtime_observer.py:263-280` catches network-idle timeout, waits the
  fixed settle interval, and measures anyway.
- `uidetox/frontend_map.py:639-651` marks any non-empty runtime page set
  `current` while separately storing errors.
- `uidetox/runtime_observer.py:411-412` and `:1064-1069` silently cap DOM
  candidates at 3,000 and 1,500.
- `uidetox/runtime_observer.py:967-1011` discards zero anchor deviations before
  selecting the smallest remaining peer deviation.
- `uidetox/runtime_observer.py:719-826` repeatedly walks ancestors and
  descendants with layout reads.
- `uidetox/runtime_observer.py:42-46` and
  `uidetox/commands/capture.py:43-48` define different viewport sets.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Runtime | `python -m pytest -q -W error tests/test_runtime_observer.py tests/test_frontend_mapping.py` | all pass |
| Capture | `python -m pytest -q -W error tests/test_capture.py tests/test_visual_evidence.py` | all pass |
| Browser | `python -m pytest -q -W error -m browser` | deterministic pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | runtime TP/FP/FN stable |
| Full | `python -m pytest -q -W error` | exit 0 |

## Scope

**In scope**:
- `uidetox/runtime_observer.py`
- `uidetox/runtime_layout.py`
- `uidetox/frontend_map.py`
- `uidetox/commands/map.py`
- `uidetox/commands/capture.py`
- `uidetox/workflow.py`
- `tests/test_runtime_observer.py`
- `tests/test_frontend_mapping.py`
- `tests/test_capture.py`
- `tests/test_visual_evidence.py`
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
- One viewport registry serves map, capture, screenshots, and evidence metadata.
- One writing-mode/logical-axis helper serves measurement and finding policy.
- Replace repeated DOM geometry/style walks with one cached measurement pass.
- Remove silent array slicing; bounded traversal must expose coverage.
- Record benchmark duration and production JavaScript/Python line deltas.

## Git workflow

- Branch: `codex/018-scenario-runtime-observation`
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
partial/failed required evidence.

**Verify**: one success plus one failed capture is partial, never current;
network-idle timeout without alternate readiness is degraded.

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
and geometry cache; browser/calibration/full suites pass.

## Test plan

- Scenario schema/action safety and environment-only secrets.
- Readiness outcomes and partial/degraded status.
- Browser console/page/network diagnostics.
- Loading/empty/error/modal/focus/auth state captures.
- DOM budget coverage.
- Alignment, clipping, spacing, sideways/RTL correctness.
- Responsive boundary/text-zoom/long-text cases.
- Deep/wide DOM performance and no orphan browser/server processes.

## Done criteria

- [ ] Initial capture is implemented as the default scenario.
- [ ] Runtime status proves matrix/readiness/coverage completeness.
- [ ] Browser and interaction failures become typed findings.
- [ ] No silent DOM truncation remains.
- [ ] Valid zero-deviation alignment is preserved.
- [ ] Geometry/styles are measured through one cached pass.
- [ ] One viewport and writing-mode policy remains.
- [ ] Production delta and benchmark are reported.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- Plans 015 or 016 are incomplete.
- Scenario execution needs real credentials or public network.
- A generic state crawler cannot avoid destructive actions; retain explicit
  scenarios and report the limitation.
- Geometry rewrite changes qualified clipping/spacing behavior without corpus
  evidence.

## Maintenance notes

New runtime detectors consume scenario evidence and cached measurements. They
must expose coverage and readiness, not infer trust from page count.
