# Plan 028: Runtime capture uniqueness and redirect semantics

## Status

DONE

## Magic moment

Every runtime observation has one record and at most one rendered page for each
canonical capture ID. Capture records identify the requested scenario URL;
rendered pages retain the resolved browser URL after redirects. Persisted maps,
redesigns, and prototype handoffs preserve that distinction without a second
identity equation or evidence model.

## Measured baseline

Live baseline on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` were
  identical at `60d28175d63ab3288d78c3a278e9ba652cd63e5c`;
- root was clean; one worktree; local and remote contained only `master`;
- Plan 015/016 archival stashes remained exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, benchmark, Playwright, or Chromium process was running;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contained
  6,021 nodes and 25,556 edges;
- `RuntimeObservation` has a CRITICAL constructor blast radius through the
  observer, map, capture, benchmark, FrontendMap, redesign, prototype, and
  finding-verification paths;
- a direct observation accepted two identical `RuntimeCaptureRecord` rows:
  2 rows, 1 unique capture ID, status `current`;
- `validate_runtime_observation_plan` also accepted two scenarios that produce
  the same capture key;
- a warning-strict focused audit passed 180 tests and observed 60
  `RuntimeObservation` instances, 91 capture rows, and 85 pages with zero
  duplicate capture rows, zero duplicate page rows, zero unrequested capture
  URLs, and zero page scenario/state/viewport mismatches;
- that same audit reproduced two redirected pages: capture records retained
  requested `http://127.0.0.1:4173`, pages retained resolved
  `http://127.0.0.1:4173/projects`, and both remained joined by the same
  canonical `capture_id`;
- 16 preserved qualification matrices contained 55 rows and zero duplicate
  IDs: Plan 022 had 15 canonical rows, final Plan 026 had 20 canonical rows,
  and Plan 025 plus aborted Plan 026 attempts had 20 intentionally
  noncanonical rows;
- every persisted capture URL appeared in its sibling `runtime_urls` or `urls`
  list;
- tracked calibration JSON contains no observation or capture-matrix artifact;
  standalone descriptive `RuntimePage.capture_id` fixtures remain outside the
  executable observation boundary.

## Root cause

`RuntimeCaptureRecord` proves that one row's ID is executable, but
`RuntimeObservation` treats capture IDs as set membership only. It therefore
accepts duplicate records, duplicate rendered pages, and pages whose scenario,
state, or viewport disagrees with the record named by `page.capture_id`.

The observer already assigns two deliberate URL roles:

- `RuntimeCaptureRecord.url` is the requested scenario URL and participates in
  `runtime_capture_id`;
- `RuntimePage.url` is `page.url` after navigation and may be the resolved
  redirect destination.

That distinction is not asserted at the observation boundary. Prototype
handoff validation also deserializes capture rows individually, so a duplicate
matrix remains acceptable even though it cannot represent one observation key.

## Architecture decision

- Make `RuntimeObservation` the only observation-level key boundary.
- Require unique `RuntimeCaptureRecord.capture_id` values and at most one
  `RuntimePage` per capture ID.
- Require supplied capture-record URLs to belong to
  `RuntimeObservation.requested_urls`.
- Require each page to match its record's scenario, state, and viewport.
- Intentionally exclude URL from the page/record equality check:
  `RuntimeCaptureRecord.url` remains requested; `RuntimePage.url` remains
  resolved.
- Keep `runtime_capture_id` unchanged and based only on the requested record
  fields.
- Keep page-only legacy construction compatible: it has no requested capture
  record, so its page URL remains the only reproducible URL and is normalized
  once before `_legacy_capture`.
- Replace prototype row-by-row validation with construction through the
  existing `RuntimeObservation.from_dict` boundary using the existing runtime
  URLs and capture matrix.
- Keep `FrontendMap` and `RedesignSet` persistence schemas unchanged. Their raw
  evidence dictionaries remain loadable; executable prototype handoff is the
  typed enforcement boundary.
- Add no identity model, cache, graph, evidence type, renderer model, wrapper,
  fallback, or schema migration.

## Tasks

### Task 1: Freeze duplicate and redirect behavior

**Acceptance criteria:**

- [x] Duplicate capture records fail with the duplicated canonical ID.
- [x] Duplicate rendered pages fail with the duplicated canonical ID.
- [x] A page whose scenario, state, or viewport disagrees with its referenced
      record fails.
- [x] A supplied capture URL absent from `requested_urls` fails.
- [x] A redirected page succeeds when only page URL differs from its record.
- [x] Page-only legacy observation and standalone calibration pages remain
      compatible.
- [x] Prototype handoff rejects a duplicate runtime capture matrix through
      `RuntimeObservation`, not duplicate validation math.

**Verification:**

- [x] New focused tests fail before production changes.

**Dependencies:** None

**Files likely touched:**

- `tests/test_runtime_observer.py`
- `tests/test_redesign_planning.py`

**Estimated scope:** Small

### Task 2: Enforce one observation key and explicit URL roles

**Acceptance criteria:**

- [x] `RuntimeObservation` owns capture and page uniqueness.
- [x] Page-to-record validation compares scenario, state, and viewport while
      deliberately preserving resolved page URLs.
- [x] Supplied records are tied to requested observation URLs.
- [x] Prototype validation reuses `RuntimeObservation.from_dict`.
- [x] Runtime plan preflight reuses `runtime_capture_id` and rejects duplicate
      execution keys before Playwright launch.
- [x] No production path owns a second capture-ID or observation-key equation.
- [x] Redundant prototype validation code/imports are deleted.

**Verification:**

- [x] Focused runtime, mapping, redesign, capture, finding, and qualification
      tests pass warning-strict with cache disabled.

**Dependencies:** Task 1

**Files likely touched:**

- `uidetox/runtime_observer.py`
- `uidetox/runtime_scenarios.py`
- `uidetox/prototype.py`

**Estimated scope:** Small

### Task 3: Qualify persisted-artifact and handoff boundaries

**Acceptance criteria:**

- [x] Final Plan 026 FrontendMap, redesign, brief, and report replay.
- [x] Canonical Plan 022/026 matrices remain unique and executable.
- [x] Preserved noncanonical Plan 025/026 attempts still fail only with the
      canonical identity error.
- [x] Duplicate synthetic redesign fails at prototype handoff.
- [x] Exact archived files and Plan 015/016 stashes remain hash-identical.

**Verification:**

- [x] Before/after archive manifests and targeted replay evidence are retained
      outside the repository.

**Dependencies:** Task 2

**Files likely touched:** External Plan 028 qualification artifacts only

**Estimated scope:** Small

### Task 4: Run repository, package, invariant, and review gates

**Acceptance criteria:**

- [x] Focused tests, full warning-strict pytest, scoped Ruff/format,
      `compileall`, wheel/sdist build and metadata, fresh install, 82 module
      imports, CLI smokes, `pip check`, invariants, and `git diff --check` pass.
- [x] Two uncontended qualification replays match the canonical report SHA.
- [x] Multi-axis correctness/readability/architecture/security/performance
      review approves exact scope.
- [x] Production/test/docs/total LOC, deletions, hashes, distributions,
      remaining risks, and next plan are recorded.
- [x] Production LOC growth is explicitly evidenced: four new observation
      invariants and one preflight invariant require distinct errors; no new
      function, type, model, cache, graph, wrapper, or fallback was added.

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

- [x] One capture ID names one observation record and at most one page.
- [x] Requested capture URLs and resolved page URLs remain explicit and
      correctly joined.
- [x] Prototype handoff enforces the same observation boundary.
- [x] Canonical final artifacts replay; noncanonical archives fail explicitly.
- [x] No archived artifact or stash is rewritten or dropped.
- [x] Full repository/package/invariant/review gates pass.
- [x] Production growth is evidenced and bounded to existing functions.
- [x] Local/origin/server SHA parity is proven.

## Execution results

- Red evidence: seven new observation/prototype cases failed before the first
  production edit; duplicate-plan preflight then failed independently before
  its implementation.
- Final warning-strict pytest: 187 focused tests and 1,450 full-suite tests
  passed with the cache provider disabled.
- Scoped Ruff `E4/E7/E9/F/I`, Ruff format, `compileall`, and
  `git diff --check` passed.
- Fresh package gates passed: build, metadata, clean install, 82 imports, CLI
  smokes, and `pip check`.
- Final wheel SHA-256:
  `70ccdb692c5e15286f92c63d2b712ab87abf3896590bcc79d2098acb6618d269`.
- Final sdist SHA-256:
  `5decd3428d2b0cfcfb6741bdd3d3e168d5ada4294933e847f13382a1faf635b3`.
- Installed canonical prototype brief remained byte-identical at
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Two uncontended qualification replays both matched
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Persisted distribution remained 16 matrices / 55 rows / 0 duplicate rows:
  35 canonical final rows and 20 intentionally noncanonical historical rows.
- All seven preserved archive manifests and both archival stash object IDs
  remained exact.
- Source commit `acc9742ad4f8430840e648e5ac622fce97011297` preceded graph
  refresh commit `254634fa6b0d411b72fa9c54dfeeb712910741e7`; the refreshed graph
  contains 6,026 nodes and 25,633 edges.
- LOC: production `+75/-22`; tests `+150/-0`; plans/docs `+291/-0`; total `+516/-22`.
  Production function count remained unchanged.
- Removed/replaced: prototype-specific row validation and direct
  `RuntimeCaptureRecord` dependency; set-only page foreign-key validation;
  integer-only preflight capture counting.
- Review verdict: **APPROVE** across correctness, readability, architecture,
  security, and performance. Runtime loops remain bounded by the existing
  capture-matrix policy.
- Remaining risk: standalone `RuntimePage` fixtures remain intentionally
  permissive until wrapped in `RuntimeObservation`; historical noncanonical
  matrices remain intentionally non-executable.
- Plan 029 recommendation: consolidate runtime observation completeness and
  status derivation around the now-canonical capture index, measuring first for
  duplicate page/capture scans and preserving the same serialized schemas.

## STOP conditions

Stop without integration if:

- canonical final Plan 026 artifacts fail for a reason other than a discovered
  root-cause defect;
- redirect semantics require renaming serialized `url` fields, adding a
  compatibility fallback, or creating another runtime model;
- legacy page-only compatibility requires guessing a requested URL;
- archived evidence would need mutation to pass;
- Plan 015/016 stash reconciliation lacks explicit source-level evidence;
- any required gate remains flaky, contested, or unexplained.
