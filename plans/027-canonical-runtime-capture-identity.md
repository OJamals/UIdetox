# Plan 027: Canonical runtime capture identity

## Status

DONE

## Magic moment

Every runtime capture record rejects an identity that its own scenario, state,
URL, and viewport cannot reproduce. Legacy page-only observations are upgraded
to that identity once, before they become capture records. Prototype handoff
generation then reuses the canonical record model instead of maintaining
capture-ID math of its own.

## Measured baseline

Live baseline on 2026-07-27:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` were
  identical at `f21f7d84aac564a20ef40b76dcca9fe111dc976f`;
- root was clean; one worktree; local and remote contained only `master`;
- Plan 015/016 archival stashes remained exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no pytest, benchmark, qualification, Playwright, Vite, or Uvicorn process
  was running;
- 140 focused warning-strict tests passed with cache disabled in 17.87 seconds;
- `RuntimeCaptureRecord` has 20 inbound graph references and a CRITICAL
  constructor blast radius through the observer, map command, capture command,
  benchmark, and tests;
- `_legacy_capture` has one CRITICAL caller:
  `RuntimeObservation.__post_init__`;
- production has three direct `RuntimeCaptureRecord` construction paths; the
  two scenario-observer paths already use `runtime_capture_id`;
- tests have five direct construction paths with synthetic IDs;
- four tracked calibration JSON files use descriptive `RuntimePage.capture_id`
  values, but load only as standalone pages and never as capture records;
- preserved artifact scan found 35 canonical capture-record occurrences:
  Plan 022 has 15 and final Plan 026 has 20;
- preserved artifact scan found 20 noncanonical capture-record occurrences:
  Plan 025 run/recovery have 16 and aborted Plan 026 run 1 has 4;
- final Plan 026 artifacts are canonical and must remain replayable;
- noncanonical archived artifacts remain exact historical evidence and must not
  be rewritten or silently accepted as executable captures.

## Root cause

`runtime_capture_id` is canonical only by convention. `RuntimeCaptureRecord`
validates status but accepts any `capture_id`, so direct construction and
deserialization can create records that the runtime observer can never emit.
Plan 026 compensated at the prototype boundary with a second implementation of
the identity equation.

The page-only compatibility path preserves any non-empty
`RuntimePage.capture_id` and promotes it into a synthetic
`RuntimeCaptureRecord`. That lets descriptive or stale page labels become
executable capture identities. Standalone `RuntimePage` calibration fixtures
do not need record identity and must remain usable.

## Architecture decision

- Put the executable identity invariant in
  `RuntimeCaptureRecord.__post_init__`, using the existing
  `runtime_capture_id` function and the record's own fields.
- Make page-only `RuntimeObservation` construction replace supplied or missing
  page IDs with canonical IDs before `_legacy_capture` runs.
- Keep modern observer pages linked to their supplied canonical capture record;
  do not derive their foreign key from redirected page metadata.
- Delete `_legacy_capture`'s `page.capture_id or runtime_capture_id(...)`
  allowance. It consumes only normalized pages.
- Replace prototype-specific identity calculation with
  `RuntimeCaptureRecord.from_dict`, preserving one model and one error.
- Leave standalone `RuntimePage` construction permissive for detector
  calibration; identity becomes executable only when an observation creates a
  capture record.
- Do not rewrite archived Plan 025/026 artifacts. Record the intentional replay
  boundary: canonical final artifacts pass; noncanonical historical attempts
  fail the new invariant.
- Add no cache, graph, evidence type, wrapper, renderer model, or parallel
  validator.

## Tasks

### Task 1: Freeze canonical-record and legacy-page failures

**Acceptance criteria:**

- [x] Direct noncanonical `RuntimeCaptureRecord` construction fails with
      expected and actual IDs.
- [x] `RuntimeCaptureRecord.from_dict` enforces the same invariant.
- [x] A page-only observation replaces a descriptive page ID with the
      canonical identity and creates a matching record.
- [x] A page cannot reference an ID absent from supplied capture records.
- [x] A prototype redesign containing a noncanonical capture fails through
      `RuntimeCaptureRecord`, not duplicate ID math.
- [x] Standalone calibration pages keep loading.

**Verification:**

- [x] New focused tests fail before production changes.

**Dependencies:** None

**Files likely touched:**

- `tests/test_runtime_observer.py`
- `tests/test_redesign_planning.py`
- `tests/test_frontend_mapping.py`

**Estimated scope:** Small

### Task 2: Centralize identity and delete the allowance

**Acceptance criteria:**

- [x] Every constructed capture record is executable from its own fields.
- [x] Page-only compatibility construction canonicalizes once.
- [x] `_legacy_capture` contains no fallback or identity calculation.
- [x] Prototype code contains no independent capture-ID calculation.
- [x] Existing scenario observation and final Plan 026 replay remain exact.

**Verification:**

- [x] Focused runtime, mapping, redesign, calibration, and finding tests pass
      warning-strict with cache disabled.

**Dependencies:** Task 1

**Files likely touched:**

- `uidetox/runtime_scenarios.py`
- `uidetox/runtime_observer.py`
- `uidetox/prototype.py`

**Estimated scope:** Small

### Task 3: Qualify persisted-artifact boundary

**Acceptance criteria:**

- [x] Final Plan 026 redesign, brief, FrontendMap, and runner report replay.
- [x] One preserved noncanonical Plan 025 redesign fails only with the canonical
      identity error.
- [x] Exact archived files remain hash-identical.
- [x] Plan 015/016 stashes remain unchanged.

**Verification:**

- [x] Before/after artifact manifests and targeted replay results are retained
      outside the repository.

**Dependencies:** Task 2

**Files likely touched:** External Plan 027 qualification artifacts only

**Estimated scope:** Small

### Task 4: Run repository, package, invariant, and review gates

**Acceptance criteria:**

- [x] Focused tests, full warning-strict pytest, scoped Ruff/format,
      `compileall`, wheel/sdist build and metadata, fresh install, 82 module
      imports, CLI smoke, `pip check`, invariants, and `git diff --check` pass.
- [x] Multi-axis review approves exact scope.
- [x] Production/test/docs/total LOC, deletions, hashes, distributions,
      remaining risks, and next plan are recorded.
- [x] Production LOC is lower unless evidence proves unavoidable growth.

**Verification:**

- [x] Every gate has exact command evidence.

**Dependencies:** Task 3

**Files likely touched:**

- this plan
- `plans/README.md`

**Estimated scope:** Small

### Task 5: Integrate and prove parity

**Acceptance criteria:**

- [x] Commit only reviewed passing scope.
- [x] Merge to `master`, push, refresh graph after source commit, and prove
      `HEAD == master == origin/master == remote refs/heads/master`.
- [x] Remove the short-lived branch only after parity.
- [x] No release, tag, or PyPI action occurs.

**Verification:**

- [x] Final Git/worktree/branch/stash/process/remote rebaseline passes.

**Dependencies:** Task 4

**Files likely touched:** None

**Estimated scope:** Small

## Done criteria

- [x] Runtime capture identity is a record invariant, not a caller convention.
- [x] Page-only compatibility cannot promote arbitrary IDs.
- [x] Prototype handoff code owns no duplicate identity equation.
- [x] Canonical final artifacts replay; noncanonical archives fail explicitly.
- [x] No archived artifact or stash is rewritten or dropped.
- [x] Full repository/package/invariant/review gates pass.
- [x] Production code finishes smaller.
- [x] Local/origin/server SHA parity is proven.

## Execution results

Completed implementation and qualification on 2026-07-27. Implementation
commit `e6ce2e5` was merged and pushed; the refreshed graph contains 6,031 nodes
and 25,164 edges.

### Root-cause fixes

- `RuntimeCaptureRecord.__post_init__` now recomputes the only executable
  capture ID from the record's scenario, state, URL, and viewport. Direct
  construction and `from_dict` reject the same noncanonical record with exact
  expected/actual evidence.
- Page-only `RuntimeObservation` construction now replaces both missing and
  descriptive IDs before synthesizing capture records. `_legacy_capture`
  contains no fallback or identity calculation.
- Observations with supplied capture records now reject page foreign keys that
  match no record, preventing canonical capture matrices from coexisting with
  unrelated runtime graph IDs.
- Prototype handoff validation now deserializes the existing
  `RuntimeCaptureRecord`; its independent `RuntimeViewport` reconstruction and
  `runtime_capture_id` equation were deleted.
- Red tests first proved both defects: noncanonical record construction did not
  raise, and a page-only observation retained `checkout-ready` instead of
  `checkout:ready:desktop:01d907100080`.

### Persisted-artifact qualification

- Capture-record population: 35 canonical occurrences and 20 noncanonical
  historical occurrences. Canonical distribution: Plan 022 = 15, final
  Plan 026 = 20. Noncanonical distribution: Plan 025 run/recovery = 16,
  aborted Plan 026 run 1 = 4.
- Four tracked runtime-design calibration fixtures retain descriptive
  standalone `RuntimePage.capture_id` values. They never construct a capture
  record and all calibration tests pass.
- Final Plan 026 brief replay is byte-identical:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Two uncontended Plan 026 runner replays are byte-identical to the preserved
  report:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Preserved Plan 025 replay exits 1 only with:
  `expected 'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'`.
- Before/after archive manifests match. No archived artifact or stash changed.
  Exact Plan 027 evidence lives at
  `/Users/omar/Documents/Projects/.uidetox-qualification/027`.

### Repository and package gates

- 143 focused warning-strict tests and 1,443 full warning-strict tests passed;
  pytest cache was disabled. Final full-suite wall time was 26.42 seconds.
- Scoped Ruff E/F/I, Ruff format, full `compileall`, and `git diff --check`
  passed.
- Final wheel/sdist build, fresh wheel install, metadata, 82 module imports,
  CLI version/map/redesign/prototype smokes, checkout/install brief parity, and
  `pip check` passed.
- Wheel:
  `26559e2a90416b4a0e5fdeb2d4839242925d88dfe8a835c3239f5449ee818ffe`.
- Sdist:
  `6ed3240793cf79a15a5566035c327e53fbdb5950d5acbec6a454a2a728886efa`.
- Multi-axis correctness/readability/architecture/security/performance review:
  APPROVE. No dependency, cache, graph, evidence type, compatibility wrapper,
  or renderer model was added.

### Scope and next plan

- Production delta: 22 insertions, 23 deletions, net -1 LOC. Deleted code is
  the legacy page-ID fallback and prototype-specific capture-ID equation.
- Tests: 169 insertions, 41 deletions, net +128 LOC. Plan/docs: net +300 LOC.
  Total excluding graph binary refresh: net +427 LOC.
- Remaining risk: an observation can still contain duplicate canonical capture
  records, and successful redirected pages retain resolved page URLs while
  capture records identify requested scenario URLs.
- Next Plan 028 should first measure duplicate-capture and redirect behavior,
  then enforce one observation-level capture key and explicit
  requested-versus-resolved URL semantics without another identity model.

## STOP conditions

Stop without integration if:

- canonical final Plan 026 artifacts fail for a reason other than a discovered
  root-cause defect;
- enforcing the record invariant requires a new parallel runtime model or
  compatibility wrapper;
- archived evidence would need mutation to pass;
- Plan 015/016 stash reconciliation lacks explicit source-level evidence;
- any required gate remains flaky, contested, or unexplained.
