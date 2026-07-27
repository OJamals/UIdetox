# Plan 026: Deterministic v1 report validation and executable state qualification

## Status

DONE

## Magic moment

One isolated disposable agent consumes one generated full-stack brief. The
existing Plan 023 runner then proves, without provider-specific parsing, that
the agent's v1 report preserves every ordered runtime-state handoff and that a
controller-owned `FrontendMap` contains one real completed page and screenshot
for every declared state.

## Measured baseline

Live baseline on 2026-07-27:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` were
  identical at `7eb35adcfa28bbe3c6b301e2cb8dc00fa2b3a099`;
- root was clean; one worktree; local and remote contained only `master`;
- Plan 015/016 archival stashes remained exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no pytest, qualification, Playwright, Vite, or Uvicorn process was running;
- `tests/test_handoff_qualification.py`: 17 passed warning-strict with cache
  disabled;
- existing runner: 993 lines; attempt schema: 3,339 bytes;
- preserved Plan 025 final v1 report: 51,913 bytes, with four ordered
  `runtime_state_handoffs`;
- canonical Plan 025 redesign contains four ordered runtime captures:
  `authenticated`, `triggered`, `empty`, and `error`;
- deleting, reversing, or corrupting `runtime_state_handoffs` produces the
  exact same current runner result as the unmodified report;
- current result identities contain only contracts, source anchors, blockers,
  and runtime unknowns; runtime-state handoffs are ignored;
- `_stateful_screenshot_namer(None, scenario, state)` returns `None`, so the
  default runtime observer falls back to a viewport-only filename and
  overwrites distinct states captured at the same viewport.

Blast radius:

- `benchmarks.handoff_qualification.qualify` is CRITICAL through its CLI and 12
  direct tests;
- `_stateful_screenshot_namer` is CRITICAL through
  `_capture_scenario_state` and the shared runtime observer.

## Root cause

Plan 025 made the report contract authoritative in the generated brief, but the
Plan 023 runner still validates the older normalized boundary. It never detects
the v1 marker in the brief, never validates exact completed/stale v1 report
fields, and never projects `runtime_capture_matrix` into ordered report
identities.

The normalized browser evidence is viewport-oriented. It cannot prove multiple
semantic states sharing one viewport. The canonical `FrontendMap` already owns
that identity in `runtime_capture_matrix` and `runtime_page` nodes, so a second
state model would be redundant.

The shared observer already has state-aware filename logic, but only applies it
when a custom screenshot namer is supplied. Normal `uidetox map --runtime
--screenshots` calls therefore lose per-state screenshot identity.

## Architecture decision

Extend only `benchmarks/handoff_qualification.py` and its existing normalized
attempt schema:

- detect `uidetox.disposable-agent-attempt.v1` from the generated brief so a
  report cannot bypass validation by omitting its schema field;
- retain legacy Plan 022/023 replay behavior only for briefs that predate the
  v1 marker;
- project exact ordered `capture_id`, `scenario`, `state`, URL, and viewport
  identities from
  `proposal.evidence_freshness.runtime.runtime_capture_matrix`;
- validate completed and stale v1 top-level fields plus the report row shapes
  promised by the generated appendix;
- add optional `runtime.frontend_map` and `runtime.frontend_map_sha256` fields
  to the existing attempt boundary;
- when supplied, load that exact `FrontendMap`, verify its SHA-256, current
  runtime status, ordered capture matrix, one matching `runtime_page` node per
  capture, and one readable state-specific PNG per page;
- emit only relative screenshot identities and computed hashes in the
  deterministic result;
- keep HTTP, console, resource, and overflow acceptance in the existing
  normalized runtime object.

Fix the existing observer filename function so its default namer is state-aware.
Do not add a launcher, provider parser, report model, cache, graph, evidence
type, compatibility wrapper, or renderer-specific model.

## Tasks

### Task 1: Freeze v1 report and state-execution failures

**Acceptance criteria:**

- [x] Missing, extra, reordered, duplicated, or corrupted v1 handoffs fail.
- [x] Wrong v1 schema/status/top-level/nested fields fail deterministically.
- [x] Legacy pre-v1 fixture behavior remains covered.
- [x] Missing, stale, incomplete, duplicated, or screenshot-less runtime
      `FrontendMap` evidence fails.
- [x] Default multi-state screenshot names are proven to collide before the
      production fix.

**Verification:**

- [x] New focused tests fail for the measured root causes.

**Dependencies:** None

**Files likely touched:**

- `tests/test_handoff_qualification.py`
- `tests/test_runtime_observer.py`

**Estimated scope:** Medium

### Task 2: Extend the existing Plan 023 runner and schema

**Acceptance criteria:**

- [x] v1 is required when the brief declares it.
- [x] Completed/stale report shapes are exact and deterministic.
- [x] Every runtime-state handoff is accounted for in canonical order.
- [x] Optional executable evidence reuses one hashed `FrontendMap`.
- [x] State page identity and screenshot bytes are verified without absolute
      paths in output.
- [x] Legacy Plan 022/023 artifacts still replay.

**Verification:**

- [x] `tests/test_handoff_qualification.py` passes warning-strict.
- [x] Repeated qualification report bytes are identical.

**Dependencies:** Task 1

**Files likely touched:**

- `benchmarks/handoff_qualification.py`
- `benchmarks/handoff-qualification.schema.json`
- `tests/test_handoff_qualification.py`

**Estimated scope:** Medium

### Task 3: Repair default state-specific screenshot ownership

**Acceptance criteria:**

- [x] Default and custom namers produce distinct stable filenames for every
      non-default scenario/state.
- [x] Default/initial legacy filename behavior remains unchanged.
- [x] Existing browser and runtime observer tests pass.

**Verification:**

- [x] Focused runtime-observer tests pass warning-strict.

**Dependencies:** Task 1

**Files likely touched:**

- `uidetox/runtime_observer.py`
- `tests/test_runtime_observer.py`

**Estimated scope:** Small

### Task 4: Run isolated executable qualification

**Acceptance criteria:**

- [x] One generated full-stack brief is consumed in a fresh isolated agent
      directory with exact prompt and artifact hashes retained.
- [x] Agent output/report remain unchanged after the agent exits.
- [x] Controller starts one uncontended localhost server and executes the
      canonical states through `RuntimeScenario`.
- [x] `map_frontend` writes one canonical `FrontendMap` containing all ordered
      captures and state-specific screenshots.
- [x] Existing runner passes exact v1 report, source, contracts, anchors,
      blockers, unknowns, states, viewports, browser acceptance, and PNG gates.
- [x] Input context, output size, wall time, retries, recovery, and contract
      preservation accuracy distributions are recorded.

**Verification:**

- [x] Two runner invocations emit byte-identical reports.
- [x] Negative stale/corrupt/state-loss probes fail for the intended reason.

**Dependencies:** Tasks 2 and 3

**Files likely touched:**

- external Plan 026 qualification artifacts only

**Estimated scope:** Medium

### Task 5: Run repository, package, invariant, and review gates

**Acceptance criteria:**

- [x] Focused tests, full warning-strict pytest, scoped Ruff/format,
      `compileall`, wheel/sdist build and metadata, fresh install, 82 module
      imports, CLI smoke, `pip check`, invariants, and `git diff --check` pass.
- [x] Multi-axis review approves exact scope.
- [x] Production/test/docs/total LOC, deletions, hashes, distributions,
      failures, recovery, risks, and next plan are recorded.
- [x] Archival stashes remain exact.

**Verification:**

- [x] Every gate has an exact artifact or command result.

**Dependencies:** Task 4

**Files likely touched:**

- this plan
- `plans/README.md`

**Estimated scope:** Small

### Task 6: Integrate and prove parity

**Acceptance criteria:**

- [x] Commit only reviewed passing scope.
- [x] Merge to `master`, push, refresh graph after source commit, and prove
      `HEAD == master == origin/master == remote refs/heads/master`.
- [x] Remove short-lived branch only after parity.
- [x] No release, tag, or PyPI action occurs.

**Verification:**

- [x] Final Git/worktree/branch/stash/process/remote rebaseline passes.

**Dependencies:** Task 5

**Files likely touched:** None

**Estimated scope:** Small

## Done criteria

- [x] Existing runner enforces the emitted v1 contract.
- [x] All ordered runtime-state handoffs are exact.
- [x] One canonical `FrontendMap` proves executable state-specific captures.
- [x] Default multi-state screenshots cannot overwrite each other.
- [x] Historical pre-v1 replay remains valid.
- [x] No parallel validator/model/cache/graph/evidence/wrapper is added.
- [x] Full repository/package/invariant/review gates pass.
- [x] Archival stashes remain unchanged.
- [x] Local/origin/server SHA parity is proven.

## Execution results

Completed 2026-07-27.

### Root-cause fixes

- The Plan 023 runner ignored `runtime_state_handoffs`; base, missing,
  reversed, and corrupted state rows produced the same result. The runner now
  detects the trusted v1 marker after `END_UIDETOX_EVIDENCE`, validates exact
  stale/completed report shapes, and accounts ordered state identities.
- Default runtime capture naming ignored scenario/state whenever no custom
  namer was supplied. Default non-initial states now reuse the existing
  state-aware filename policy; default/initial naming remains unchanged.
- The first preserved Plan 025 brief contained synthetic capture IDs that
  `runtime_capture_id` could never emit. That preflight agent was interrupted
  before implementation, its zero-output boundary was retained, and a
  corrected map/brief was generated with the existing canonical ID function.
  `build_prototype_brief` now rejects non-executable capture identities.
- Live replay exposed a second defect: the first v1 validator modeled a
  synthetic test-only decision/command shape instead of the emitted appendix.
  The appendix and validator now share one exact completed shape, integer
  millisecond timings, explicit runtime acceptance, relative-path containment,
  canonical URL coupling, and status coupling.
- Review found and fixed bool-as-zero acceptance, prototype screenshot
  traversal, arbitrary FrontendMap roots, and mismatched blocked/passed
  acceptance status.

### Isolated-agent measurements

- Preflight boundary: `fork_turns=none`; prompt 970 bytes; brief 49,670 bytes;
  controlled input 50,640 bytes; zero output; interrupted before
  implementation because the four capture IDs were non-executable.
- Final boundary: `fork_turns=none`; prompt 1,123 bytes; brief 50,240 bytes;
  controlled input 51,363 bytes. Provider token telemetry was unavailable, so
  exact bytes—not fabricated token counts—are authoritative.
- Controlled-input byte distribution: samples `[50640, 51363]`; min 50,640;
  median/mean 51,001.5; p90 51,290.7; max 51,363.
- Final agent wall time: 310.603 seconds from recorded start to latest output
  mtime; one implementation attempt; zero agent retries.
- Prototype: one file, 42,281 bytes,
  `f2e8b21734a52b2cad6b4f5f315968844afa28947f0fb2123d4efca2abc5bd31`.
- Agent report: 71,137 bytes,
  `7561c41022ea24c91c48874688095091d307032d77a1be07c15ce536fb90ea8a`.
- Total final agent output: 113,418 bytes. Implementation-output distribution
  across preflight/final boundaries: `[0, 42281]`; total-output distribution:
  `[0, 113418]`.
- All 44 ordered mapped source files remained hash-identical. Original final
  agent attempt tree remained
  `2db2faf667ec8fce99300628c319bb4d7b633b7b6154575abf47f66354c6bcc0`
  after controller recovery.

### Executable qualification

- Controller used one server at `127.0.0.1:4173` and existing
  `RuntimeScenario`, `observe_frontend`, `map_frontend`, `FrontendMap`, and
  `runtime_capture_id` paths.
- Four ordered captures passed: authenticated/mobile, triggered/tablet,
  empty/desktop, and error/desktop. HTTP errors, failed requests, console
  warnings/errors, and overflowing viewports were all zero.
- Exact accounting passed: 69/69 preserved contracts, 34/34 source anchors,
  24/24 blockers, 3/3 runtime unknowns, 4/4 runtime-state handoffs, 3/3
  viewport handoffs, 4/4 state pages, and 4/4 state screenshots.
- Contract-preservation accuracy distribution: sample/min/median/mean/p90/max
  all `1.0`.
- Two uncontended runner invocations were byte-identical:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Reordered state rows failed only with
  `runtime_state_handoffs:reordered`; wrong map hash failed only with
  `runtime:frontend-map-hash`.
- Executable FrontendMap:
  `566e4f6f31e65011f9e40ebb7168c645c38d7567861dab53b3c0180d3c5e3191`.

### Repository and package gates

- 99 focused warning-strict tests; 1,440 full warning-strict tests; pytest
  cache disabled.
- Scoped Ruff and format, full `compileall`, and `git diff --check` passed.
- Wheel/sdist build, fresh wheel install, metadata, 82 module imports, CLI
  version/map/redesign/prototype smokes, checkout/install brief parity, and
  `pip check` passed.
- Wheel:
  `5b5a764f9427916009f75ab6aaed3095f5449be103b19cba628bf12ba00387f9`.
- Sdist:
  `274c039743959ed59eb24cf7c0a286ada28d5f98c9fa3cf9ceec9baf6be62ae1`.
- Installed canonical brief:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Multi-axis correctness/readability/architecture/security/performance review:
  APPROVE after all required findings above were fixed.
- Codebase-memory full refresh: 6,028 nodes and 24,986 edges.

### Scope, artifacts, and next plan

- Production delta: +32 LOC (`prototype.py` +32;
  `runtime_observer.py` ±0). Growth is the canonical capture-ID gate plus the
  exact v1 appendix; no duplicate model/cache/graph/evidence/wrapper or
  dependency was added.
- Benchmark/schema delta: +661 LOC. Tests: +595 LOC. The old ambiguous v1
  command/decision sentence and default state-collision fallback were
  replaced, not retained as alternate paths.
- Exact artifacts:
  `/Users/omar/Documents/Projects/.uidetox-qualification/026-run-1` and
  `/Users/omar/Documents/Projects/.uidetox-qualification/026-recovery-1`.
- Remaining risk: provider token/cache/reasoning telemetry was unavailable;
  exact prompt/brief/output bytes and wall time are retained instead.
- Next Plan 027 should move executable capture-identity validation from the
  prototype boundary into the canonical runtime-record construction path,
  then delete the remaining legacy page-to-capture identity allowance once
  archived artifact impact is measured.

## STOP conditions

Stop without implementation or integration if:

- live state diverges from the measured clean baseline unexpectedly;
- a state can only be proven by inventing evidence absent from the generated
  brief;
- executable qualification would require modifying mapped production source or
  the preserved agent report after agent exit;
- the shared runtime model cannot express the required capture without a new
  parallel evidence type;
- Plan 015/016 stash reconciliation lacks explicit source-level evidence;
- any required gate remains flaky, contested, or unexplained.
