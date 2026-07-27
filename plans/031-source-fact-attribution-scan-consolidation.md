# Plan 031: Source-fact attribution scan consolidation

## Status

DONE

## Magic moment

FrontendMap preserves exact action lines and per-call lifecycle/action attribution
while each module's action and state facts are traversed once. Existing
map-local grouping and ownership indexes become deep enough to answer later
lookups without adding a helper, model, cache, graph, wrapper, or compatibility
path.

## Measured baseline

Live baseline on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `29497791c6f4924e01b7442aa54a647e21e61af5`;
- root is clean; one worktree; local and remote contain only `master`;
- Plan 015/016 archival stashes remain exactly
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload is
  running; the observed pytest process belongs to
  `/Users/omar/Documents/Projects/oracle` and is untouched;
- this checkout has no `.beads` directory, so there is no repository Beads
  state to claim or mutate;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,725 edges;
- `map_frontend` has a CRITICAL blast radius, 60 direct inbound call edges,
  75 inbound structural edges, complexity 31, cognitive complexity 75,
  14 loops, and three graph-reported linear scans inside loops;
- warning-strict focused baseline passes 190 tests with the cache provider
  disabled;
- production contains 40,126 lines, 982 functions, and 132 classes/models;
  tests contain 30,700 lines, 1,626 functions, and 40 classes.

### Exact repeated traversals

For one module with `A` action facts, `G` unique
`(owner, name, target)` action groups, `S` state facts, and `N` network calls:

1. Action grouping traverses `facts.actions` once, then each action group's
   `first_line` lookup rescans from the beginning until the first exact group
   occurrence. Exact lookup work is the sum of the one-based first-occurrence
   positions for all `G` groups.
2. Every network call traverses all `S` state facts to select states owned by
   `call_ui_owner`, producing `S * N` ownership inspections.
3. Every network call traverses all `A` action facts to select actions with the
   exact UI owner and either direct-owner or target-owner relationship,
   producing `A * N` attribution inspections.

The second and third filters are intentional per-call attribution semantics.
Their repeated full traversal is not intentional: both answers can be supplied
by the map-local owner indexes built from the same immutable source facts.

### Full-stack fixture distribution

Measured against `examples/fullstack-slop-lab/frontend/src` using the production
`ProjectFileSet`, semantic adapter registry, and application-resolution path:

- 36 semantic modules; 21 contain actions, states, or network calls;
- 42 action groups from 61 action occurrences;
- 66 states and 57 network calls;
- 31 declared UI owners across all modules; the 21 work-bearing modules contain
  20 UI owners, 19 action owners, 16 state owners, and 55 call owners;
- 14 call UI owners resolve, but only 10 calls are uniquely attributable after
  the existing per-owner call-count rule;
- median work-bearing module: 2 action groups, 2 actions, 3 states, 2 calls,
  and 9 target-loop inspections;
- p95 work-bearing module: 3 groups, 6 actions, 6 states, 3 calls, and
  39 target-loop inspections;
- maximum is `ProjectsPage.tsx`: 6 groups, 11 actions, 9 states, 3 calls,
  and 90 target-loop inspections.

Exact fixture target-loop work:

- first-action-line lookups: 97 inspections;
- state-owner filtering: 136 inspections;
- action owner/target attribution: 108 inspections;
- graph-reported repeated scan work: 341 inspections.

Including the primary action grouping, action-owner indexing, and state-node
passes, relevant source-fact traversal work is 529 inspections. Reusing those
primary passes projects this to 127 inspections: one pass over 61 actions and
one pass over 66 states. The three nested scans project from 341 to zero.

### Representative causal variants

| Variant | Groups | Actions | States | Calls | UI owners | Attributable calls | First-line | State scan | Action scan | Total |
|---------|-------:|--------:|-------:|------:|----------:|-------------------:|-----------:|-----------:|------------:|------:|
| Direct single call with four lifecycle states | 1 | 1 | 4 | 1 | 1 | 1 | 1 | 4 | 1 | 6 |
| Handler target with duplicate action occurrences | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 4 |
| Two calls owned by one UI module | 1 | 1 | 1 | 2 | 1 | 0 | 1 | 2 | 2 | 5 |
| Two independent UI owners | 2 | 2 | 2 | 2 | 2 | 2 | 3 | 4 | 4 | 11 |
| Two distinct handler targets | 2 | 2 | 0 | 2 | 1 | 0 | 3 | 0 | 4 | 7 |

These variants cover direct ownership, target ownership, duplicate groups,
multi-call ambiguity, and owner isolation. They demonstrate that scan removal
must not collapse owner or target dimensions.

### History and semantic intent

- `83eaab90` established first-occurrence action-line behavior. Later source-fact
  migrations retained `next(...)` specifically to preserve the first source
  occurrence rather than the final line or a sorted minimum.
- `d2aaaf52` introduced lifecycle/action evidence on each network operation.
- `32addbab` made multi-call attribution conservative so ambiguous actions and
  states stay empty/unknown.
- `d0ec3b0f` added exact action `(owner, name, target)` identity, direct versus
  target call ownership, unique UI-owner resolution, owner-scoped lifecycle
  evidence, and causal action attribution.
- Existing contract tests require independent UI owners to retain their own
  lifecycle states, handler targets to link only their own actions, and
  ambiguous multi-call modules to emit no cross-linked evidence.

### Existing indexes and ownership

- `SourceFacts.actions`, `.states`, and `.network_calls` remain immutable tuple
  authority.
- `_ApplicationIndex` owns application-wide module, selector, route, and
  network-symbol indexes. It deliberately has no FrontendMap presentation or
  per-call attribution responsibility.
- `record.component_ids` and `ui_owners` own map-local UI source identity.
- the current `actions` grouping owns action deduplication/counting;
  `action_ui_owners` owns target-to-UI-owner resolution;
  `call_ui_owners` and `call_counts_by_ui_owner` own conservative call
  attribution.
- FrontendMap owns action/state/data node ordering and serialized metadata.
  ProjectMap consumes only the resulting data-node `ui_actions`, `ui_states`,
  `ui_lifecycle_evidence`, source anchors, and contract fields.

## Architecture decision

- Replace the `Counter` plus per-group `next(...)` lookup with one insertion-
  ordered dictionary mapping each exact action group to its first line and
  occurrence count. Never overwrite the first stored line.
- Deepen the existing action-owner index, in the same action traversal, so a
  call owner resolves to exact UI-owner action names. Preserve the direct-owner
  fast path and unique-owner ambiguity rule.
- Populate lifecycle state names by owner during the existing state-node pass.
  Use the owner lookup during network-call projection.
- Keep all structures local to `map_frontend`; they are implementation details,
  not a new interface or seam.
- Keep `ApplicationSemantics`, `SourceFacts`, `FrontendMap`, and `ProjectMap`
  authority unchanged.
- Add no function, type, model, enum, cache, graph, wrapper, compatibility
  fallback, serialized field, schema migration, dependency, or test-only
  production hook.
- Do not split `map_frontend`; the deletion must make the existing local
  implementation smaller and easier to follow.
- Treat this as a pure refactor. Existing tests are the contract and remain
  unchanged. If any output behavior must change, stop and write a failing
  behavior test before continuing.

## Compatibility boundaries

- Action grouping remains exact on `(owner, name, target)`.
- Action occurrence count and first source line remain exact, including
  interleaved duplicate groups.
- Action node IDs, names, owners, targets, edges, source lines, extractor,
  confidence, sorting, and fingerprint inputs remain unchanged.
- State node IDs, source lines, owners, edges, extractor, confidence, and
  ordering remain unchanged.
- Direct call ownership, target-derived ownership, unique-owner resolution,
  multi-call ambiguity, and unattributable low-level clients remain unchanged.
- `attributable_ui`, `ui_actions`, `ui_states`, `ui_lifecycle_evidence`,
  `ui_required`, mutation/cache/auth evidence, request/response contracts, and
  every data-node field remain exact.
- FrontendMap schema 1 and raw `asdict` serialization remain exact.
- ProjectMap consumes identical frontend observations and therefore preserves
  nodes, edges, findings, source anchors, IDs, and serialized fields.
- RedesignSet schema 2, prototype handoff evidence, review/finding verification,
  workflow, scan, map freshness, and runtime evidence paths remain unchanged.
- Canonical Plan 026-030 artifacts must remain byte-identical; historical
  noncanonical artifacts must retain their intentional canonical failure.

## Tasks

### Task 1: Freeze traversal and ownership semantics

**Acceptance criteria:**

- [x] Live Git/worktree/branch/stash/process/remote/graph state is rebaselined.
- [x] All three graph-reported scans have exact work equations.
- [x] Real fixture and representative causal distributions are recorded.
- [x] Git history/blame identifies first-occurrence, owner, target, and
      ambiguity intent.
- [x] Existing application-wide and map-local indexes are classified.
- [x] FrontendMap, ProjectMap, RedesignSet, finding, review, workflow, scan,
      and prototype boundaries are inventoried.
- [x] Warning-strict focused baseline passes before production edits.

**Dependencies:** Plan 030

### Task 2: Consolidate source-fact traversal

**Acceptance criteria:**

- [x] Action counts and first lines come from one exact ordered grouping pass.
- [x] Action call-owner/name attribution reuses that same action pass.
- [x] Lifecycle state ownership reuses the existing state-node pass.
- [x] No network-call iteration scans `facts.actions` or `facts.states`.
- [x] Direct, target, ambiguous, duplicate, and owner-isolated behavior remains
      exact.
- [x] Production LOC is negative; function/type/model counts do not grow.
- [x] The three measured source-fact nested scans fall from three to zero.
      The coarse function-level graph signal remains three and is recorded
      separately because it does not expose source locations.
- [x] Tests remain unchanged because behavior remains unchanged.

**Verification:**

- [x] Focused warning-strict tests pass after the refactor.
- [x] Before/after FrontendMap and ProjectMap payload probes are byte-identical.
- [x] Exhaustive action ordering/duplicate/owner/target probes match.

**Dependencies:** Task 1

### Task 3: Qualify consumer and historical boundaries

**Acceptance criteria:**

- [x] FrontendMap and ProjectMap JSON round trips remain exact.
- [x] RedesignSet, review, finding verification, workflow, scan, and prototype
      focused paths pass unchanged.
- [x] Canonical prototype and qualification replays retain their hashes.
- [x] Plan 030 projection probe and Plan 026-030 artifacts remain exact.
- [x] Historical Plan 025 artifact still fails with the canonical identity
      error.
- [x] Archived stashes and existing qualification artifacts remain
      hash-identical.

**Dependencies:** Task 2

### Task 4: Run repository, package, invariant, and review gates

**Acceptance criteria:**

- [x] Focused and full warning-strict pytest pass with cache disabled.
- [x] Scoped Ruff `E4/E7/E9/F/I`, Ruff format, repository-wide unused-symbol
      checks, `compileall`, wheel/sdist build, metadata, fresh install,
      82 imports, CLI smokes, `pip check`, and `git diff --check` pass.
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

- [x] Each module's actions and states are traversed once for map projection.
- [x] Exact first occurrence, ownership, target, and ambiguity semantics remain.
- [x] All serialized fields, schemas, node/edge order, IDs, fingerprints, and
      consumers remain compatible.
- [x] Production code and cognitive/scan complexity both decrease.
- [x] Canonical artifacts replay and historical failures remain intentional.
- [x] Full repository/package/invariant/review gates pass.
- [x] Local/origin/server SHA parity is proven after graph refresh.

## Execution results

- Source commit: `ebc0fdbaf4bfb917351d61aadfc5747cbaa2a886`.
- Graph refresh commit: `7bc7b31`.
- Production delta: 27 insertions, 30 deletions, net `-3` lines;
  40,126 to 40,123 lines. Functions remain 982; classes/models remain 132.
  Tests remain unchanged at 30,700 lines, 1,626 functions, and 40 classes.
- Documentation grows from 24,774 to 25,128 lines (`+354`), entirely the
  Plan 031 record and its one-line plan-index entry.
- `map_frontend` graph metrics: complexity 31 to 30, cognitive complexity
  75 to 72, lines 649 to 646; 14 loops and loop depth 2 remain unchanged.
- The graph's coarse `linear_scan_in_loop` property remains three. Exact
  source-level review proves the three Plan 031 sites are gone: no
  per-action-group `facts.actions` first-line scan and no per-network-call
  `facts.states` or `facts.actions` scan remain.
- Full-stack fixture work: 42 action groups / 61 actions / 66 states /
  57 network calls. Target nested-scan inspections fall 341 to zero;
  relevant source-fact traversal falls 529 to 127 (`-76.0%`).
- The before/after normalized full-stack FrontendMap plus ProjectMap payload is
  byte-identical at SHA-256
  `a52678994d6d612910fa8e1777825d01c93e1c8b512e2c60e8ecc39b93721672`.
- Exhaustive equivalence passed 19,608 action sequences,
  5,078,472 call projections, 19,608 state sequences, and 117,648 state-owner
  projections. The probe caught and then preserved the intentional empty-target
  suppression boundary.
- Warning-strict focused pytest: 190 passed before and after. Warning-strict
  full pytest: 1,451 passed. Review-target pytest: 3 passed.
- Scoped Ruff, repository-wide unused-symbol checks, Ruff format,
  `compileall`, `git diff --check`, build, fresh install, all 82 package
  submodule imports, CLI smokes, and `pip check` passed.
- Canonical prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Plan 030 projection probe SHA-256 remains
  `978084944d21541d3b062f2ee804c0ecae705689357173cf307b89bd74277a25`.
- Final wheel SHA-256:
  `50ee2ac9cdfececb72f09064fdff87657e3589d56d10ca4580b8341955a98ec0`.
- Final sdist SHA-256:
  `7c1c9bde13e0474ab323410cccc5f5262b226c60ede9c29ea8877e6a6faca4f8`.
- Historical Plan 025 still fails exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/031.uonBRY`.
- Multi-axis review verdict: no findings; APPROVE. No schema, serialized field,
  function, type, model, enum, cache, graph, wrapper, facade, compatibility
  fallback, dependency, test, release, tag, or PyPI change occurred.
- Remaining risk: action/state attribution remains a CRITICAL `map_frontend`
  boundary. The coarse graph scan counter cannot distinguish dictionary
  membership from source-fact traversal, so future work must repeat exact
  source-level equations and output probes rather than optimize that counter.
- Plan 032 recommendation: measure `_read_pyproject_dependency_names` before
  changes. It is the next production cognitive hotspot (complexity 28,
  cognitive 91, 63 lines) with CRITICAL inbound detection paths. Consolidate
  only proven repeated PEP 621, dependency-group, and Poetry table traversal;
  preserve malformed-file fail-closed behavior and normalized dependency
  semantics without helper proliferation.

## STOP conditions

Stop without integration if:

- consolidation requires a schema change, compatibility layer, new public
  authority, helper facade, parallel index model, cache, or semantic guess;
- exact first occurrence cannot be preserved for interleaved duplicate groups;
- direct, target, ambiguous, or owner-isolated attribution changes;
- production LOC or cognitive complexity grows;
- `map_frontend` must be split merely to move lines;
- FrontendMap, ProjectMap, RedesignSet, finding, review, workflow, scan, or
  prototype output changes;
- canonical Plan 026-030 artifacts change for any reason;
- a historical noncanonical artifact stops failing at the canonical boundary;
- archived evidence or Plan 015/016 stashes would need mutation;
- any required gate remains flaky, contested, or unexplained.
