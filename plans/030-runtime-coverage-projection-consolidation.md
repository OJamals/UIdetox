# Plan 030: Runtime coverage projection consolidation

## Status

DONE

## Magic moment

FrontendMap runtime coverage preserves every persisted key and exact value while
counting completed and failed capture statuses in one projection pass. Distinct
coverage totals remain explicit, bounded aggregates instead of gaining a new
helper, model, cache, or reflective abstraction.

## Measured baseline

Live baseline on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `620b1d82f2138c5d9c7e703acaa9e75f6a6c1deb`;
- root is clean; one worktree; local and remote contain only `master`;
- Plan 015/016 archival stashes remain exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload is
  running; observed Node/Playwright work belongs to the separate MASEST
  checkout and is untouched;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,673 edges;
- `map_frontend` has a CRITICAL blast radius with 60 inbound graph edges and
  direct CLI, scan, redesign, workflow, project-map, and test consumers;
- warning-strict focused baseline passes 162 tests with the cache provider
  disabled;
- production contains 40,128 lines, 982 functions, and 132 classes/models;
  tests contain 30,700 lines, 1,626 functions, and 40 classes.

### Projection pass count

`map_frontend.runtime_coverage` currently has eight persisted equations:

- `requested`: one O(1) `len` call and no capture traversal;
- `completed`: one full capture traversal;
- `failed`: one full capture traversal;
- `truncated`: one full capture traversal;
- `total`: one full capture traversal;
- `candidates`: one full capture traversal;
- `eligible`: one full capture traversal;
- `emitted`: one full capture traversal.

The projection therefore performs seven full capture scans, not eight. Runtime
observation plans cap the capture matrix at 256 rows, so the current worst case
is 1,792 aggregate iterations.

### Consumer inventory

- FrontendMap persists the eight-key `runtime_coverage` dictionary as raw
  evidence.
- `retain_runtime_evidence` retains every `runtime_*` field and changes only
  `runtime_status` when source freshness becomes stale.
- redesign copies `runtime_coverage` through a JSON round trip into proposal
  evidence without interpreting any key.
- prototype renders the copied dictionary as bounded JSON without deriving
  status or coverage.
- review and finding verification consume `runtime_capture_matrix`, not
  `runtime_coverage`; their exact completed-capture checks remain intentional.
- workflow and scan consume exact runtime status/freshness, not the summary.
- tests directly assert the `requested` and `completed` values and preserve the
  entire dictionary through FrontendMap, RedesignSet, and prototype boundaries.

### Duplicate classification

- `completed` and `failed` are duplicate status traversals over the same field
  and can share an existing `Counter` projection without changing behavior,
  including behavior for a noncanonical status value.
- `truncated`, `total`, `candidates`, `eligible`, and `emitted` aggregate
  independent fields. Combining them would require a new helper/interface,
  mutable accumulator block, reflection, or per-row temporary allocation.
- `requested` is an O(1) cardinality query and is not a scan.
- capture-matrix iteration in review, findings, diagnostics, and serialization
  has distinct output or validation responsibility and is not duplicate
  coverage ownership.

## Architecture decision

- Use the already-imported `Counter` to count capture statuses once.
- Preserve the named `runtime_coverage` projection and all eight keys in their
  existing order.
- Preserve five explicit coverage-field sums; do not force a generalized
  one-pass abstraction when it would increase code and cognitive load.
- Keep `RuntimeObservation` as intrinsic status authority and FrontendMap as
  persisted projection/freshness owner.
- Keep review and findings on exact capture rows.
- Remove adjacent redundant multiline construction where it makes the
  production delta negative without changing behavior.
- Add no function, type, model, enum, cache, graph, wrapper, compatibility
  fallback, renderer type, serialized field, schema migration, or dependency.
- Treat this as a pure refactor: existing tests are the contract and remain
  unchanged.

## Compatibility boundaries

- RuntimeObservation construction, status strings, and serialization remain
  unchanged.
- RuntimeCaptureRecord remains the canonical capture status validation
  boundary.
- FrontendMap evidence retains the same eight `runtime_coverage` keys, order,
  integer values, and plain-dictionary serialization.
- `stale` remains source/map freshness and is not admitted to intrinsic runtime
  observation state.
- RedesignSet schema 2 and nested runtime handoff evidence remain unchanged.
- Review, finding verification, workflow, and scan retain exact-current and
  exact-capture semantics.
- Prototype output and canonical capture-identity validation remain unchanged.
- Canonical Plan 026-029 artifacts must remain byte-identical; historical
  noncanonical artifacts must retain their intentional canonical failure.

## Tasks

### Task 1: Freeze measured projection ownership

**Acceptance criteria:**

- [x] Live Git/worktree/branch/stash/process/remote/graph state is rebaselined.
- [x] Eight equations are separated into seven traversals plus one O(1) query.
- [x] Capture-matrix bound and worst-case aggregate iterations are recorded.
- [x] Every persisted and exact-current consumer is classified.
- [x] True duplicate status scans are separated from independent aggregates.
- [x] Focused warning-strict baseline passes before production edits.

**Dependencies:** None

### Task 2: Consolidate duplicate status projection

**Acceptance criteria:**

- [x] Completed and failed counts come from one capture-status traversal.
- [x] Five independent coverage sums and requested cardinality stay explicit.
- [x] All eight keys, order, types, and values remain exact.
- [x] Production LOC is negative and function/type/model counts do not grow.
- [x] Tests remain unchanged because behavior remains unchanged.

**Verification:**

- [x] Focused warning-strict tests pass after the refactor.
- [x] Exhaustive canonical and noncanonical status probes match before/after.

**Dependencies:** Task 1

### Task 3: Qualify persistence and historical boundaries

**Acceptance criteria:**

- [x] FrontendMap and RedesignSet JSON round trips remain exact.
- [x] Review, finding verification, workflow, scan, and prototype focused paths
      pass unchanged.
- [x] Canonical prototype and qualification replays retain their hashes.
- [x] Historical Plan 025 artifact still fails with the canonical identity
      error.
- [x] Archived stashes and existing qualification artifacts remain
      hash-identical.

**Dependencies:** Task 2

### Task 4: Run repository, package, invariant, and review gates

**Acceptance criteria:**

- [x] Focused and full warning-strict pytest pass with cache disabled.
- [x] Scoped Ruff `E4/E7/E9/F/I`, Ruff format, unused-symbol checks,
      `compileall`, wheel/sdist build, metadata, fresh install, 82 imports, CLI
      smokes, `pip check`, and `git diff --check` pass.
- [x] Multi-axis correctness/readability/architecture/security/performance
      review approves exact scope.
- [x] Production/test/docs/total LOC, function/type/model delta, removed code,
      distributions, compatibility boundaries, and remaining risks are
      recorded.

**Dependencies:** Task 3

### Task 5: Integrate and prove parity

**Acceptance criteria:**

- [x] Commit and push only after every required gate passes.
- [x] Refresh graph after the source commit.
- [x] Prove `HEAD == master == origin/master == remote refs/heads/master`.
- [x] Root is clean; one worktree; only `master`; archival stashes exact; no
      UIdetox test, qualification, Playwright, or Chromium workload remains.
- [x] No release, tag, or PyPI action occurs.

**Dependencies:** Task 4

## Done criteria

- [x] Capture-status projection uses one traversal.
- [x] Independent coverage aggregates stay explicit and local.
- [x] All serialized fields, schemas, exact strings, and consumers remain
      compatible.
- [x] Canonical artifacts replay and historical failures remain intentional.
- [x] Full repository/package/invariant/review gates pass.
- [x] Local/origin/server SHA parity is proven after graph refresh.

## Execution results

- Runtime coverage retains eight equations. Full capture scans fell from seven
  to six: status scans `2 -> 1`, independent coverage scans `5 -> 5`, and
  requested cardinality remains one O(1) `len`. At the 256-row matrix bound,
  aggregate iterations fall from 1,792 to 1,536.
- Five empty/canonical/noncanonical status probes retained exact projected
  values. Before/after payload SHA-256 is
  `978084944d21541d3b062f2ee804c0ecae705689357173cf307b89bd74277a25`.
- Focused warning-strict pytest passed 162 tests before and after the refactor.
  Full warning-strict pytest passed 1,451 tests with the cache provider
  disabled.
- Scoped Ruff `E4/E7/E9/F/I`, Ruff format, repository-wide Ruff `F`
  unused-symbol coverage, full `compileall`, and `git diff --check` passed.
  A deliberately broad format/import sweep found 21 pre-existing untouched
  files and was not applied outside scope.
- Production delta is `+4/-6`, net `-2` LOC. Tests are unchanged. Production
  remains 982 functions and 132 classes/models; tests remain 1,626 functions
  and 40 classes. No symbol was added or removed.
- Removed code: two independent capture-status generator scans and redundant
  multiline assembly of the adjacent runtime-finding list. Added functions,
  types, models, enums, caches, graphs, wrappers, fallbacks, serialized fields,
  schema migrations, and dependencies: none.
- FrontendMap, RedesignSet, review, finding verification, workflow, scan, and
  prototype compatibility paths passed unchanged. The plain eight-key
  `runtime_coverage` dictionary and capture-matrix authority remain exact.
- Checkout and fresh-installed canonical prototype SHA-256 remain
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two uncontended qualification replays remain byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
  Plan 025 still fails exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Fresh build/install gates passed: metadata reports `uidetox 1.9.0`, Python
  `>=3.11`, 14 dependency records; 82 package modules import; version/map/
  redesign/prototype CLI smokes and `pip check` pass.
- Wheel SHA-256:
  `6e09d7ae6806a6cc5f22a323a56eaf87e3b67e7ebdf5d6f8d55ca04cc76d23fb`.
- Sdist SHA-256:
  `abfc1ef3f823dda2259821fcbecd5191d01a4e365b6ef48b1db841b89528c80c`.
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/030.Z7DTIf`.
- Source commit:
  `1097f6c` (`refactor: consolidate runtime coverage status projection`).
- Graph refresh commit:
  `0e2f2c7`; refreshed graph contains 6,027 nodes and 25,725 edges.
- Multi-axis review verdict: **APPROVE**. Correctness and noncanonical behavior
  are identical; the named projection is smaller; no security boundary moves;
  status traversal work decreases without generalizing independent fields.
- Remaining risk: `map_frontend` remains a CRITICAL, 60-caller function. Its
  five independent coverage sums are intentionally explicit; forcing them into
  one accumulator would add code and abstraction for at most 256 rows.
- Plan 031 recommendation: measure the three graph-reported
  `map_frontend` linear scans inside source-fact loops, especially action
  first-line lookup and per-network-call state/action ownership scans. Replace
  only proven repeated traversals with existing owner indexes when production
  LOC and cognitive complexity both fall; do not split `map_frontend` merely
  to redistribute lines.

## STOP conditions

Stop without integration if:

- consolidation requires a schema change, compatibility layer, new authority,
  reflective abstraction, or semantic guess;
- a one-pass all-field accumulator increases production LOC or cognitive load;
- review or finding verification proves to consume aggregate coverage instead
  of exact capture rows;
- intrinsic runtime status and map freshness would need merging;
- canonical Plan 026-029 artifacts change for any reason;
- a historical noncanonical artifact stops failing at the canonical boundary;
- archived evidence or Plan 015/016 stashes would need mutation;
- any required gate remains flaky, contested, or unexplained.
