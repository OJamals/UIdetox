# Plan 015: Replace fragmented issue handling with verified finding lifecycle

> **Executor instructions**: This is a replacement migration. Introduce the new
> typed finding path, move every producer/consumer, then delete superseded issue
> translation, lifetime-score, and duplicate eligibility code. Never leave old
> and new pipelines active together. Update `plans/README.md` when done.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- uidetox/analyzer_engine.py uidetox/runtime_layout.py uidetox/project_map.py uidetox/commands/scan.py uidetox/commands/map.py uidetox/commands/next.py uidetox/commands/batch_resolve.py uidetox/commands/review.py uidetox/commands/status.py uidetox/commands/finish.py uidetox/state.py uidetox/utils.py uidetox/workflow.py tests`

## Status

- **Priority**: P0
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/013-secure-evidence-boundaries.md`, `plans/014-calibration-and-qualification-matrix.md`
- **Category**: tech-debt
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

Static issues enter the queue, while runtime layout and full-stack parity
findings are only printed or embedded in map artifacts. Resolution verifies
compiler/linter/formatter status rather than the originating detector. The
objective score rewards all historical resolutions, the subjective score is a
stale scalar, and `finish` has a separate weaker gate. These seams permit a
clean queue and high score without proving the application is clean.

## Current state

- `uidetox/analyzer_engine.py:39-63` returns anonymous dictionaries and only the
  first standard regex occurrence per file.
- `uidetox/commands/scan.py:480-528` serializes and queues only static analyzer
  output.
- `uidetox/commands/scan.py:552-576` prints `ProjectMap` parity counts without
  queueing findings.
- `uidetox/commands/map.py:65-76` prints rendered finding counts without adding
  them to the remediation lifecycle.
- `uidetox/commands/batch_resolve.py:24-189` runs tsc/lint/format only.
- `uidetox/utils.py:175-219` computes objective score from pending plus lifetime
  resolved issue weights.
- `uidetox/commands/review.py:279-291` stores a scalar score/timestamp.
- `uidetox/workflow.py:515-536` has eligibility checks not enforced by
  `uidetox/commands/finish.py:83-116`.

Existing compatibility boundary: state files under `.uidetox/` must load
without destructive read-time rewrites.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| State/lifecycle | `python -m pytest -q -W error tests/test_state_persistence.py tests/test_status.py tests/test_review.py tests/test_finish.py tests/test_workflow.py` | all pass |
| Producers | `python -m pytest -q -W error tests/test_regressions.py tests/test_runtime_observer.py tests/test_project_mapping.py tests/test_frontend_mapping.py` | all pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | no unclassified FP/FN |
| Full | `python -m pytest -q -W error` | exit 0 |

## Scope

**In scope**:
- `uidetox/findings.py` (create)
- `uidetox/analyzer_engine.py`
- `uidetox/runtime_layout.py`
- `uidetox/project_map.py`
- `uidetox/commands/scan.py`
- `uidetox/commands/map.py`
- `uidetox/commands/next.py`
- `uidetox/commands/batch_resolve.py`
- `uidetox/commands/review.py`
- `uidetox/commands/status.py`
- `uidetox/commands/finish.py`
- `uidetox/state.py`
- `uidetox/utils.py`
- `uidetox/workflow.py`
- `tests/test_findings.py` (create)
- `tests/test_state_persistence.py`
- `tests/test_status.py`
- `tests/test_review.py`
- `tests/test_finish.py`
- `tests/test_workflow.py`
- `tests/test_regressions.py`
- `tests/test_runtime_observer.py`
- `tests/test_project_mapping.py`
- `tests/test_frontend_mapping.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/finding-lifecycle.md` (create)

**Out of scope**:
- New parser coverage; plan 016 owns it.
- New contract semantics; plan 017 owns them.
- New runtime/design detectors; plans 018-019 own them.
- Changing established rule IDs or severities without calibration evidence.

## Cleanup and replacement constraints

- One canonical `Finding` model; no parallel static/runtime/parity issue types at
  lifecycle boundaries.
- One canonical eligibility evaluator consumed by status, workflow, and finish.
- One scoring implementation based on current evidence; delete or shrink
  `compute_design_score` once callers migrate.
- Remove producer-specific queue translation after migration.
- Preserve backward loading through a narrow migration adapter; do not retain
  two mutable state schemas.
- Record production line counts before/after. New typed code should replace at
  least the duplicated translation/eligibility/scoring code it supersedes.

## Git workflow

- Branch: `codex/015-verified-finding-lifecycle`
- Commit in safe slices: model/compatibility, producers, occurrence handling,
  resolver/verifiers, score/review, finish/cleanup.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Freeze current state and output contracts

Add fixtures for legacy state, current scan JSON, GitHub annotations, `next`
packets, runtime/parity artifacts, score calculation, and finish eligibility.
Include incomplete and stale evidence. Do not bless current false-success
behavior; mark expected migration changes explicitly.

**Verify**: focused baseline tests pass before production edits.

### Step 2: Define one immutable typed finding

Create a frozen model containing:

- stable fingerprint from detector ID, source/runtime/contract anchor, and
  normalized evidence;
- category, severity, confidence, message, and lifecycle status;
- provenance and evidence freshness;
- source/runtime/contract anchors;
- suppression key;
- verifier recipe and last verification result;
- sanitized display excerpt.

Use versioned `to_dict`/`from_dict`. Unknown fields survive round trips where
needed for forward compatibility. Apply plan 013 sanitization before model
construction.

**Verify**: exact serialization, fingerprint stability, sanitization, and
legacy migration tests pass.

### Step 3: Move all producers to the typed model

Adapt static analyzer, runtime layout, and parity findings at their producer
boundary. `scan --json`, GitHub output, map artifacts, queue state, and `next`
must consume the same objects. Ambiguous backend-only/unresolved evidence uses
`investigate`/informational policy, not an automatic defect.

Delete the old per-command dictionary reshaping once all callers migrate.

**Verify**: static, runtime, and parity findings appear in JSON/state/`next` with
stable IDs and correct provenance.

### Step 4: Preserve every standard-rule occurrence

Replace `pattern.search` with ordered safe iteration. Emit one finding per
distinct `(detector, file, match start, match end)` anchor. Handle zero-width
patterns without looping. Preserve the first occurrence's existing
line/column/snippet behavior. Presentation may group findings but must retain
all anchors.

**Verify**: calibration cases for multiple same-line and multi-line occurrences
pass; no secret bytes appear due to plan 013.

### Step 5: Verify the originating detector before resolution

Implement verifier dispatch from the finding recipe:

- static finding: rerun the specific rule against its file/anchor;
- runtime finding: require fresh scenario/route/viewport evidence;
- parity/contract finding: rebuild the relevant contract slice;
- manual subjective finding: require structured reviewer evidence.

`batch-resolve` may still run mechanical gates, but cannot mark a finding
resolved while its verifier reproduces it. Record explicit overrides separately
with actor, reason, and timestamp; never count override as verified resolution.

**Verify**: unchanged defects remain pending; changed anchors become stale and
require rescan; fixed defects resolve.

### Step 6: Replace lifetime scoring with evidence-bound scoring

Score a current scan snapshot using severity, confidence, qualified coverage,
and verified status. Historical resolved findings remain history only. Store
subjective review as A/B/C/D dimensions, rationale, finding links, routes,
states, viewports, reviewer, and source/map/runtime hashes. Mark review stale
when relevant hashes change.

Do not create an aesthetic score from image-diff magnitude.

**Verify**: adding old resolved history cannot raise a new snapshot's score;
source change stales subjective review.

### Step 7: Consolidate finalization eligibility

Create one evaluator returning typed blockers for pending findings, target
score, stale/incomplete evidence, missing structured review, dirty tree, and
branch/session requirements. Use it from status, workflow, and finish. Remove
the duplicate weaker checks.

**Verify**: direct `uidetox finish` rejects every state the workflow labels
ineligible and accepts the same eligible fixture.

### Step 8: Remove obsolete code and document migration

Delete old queue translation, lifetime score math, duplicated eligibility, and
dead issue-shape helpers. Keep only the legacy state reader needed for migration
and test it. Record the finding lifecycle ADR and state schema version.

**Verify**: `git grep` finds no old mutable issue schema construction outside
the migration adapter; full suite passes.

## Test plan

- Typed finding serialization/fingerprint/sanitization.
- Legacy state load and one-way write migration.
- Static/runtime/parity queue inclusion and outputs.
- Multiple occurrence anchors and deterministic ordering.
- Detector-specific resolution success/failure/staleness.
- Evidence-bound scoring and structured subjective review freshness.
- Shared workflow/status/finish eligibility.
- Calibration and full-suite regression.

## Done criteria

- [ ] One finding model crosses every lifecycle boundary.
- [ ] Static, runtime, and contract evidence reaches remediation.
- [ ] Resolution proves the originating finding absent.
- [ ] Scores use only current qualified evidence.
- [ ] Review evidence is structured and freshness-bound.
- [ ] Status, workflow, and finish share one eligibility evaluator.
- [ ] Superseded translation/scoring/eligibility code is deleted.
- [ ] Production-code delta is reported and justified.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- Plan 013 sanitization or plan 014 calibration is incomplete.
- A public state/output consumer cannot migrate from versioned JSON.
- Runtime or contract findings lack enough provenance to define a verifier;
  leave them informational and report the blocker.
- Consolidation would require keeping two active mutable lifecycle schemas.

## Maintenance notes

New detector families must implement the canonical model and verifier contract.
Reviewers should reject any producer-specific queue or score path. Historical
statistics must never influence current correctness.
