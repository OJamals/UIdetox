# Plan 029: Runtime observation completeness and status derivation

## Status

IN PROGRESS

## Magic moment

Every runtime observation validates capture identity and derives intrinsic
completeness in one capture pass. Persisted maps still distinguish intrinsic
observation state from source-freshness state, and all review, verification,
workflow, redesign, and prototype consumers retain their existing schemas and
exact status strings.

## Measured baseline

Live baseline on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `6ad1af7a3860d4800be02b838d337a61c8a517bc`;
- root is clean; one worktree; local and remote contain only `master`;
- Plan 015/016 archival stashes remain exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload is
  running;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,650 edges;
- `RuntimeObservation` has a CRITICAL class blast radius with 51 inbound graph
  edges across observer, map, capture, redesign, prototype, finding, benchmark,
  and test paths;
- warning-strict focused baseline passes 188 tests with the cache provider
  disabled;
- canonical review-cleanup artifacts remain exact:
  prototype
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`,
  qualification
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`,
  wheel
  `ab2c91dbf587f96d04bf91d0123fe31924df295312323679dba11f6b1cec9de6`,
  and sdist
  `f9f8fefc6a764d2e7b781d5446eb78a710231a3521a1581175f115226d0658a5`.

### Constructor pass count

`RuntimeObservation.__post_init__` currently performs:

- four capture passes:
  one identity/index validation loop plus separate `completed`, `failed`, and
  `degraded` aggregate scans;
- three page passes:
  capture-ID normalization, conditional page-only legacy capture construction,
  and page-to-capture validation;
- three independent capture-status equations followed by one five-branch
  status decision;
- five intrinsic observation outputs:
  `absent`, `current`, `partial`, `degraded`, and `failed`.

The page passes have distinct normalization, legacy-compatibility, and
validation responsibilities. The three aggregate capture scans duplicate the
already-required canonical capture traversal.

### Derivation inventory

- `RuntimeObservation.__post_init__` is the sole intrinsic observation-status
  authority. `RuntimeObservation.from_dict` deliberately ignores persisted
  `status` and recomputes it through construction.
- `map_frontend` copies `runtime.status` into raw FrontendMap evidence and
  persists a separate `runtime_coverage` summary. Its completed/failed and
  coverage totals are compatibility output, not a second status equation.
- `retain_runtime_evidence` owns source-freshness transition to `stale`.
- redesign freshness projects existing intrinsic status, promotes only
  `current` evidence to `stale` when mapped source is stale, and retains the
  existing legacy `runtime_observed` fallback.
- review requires exact-current map evidence, then independently enumerates
  completed capture tuples as review-scope coverage.
- finding hashing consumes persisted runtime status. Runtime finding
  verification requires exact-current map evidence and an exact completed
  capture row before evaluating a detector.
- workflow and scan paths use exact-current checks as eligibility gates.
- prototype validation reconstructs the existing capture matrix through
  `RuntimeObservation.from_dict`; it does not own another status equation.

### State boundary

- Intrinsic observation state:
  `absent`, `current`, `partial`, `degraded`, `failed`.
- Map freshness state:
  `stale`.
- Exact-current checks in review, findings, workflow, scan, redesign
  acceptance, and prototype handoff are intentional consumers.
- Capture-level `completed`/`failed` checks in FrontendMap coverage, review
  scope, and finding verification are intentional persisted-matrix consumers.

## Architecture decision

- Keep `RuntimeObservation` as the only intrinsic runtime authority.
- Fold the three intrinsic status aggregates into its existing
  capture-identity/index loop.
- Preserve the existing five-branch precedence and every exact output string.
- Do not merge `stale` into intrinsic observation status.
- Do not alter page normalization, legacy page-only construction, or
  page-to-record validation.
- Keep FrontendMap coverage projection, redesign freshness, exact-current
  consumers, and prototype reconstruction unchanged.
- Add no model, enum, cache, graph, wrapper, compatibility fallback, renderer
  type, serialized field, schema migration, or helper function.
- Treat this as a pure refactor: existing tests are the contract and remain
  unchanged. A new red test would assert implementation shape rather than
  behavior.

## Compatibility boundaries

- `RuntimeObservation.to_dict` remains `asdict(self)` with the same fields.
- `RuntimeObservation.from_dict` retains current malformed-row validation,
  legacy defaults, and constructor recomputation.
- FrontendMap schema and raw `evidence` dictionary remain unchanged.
- RedesignSet schema 2 and nested proposal evidence remain unchanged.
- Finding verification retains exact runtime anchor, capture row, completion,
  and current-map requirements.
- Review retains exact route/state/viewport completed-matrix validation.
- Workflow and scan retain exact-current eligibility semantics.
- Prototype retains `RuntimeObservation.from_dict` as its executable boundary.
- Canonical Plan 026-028 artifacts must remain byte-identical; historical
  noncanonical artifacts must retain their intentional canonical failure.

## Tasks

### Task 1: Freeze measured ownership and compatibility

**Acceptance criteria:**

- [x] Live Git/worktree/branch/stash/process/remote/graph state is rebaselined.
- [x] Capture and page passes plus status equations are counted.
- [x] Intrinsic statuses are separated from `stale` freshness.
- [x] Every requested consumer path is classified as authority, projection,
      freshness owner, exact-current consumer, or capture-matrix consumer.
- [x] Persisted FrontendMap, RedesignSet, finding, review, workflow, and
      prototype boundaries are recorded.
- [x] Focused warning-strict baseline passes before production edits.

**Dependencies:** None

### Task 2: Collapse duplicate intrinsic capture scans

**Acceptance criteria:**

- [x] Completed, failed, and degraded aggregates are computed during the
      existing canonical capture loop.
- [x] Capture traversals fall from four to one.
- [x] Page traversals remain three because their responsibilities are distinct.
- [x] Five intrinsic status strings and precedence remain exact.
- [x] No consumer or persistence path changes.
- [x] Production LOC is negative and function/type/model counts do not grow.
- [x] Tests remain unchanged because behavior remains unchanged.

**Verification:**

- [x] Focused warning-strict tests pass after the refactor.
- [x] Exhaustive constructor-state probes match the pre-change distribution.

**Dependencies:** Task 1

### Task 3: Qualify persistence and historical boundaries

**Acceptance criteria:**

- [x] RuntimeObservation and FrontendMap round trips remain exact.
- [x] RedesignSet, review, finding verification, workflow, scan, and prototype
      focused paths pass unchanged.
- [x] Canonical prototype and qualification replays match the Plan 028 hashes.
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
- [x] Production/test/docs/total LOC, function/type/model delta, deleted code,
      distributions, compatibility boundaries, and remaining risks are
      recorded.

**Dependencies:** Task 3

### Task 5: Integrate and prove parity

**Acceptance criteria:**

- [ ] Commit and push only after every required gate passes.
- [ ] Refresh graph after the source commit.
- [ ] Prove `HEAD == master == origin/master == remote refs/heads/master`.
- [ ] Root is clean; one worktree; only `master`; archival stashes exact; no
      test, qualification, Playwright, or Chromium workload remains.
- [ ] No release, tag, or PyPI action occurs.

**Dependencies:** Task 4

## Done criteria

- [x] One canonical capture pass validates identity and derives intrinsic
      completeness.
- [x] Intrinsic status and `stale` map freshness remain separate.
- [x] All serialized fields, schemas, exact status strings, and persisted
      consumer boundaries remain compatible.
- [x] Canonical artifacts replay and historical failures remain intentional.
- [x] Full repository/package/invariant/review gates pass.
- [ ] Local/origin/server SHA parity is proven after graph refresh.

## Pre-integration execution results

- Capture passes fell from four to one. Page passes remained three.
- Constructor-state distribution stayed exact:
  `absent=1`, `current=1`, `partial=3`, `degraded=2`, `failed=2` across the
  nine-case boundary probe; before/after payload SHA-256 is
  `c09bdd9171868db8d6431e8bde8dd3234d5046bba89b3e04315d422d096d7e9e`.
- Focused warning-strict pytest passed 188 tests. Additional review/findings/
  workflow coverage passed 50 tests. Full warning-strict pytest passed 1,451
  tests with the cache provider disabled.
- Scoped Ruff `E4/E7/E9/F/I`, Ruff format, unused-symbol coverage through Ruff
  `F`, full `compileall`, and `git diff --check` passed.
- Production delta is `+16/-17`, net `-1` LOC. Tests are unchanged. Plan/docs
  add 231 lines before final result updates. Production function count remains
  982 and class/model count remains 132; no symbol was added or removed.
- Removed code: three post-validation capture scans and the redundant
  integer-count form of the five-way status decision. Added functions, types,
  models, enums, caches, graphs, wrappers, fallbacks, serialized fields, and
  dependencies: none.
- FrontendMap and RedesignSet JSON round trips remained exact. Canonical
  RuntimeObservation reconstruction remained `current` with four captures.
- Checkout and fresh-installed canonical prototype SHA-256 remained
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two uncontended qualification replays remained byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
  Plan 025 still failed exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Fresh build/install gates passed: metadata reports `uidetox 1.9.0`, Python
  `>=3.11`, 14 dependency records; 82 package modules import; version/map/
  redesign/prototype CLI smokes and `pip check` pass.
- New wheel SHA-256:
  `28d568566429d03c275484fa580a2fa4ec9455760e121e3db008d68bbc6da483`.
- New sdist SHA-256:
  `141da884d26cac1bced1fe074680e4d8ec55fd027bec0acad33a4b55f1c5411f`.
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/029.CGurhh`.
- Multi-axis review verdict: **APPROVE**. Correctness truth table is identical;
  control flow is smaller; authority stays in `RuntimeObservation`; no
  security boundary changes; capture aggregation drops from four linear passes
  to one.
- Remaining risk: intrinsic states remain exact strings by compatibility
  contract, so any future capture status must update this canonical loop and
  its exhaustive boundary probe. `RuntimeObservation` remains a CRITICAL
  high-fan-in class.
- Plan 030 recommendation: measure the eight persisted
  `map_frontend.runtime_coverage` aggregate scans and their consumers, then
  consolidate only the projection loop if exact serialized fields and
  capture-level review/finding semantics can remain unchanged. Do not revisit
  intrinsic/current/stale ownership without new evidence.

## STOP conditions

Stop without integration if:

- consolidation requires a schema change, compatibility layer, new authority,
  or semantic guess;
- any exact-current consumer proves to own intrinsic status derivation;
- `stale` must be admitted to `RuntimeObservation` to make a gate pass;
- canonical Plan 026-028 artifacts change for any reason;
- a historical noncanonical artifact stops failing at the canonical boundary;
- archived evidence or Plan 015/016 stashes would need mutation;
- any required gate remains flaky, contested, or unexplained.
