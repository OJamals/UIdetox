# Plan 035: Watch snapshot-delta consolidation

## Status

DONE

## Magic moment

`uidetox watch` preserves exact startup, polling, changed/new/deleted
attribution, sorted output, and interruption behavior while each current
snapshot path needs one previous-snapshot lookup instead of two.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `109159ca6aabb290c93c1c6c873a23e2828ac951`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 034 is DONE; Plan 035 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,769 edges and is bound to Plan 034 source commit
  `3d8d26b842eb04fcf5f480403ba6521691be848f`;
- `uidetox.commands.watch.run` is dynamically dispatched by argparse and has
  filesystem discovery, repeated analysis, terminal clearing/output, sleep,
  and process-exit side effects. Treat blast radius as CRITICAL even though
  static inbound tracing cannot see the dispatch;
- graph metrics are 79 lines, complexity 15, cognitive complexity 32, 6 loops,
  loop depth 2, zero loop-local linear scans, and one loop allocation;
- production contains 40,092 lines, 981 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict baseline passes all 6 watch/fileset tests with cache
  disabled;
- Plan 034's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

The repository's canonical `ProjectFileSet` produces 238 watched paths:

- 166 Markdown;
- 37 TSX;
- 18 TypeScript;
- 5 CSS;
- 3 JavaScript;
- 3 Svelte;
- 3 Vue;
- 2 Astro;
- 1 HTML.

Nine snapshot samples take a median 68.625 ms with a 67.748–71.941 ms range.
The initial analyzer pass over all 238 paths takes 2,888.538 ms and finds 12
issues across 9 files: 6 files have one issue and 3 files have two.

Each unchanged poll currently performs:

- one canonical `_snapshot` discovery;
- one current-snapshot traversal for changed/new detection;
- one previous-snapshot traversal for deletion detection;
- one membership probe plus one subscript probe for each existing current
  path;
- one current-snapshot membership probe for each previous path;
- no analysis, clear, timestamp, rendering, or snapshot-state mutation.

At 238 stable paths this is 476 path visits and 714 dictionary probes.
Replacing the membership/subscript pair with the typed snapshot's single
`dict.get` keeps 476 path visits but reduces dictionary probes to 476
(`-33.3%`). With one new, one modified, and one deleted path, probes fall
from 713 to 476.

Nine alternating isolated delta-detection samples show:

- unchanged 238 paths: 286.999 -> 252.481 ms for 20,000 runs (`0.880x`);
- mixed 238 paths: 286.413 -> 256.231 ms (`0.895x`);
- unchanged 10,000 paths: 353.850 -> 315.743 ms for 500 runs (`0.892x`);
- mixed 10,000 paths: 356.552 -> 322.258 ms (`0.904x`).

All candidate ranges beat their corresponding baseline ranges except minor
mixed-case tail overlap; medians improve 9.6–12.0%. Snapshot discovery
dominates whole-poll latency, so report the isolated saving honestly rather
than claiming a material full-poll improvement.

A deterministic matrix first validated 6,118 ordered snapshot pairs through
lengths 0–6; final verification expands this to all 59,049 pairs over five
keys with absent, `0.0`, and `1.0` states. A seven-scenario behavioral probe
freezes invalid-root, empty/default,
initial-issue, unchanged, mixed changed/new/deleted, two-poll state transition,
clear, output, call, and exit behavior at:

`49806c971e97713e0b1d1d96fd2f6d7bc95d3df8d3075f6b0858f9ca733d6bd0`.

## Frozen behavior and side-effect contract

Preserve exactly:

- `path` precedence and project-root resolution for `None`, empty, and `.`;
- interval/clear defaults and invalid-directory stderr/exit-one behavior;
- startup output, blank lines, ANSI sequences, and output ordering;
- initial `_snapshot` before initial analysis;
- initial analysis once per discovered path in snapshot insertion order;
- storage/rendering of issue-bearing initial paths only;
- initial total/file counts and no-issues output;
- initial clear after analysis and before the persistent header;
- one sleep and one fresh `_snapshot` per polling attempt;
- current snapshot insertion order during changed/new derivation;
- new paths as changed even when absent from the previous snapshot;
- changed paths when and only when their float mtime differs;
- deletion attribution from previous keys absent from current keys;
- separate changed and deleted categories;
- no clear, timestamp, analysis, output, or `prev` mutation for unchanged
  polls;
- clear, fixed changed-before-deleted category ordering, and lexicographic
  order within each category for event polls;
- changed/new analysis only; deleted paths are never analyzed;
- `_print_issues` output and malformed tier resilience;
- `prev = curr` only after all event output succeeds;
- `KeyboardInterrupt` handling only around the polling loop and exact stop
  output;
- propagation of non-`KeyboardInterrupt` discovery, analysis, rendering, and
  terminal failures;
- per-poll `load_config`, `find_project_root`, and `ProjectFileSet`
  reconstruction in `_snapshot`, including live exclude/zone changes;
- `_snapshot`'s optional existing `ProjectFileSet` seam and OSError filtering;
- every public/private signature and CLI argument.

## History and architecture

- `36c6eee` introduced watch plus changed/new/deleted polling and hardened
  malformed tier handling.
- `e582819` made default watch scope resolve from the canonical project root.
- `54dc45c` replaced a private extension/os.walk registry with
  `ProjectFileSet`, live config exclusions, zone overrides, and scoped
  discovery.
- `1571409` reformatted the module without semantic change.
- `ProjectFileSet` and `_snapshot` remain the canonical discovery authorities.
- `_parse_tier`, `_print_issues`, `_colour_tier`, and `_snapshot` all have live
  callers; no stale or orphaned watch symbol was found.
- The deletion traversal is intentional attribution over previous ownership,
  not duplicate current-snapshot work.
- Reconstructing `ProjectFileSet` each poll preserves live config semantics.
  Caching it would change behavior and add a second lifecycle authority.
- Sorting at render time is intentional. It removes discovery-order
  variability while retaining changed-before-deleted grouping.

## Architecture decision

- Replace only the explicit changed/new accumulation loop.
- Use `prev.get(fpath) != mtime` because `_snapshot`'s contract is
  `dict[str, float]`; `None` is not a valid mtime.
- Preserve list-comprehension insertion order and downstream sorting.
- Keep deletion detection as its separate previous-snapshot traversal.
- Keep `ProjectFileSet`/config reconstruction, initial aggregation, analysis,
  rendering, state mutation, and interruption boundaries unchanged.
- Add no helper, function, type, model, enum, cache, index, watcher backend,
  graph, wrapper, facade, adapter, fallback, schema, field, dependency, or
  public interface.
- Keep tests unchanged because this is a pure refactor; use external
  differential evidence for the uncovered polling projection.
- Keep only if production LOC, cyclomatic complexity, cognitive complexity,
  dictionary-probe work, and isolated timing all improve.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the dynamic CRITICAL CLI and inspect exact source.
- [x] Inspect fileset/analysis/output helpers, tests, Git history, and blame.
- [x] Measure repository distributions, poll work, source metrics, isolated
      timing, and exact behavioral projection.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate snapshot delta detection

- [x] Replace repeated membership/subscript lookup with one typed lookup.
- [x] Preserve changed/new insertion order and deletion traversal exactly.
- [x] Reduce production LOC and graph complexity without a new symbol or pass.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
- [x] Re-run controlled timing and retain only a beyond-noise improvement.
- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff, Ruff format, repository-wide unused-symbol checks,
      `compileall`, and `git diff --check`.
- [x] Prove tests and unrelated production files remain unchanged.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Complete correctness/readability/architecture/security/performance review.

### Task 4: Integrate

- [x] Commit source only after all gates pass.
- [x] Refresh and commit codebase-memory graph after source commit.
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 036
      recommendation.
- [x] Commit Plan 035/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `14fb3ecbaf23fc6828c8e09d981058f2db29a17b`.
- Refreshed graph commit:
  `c1e0eb1d1c00eb8009af21a76248bd610a2453a0`.
- Production delta: 4 insertions, 9 deletions, net `-5` LOC
  (`40,092 -> 40,087`); functions remain 981 and classes/models remain 132.
- `uidetox.commands.watch.run`: 79 -> 74 lines, cyclomatic complexity
  15 -> 13, cognitive complexity 32 -> 25, loops 6 -> 5, and loop allocations
  1 -> 0. Loop depth remains 2 and loop-local linear scans remain 0.
- Stable 238-path poll work remains two intentional snapshot traversals, while
  dictionary probes fall 714 -> 476 (`-33.3%`). No helper, function, type,
  model, cache, index, watcher backend, schema, field, dependency, runtime
  pass, or compatibility path was added.
- Removed code is the explicit changed-list accumulator, its append mutation,
  duplicate membership/subscript probe, and comments that merely restated the
  adjacent changed/deleted expressions.
- Exact seven-scenario HEAD-versus-working-tree projection remains
  `49806c971e97713e0b1d1d96fd2f6d7bc95d3df8d3075f6b0858f9ca733d6bd0`.
  Startup, stdout, stderr, snapshot/analyzer/clear calls, exits, changed/new/
  deleted attribution, two-poll state mutation, and interruption are
  identical.
- All 59,049 typed five-key snapshot pairs produce identical ordered changed
  and deleted lists.
- Final nine-sample controlled medians improve beyond non-overlapping ranges:
  unchanged 238 paths `317.782 -> 280.564 ms` (`0.883x`), mixed 238 paths
  `309.899 -> 274.699 ms` (`0.886x`), unchanged 10,000 paths
  `366.160 -> 323.512 ms` (`0.884x`), and mixed 10,000 paths
  `361.143 -> 319.294 ms` (`0.884x`).
- Focused warning-strict watch/fileset tests pass 6/6 before and after. Full
  warning-strict pytest passes 1,451 tests with cache disabled in 407.85s.
- Scoped Ruff `E4,E7,E9,F`, full touched-file Ruff, Ruff format,
  repository-wide Ruff `F`, `compileall`, and `git diff --check` pass.
- Tests and unrelated production files are byte-unchanged.
- Wheel SHA-256:
  `74afbafe5e669a46c1f92d504cdba640568c4b809e57a90e3aaea1932c32d126`.
- Sdist SHA-256:
  `bc8968445dd024fd7f60ec8b1a3aa86596aacd0e46c467ee5c3d65a382439b3b`.
- Fresh-install metadata reports version 1.9.0, Python >=3.11, and 14
  dependency declarations. All 82 package modules import; CLI help/watch/map/
  prototype smokes and `pip check` pass.
- Checkout and fresh-installed canonical prototype both remain
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two canonical qualification replays remain byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/035.g2hb5W`.
- Refreshed graph contains 6,027 nodes and 25,784 edges and is bound to source
  commit `14fb3ecbaf23fc6828c8e09d981058f2db29a17b`.
- Multi-axis review: no findings / APPROVE.
- Remaining risk: `dict.get` treats an absent path and an invalid stored
  `None` mtime alike. `_snapshot` constructs only float `st_mtime` values, its
  signature is `dict[str, float]`, and all valid typed pairs plus exact
  orchestration probes pass. Supporting invalid `None` snapshots would require
  compatibility behavior outside this private contract.
- Plan 036 recommendation: measure and consolidate the four repeated
  frontend/backend/database/API rendering loops in
  `uidetox.commands.detect.run`. Refreshed graph reports 69 lines, complexity
  14, cognitive complexity 20, 5 loops, loop depth 1, and zero loop-local
  scans/allocations. Treat blast radius as CRITICAL because the dynamic CLI
  persists tooling/AST config before rendering. Preserve detection and save
  order, exact labels/spacing/tool order, optional frontend compatibility, AST
  output, and config serialization. Replace only proven repeated list
  rendering with existing `ProjectProfile` data; add no renderer helper,
  model, cache, wrapper, schema, fallback, or output reordering.

## STOP conditions

Stop without source integration if:

- path/root, startup, polling, attribution, analysis, output, clear, timestamp,
  state mutation, error, or interruption behavior changes;
- changed/new or deleted ordering, grouping, deduplication, or provenance
  changes;
- live config/fileset reconstruction changes;
- valid typed snapshot behavior differs in the differential matrix or probe;
- consolidation adds a helper, cache, index, watcher backend, compatibility
  layer, runtime pass, schema, or dependency;
- production LOC, complexity, cognitive complexity, or dictionary-probe work
  does not improve;
- controlled timing does not beat run-to-run noise;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
