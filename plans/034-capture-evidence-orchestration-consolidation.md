# Plan 034: Capture evidence orchestration consolidation

## Status

DONE

## Magic moment

`uidetox capture --stage after` preserves exact responsive and desktop
capture, attribution, output, metadata, error, and `latest.png` behavior while
one shared evidence invocation/error path replaces two structurally duplicated
branches.

## Live baseline

Measured on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `e24ebfddf407231f5075ef4aeeda41d09fbf02f4`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 033 is DONE; Plan 034 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,764 edges and is bound to Plan 033 source commit
  `4ecb4b5c57cba53b110492062916a3bde7345678`;
- `uidetox.commands.capture.run` is a dynamic CLI entry point with filesystem,
  browser, runtime-observation, visual-evidence, and process-exit side effects.
  Treat blast radius as CRITICAL even though static inbound call tracing cannot
  see argparse dispatch;
- graph metrics are 171 lines, complexity 26, cognitive complexity 107,
  2 loops, loop depth 1, zero loop-local linear scans, and one loop allocation;
- production contains 40,106 lines, 981 functions, and 132 classes/models;
- tests contain 30,700 lines, 1,626 functions, and 40 classes;
- focused warning-strict baseline passes all 19 capture tests with cache
  disabled;
- Plan 033's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and repeated work

`VIEWPORT_REGISTRY` contains four base viewports:

- mobile `390x844`;
- tablet `768x1024`;
- desktop `1440x900`;
- wide `1920x1080`.

Source-boundary discovery over this repository produces ten ordered viewports:
the four base viewports plus `container-400-below`, `container-400-above`,
`container-600-below`, `container-600-above`, `media-768-below`, and
`media-768-above`.

The focused fixture contains 19 tests:

- four non-HTTP reachability cases;
- one successful reachability/close case;
- four low-level capture success/dependency/navigation cases;
- one responsive source-boundary discovery case;
- four direct `run` success cases covering BEFORE, desktop AFTER with/without
  baseline, and partial responsive AFTER;
- five parameterized `run` exit-one cases covering unreachable server, empty
  desktop BEFORE, empty responsive BEFORE/AFTER, and failed default capture.

The AFTER implementation currently contains:

- two source call sites for `_build_capture_evidence`;
- two `VisualEvidenceError` handlers;
- two `missing_dependency` policies that differ only by existing stdout
  indentation;
- one responsive captured-path scan that derives viewport ownership from
  `after_<viewport>.png` and filters to existing BEFORE files;
- one runtime-page projection keyed by viewport name;
- one evidence invocation at most per command execution.

Therefore the opportunity is source/cognitive consolidation, not removal of
runtime attribution work. Preserve the responsive scan and runtime-page
projection. Replace only the duplicated evidence invocation/error policy.

A 16-scenario behavioral probe freezes:

- unreachable server;
- default capture success/failure;
- desktop and responsive BEFORE success;
- empty BEFORE;
- desktop AFTER without baseline, with successful evidence, missing dependency,
  and fatal evidence error;
- responsive AFTER with successful evidence, no matching baselines, missing
  dependency, fatal evidence error, empty capture, and partial capture without
  desktop.

The projection executes seven evidence calls, has six exit-one outcomes and ten
successful outcomes, and hashes exact stdout, stderr, calls, exit state, and
file contents to:

`fa2b6c3c0b611c6a593adb89691c801eb57c7ba9c0b5afc4f7c8e9565a3c93a3`.

## Frozen behavior and side-effect contract

Preserve exactly:

- `url` argument precedence over configured `dev_server`;
- `load_config`, `_snapshots_dir`, `_visual_options`, expected-viewport
  initialization, reachability check, and stage dispatch order;
- non-HTTP/unreachable diagnostics, stderr routing, and exit code 1;
- BEFORE/default messages, blank lines, capture calls, filenames, tips, and
  exit behavior;
- `_capture_named_stage` call arguments and capture order;
- `runtime_pages` projection by viewport name;
- discovery-derived `expected_viewports` override after observation;
- responsive success with any non-empty partial capture;
- responsive pair order from captured AFTER order;
- viewport name derivation via `after_` prefix removal;
- per-pair BEFORE existence filtering and no evidence call when no pair exists;
- desktop singular `before.png`/`after.png` pairing;
- responsive and desktop visual-diff heading text;
- one `_build_capture_evidence` call with identical comparisons, snapshots,
  runtime pages, config, and visual options;
- `missing_dependency` as nonfatal with exact two-space responsive and
  three-space desktop indentation;
- every other `VisualEvidenceError` message on stderr and exit code 1;
- responsive per-viewport output order and required `diff["viewport"]` access;
- desktop first-result selection, empty-result fallback, coverage output, and
  optional diff-image output;
- responsive `diff_meta.json` schema
  `{"schema_version": 1, "comparisons": [...]}`;
- desktop legacy `diff_meta.json` payload as the single comparison object;
- responsive metadata write when evidence returns an empty list after a matched
  pair;
- desktop metadata omission when evidence returns an empty list;
- metadata omission for responsive no-pair and desktop no-baseline paths;
- atomic metadata writes and exact serialization;
- desktop no-baseline warning;
- responsive `latest.png` copy only when captured desktop exists;
- stale responsive `latest.png` deletion after partial capture without desktop;
- desktop `after.png` atomic copy to `latest.png`;
- all filesystem mutation, output, exception, and process-exit ordering.

## History and architecture

- `74081be` introduced the legacy BEFORE/AFTER/default stage flow.
- `168bf26` hardened failure exit behavior.
- `e582819` added server reachability and configured dev-server behavior.
- `69c2771` introduced deterministic typed visual evidence, responsive pair
  filtering, distinct responsive/desktop metadata schemas, missing-dependency
  fallback, and atomic `latest.png` behavior.
- `eb15515` routed screenshot capture through shared runtime observation and
  attached runtime pages/config to visual evidence.
- `7d34d60` preserved HTTP(S)-only reachability, closed responses, and exact
  diagnostics.
- `d5e6c25` added source-boundary viewport discovery and discovery-derived
  expected-viewport evidence.
- `577cfa8` removed orphaned compatibility seams without changing this
  orchestration.
- `_build_capture_evidence` is the existing canonical evidence module. Reuse
  it; add no wrapper.
- `_capture_named_stage` owns runtime capture and ordered partial success.
- `_atomic_write_json` and `_atomic_copy` own durable artifact mutation.
- Responsive pair discovery is intentional per-viewport attribution, not
  duplicate evidence computation.
- Responsive/desktop output and metadata remain different interfaces. Keep
  those projections distinct after the shared evidence call.

## Architecture decision

- Keep capture, attribution, output projection, metadata projection, and latest
  lifecycle in `run`; do not split the function merely to move lines.
- Build the responsive or desktop comparison list in its existing branch.
- Invoke `_build_capture_evidence` once syntactically after pair construction.
- Preserve mode-specific missing-dependency indentation with existing output.
- Return to distinct responsive/desktop result projection immediately after
  the shared call.
- Delete the duplicate evidence call and duplicate exception policy.
- Add no helper, function, type, model, enum, cache, graph, wrapper, facade,
  adapter, compatibility fallback, schema, field, dependency, or public
  interface.
- Keep tests unchanged because this is a pure refactor.
- Keep only if production LOC, cyclomatic complexity, cognitive complexity, and
  duplicated source orchestration all decrease without adding runtime passes.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the dynamic CRITICAL CLI and inspect exact source.
- [x] Inspect runtime/evidence helpers, tests, Git history, and blame.
- [x] Measure viewport/test distributions, duplicated orchestration, source
      metrics, and exact behavioral projection.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate evidence orchestration

- [x] Build mode-specific comparison pairs without changing order/filtering.
- [x] Replace two evidence invocations and handlers with one shared path.
- [x] Preserve distinct output, metadata, errors, and latest lifecycle exactly.
- [x] Reduce production LOC and graph complexity without a new symbol or pass.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 035
      recommendation.
- [x] Commit Plan 034/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `3d8d26b842eb04fcf5f480403ba6521691be848f`.
- Refreshed graph commit:
  `94e0150434d7b4e7f53f7104fd2241384f6f7786`.
- Production delta: 52 insertions, 66 deletions, net `-14` LOC
  (`40,106 -> 40,092`); functions remain 981 and classes/models remain 132.
- `uidetox.commands.capture.run`: 171 -> 157 lines, cyclomatic complexity
  26 -> 25, cognitive complexity 107 -> 86; loops remain 2, loop depth remains
  1, loop-local linear scans remain 0, and loop allocations remain 1.
- `_build_capture_evidence` call sites and `VisualEvidenceError` handlers both
  fall from 2 -> 1. No helper, function, type, model, cache, schema, field,
  dependency, runtime pass, or compatibility path was added.
- Exact 16-scenario HEAD-versus-working-tree projection remains
  `fa2b6c3c0b611c6a593adb89691c801eb57c7ba9c0b5afc4f7c8e9565a3c93a3`.
  Seven evidence calls, six exit-one results, ten successful results, stdout,
  stderr, arguments, filesystem artifacts, and exit state are identical.
- Nine alternating controlled samples of 3,000 mocked AFTER runs show no
  material regression: desktop median `40.171 -> 40.061 ms` (`0.997x`);
  responsive median `292.157 -> 300.178 ms` (`1.027x`) with heavily
  overlapping ranges.
- Focused warning-strict capture tests pass 19/19 before and after. Full
  warning-strict pytest passes 1,451 tests with cache disabled.
- Scoped Ruff `E4,E7,E9,F`, Ruff format, repository-wide Ruff `F`,
  `compileall`, and `git diff --check` pass. The touched file's sole full-Ruff
  `BLE001` finding at line 76 exists identically on the parent commit.
- Tests and unrelated production files are byte-unchanged.
- Final wheel SHA-256:
  `a95e120c5af48a1c7acebde9f7f66dd9bf7ac2e583994f52cdef3a94603580d3`.
- Final sdist SHA-256:
  `7f8d07812df89471bcde44e1372b70a94ead0a1fa9a4b6c1e585dc04f1d3cc02`.
- Fresh-install metadata reports version 1.9.0, Python >=3.11, and 14
  dependency declarations. All 82 package modules import; CLI help/capture/
  map/prototype smokes and `pip check` pass.
- Canonical prototype remains
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Canonical qualification remains
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still fails exactly with:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/034.cZ0LZm`.
- Refreshed graph contains 6,027 nodes and 25,769 edges and is bound to source
  commit `3d8d26b842eb04fcf5f480403ba6521691be848f`.
- Multi-axis review: no findings / APPROVE.
- Remaining risk is limited to shared local `pairs` truthiness selecting the
  evidence path. Exact differential coverage proves empty responsive and
  desktop no-baseline paths still skip evidence, while mode-specific result,
  metadata, error indentation, and latest projections remain separate.
- Plan 035 recommendation: measure `uidetox.commands.watch.run` polling-state
  and rendering orchestration. Refreshed graph ranks it highest among current
  production Python candidates at 79 lines, complexity 15, cognitive
  complexity 32, 6 loops, loop depth 2, and one loop allocation. Treat blast
  radius as CRITICAL; preserve initial scan, modified/new/deleted detection,
  sorted output, clear/timestamp behavior, Ctrl+C output, and polling
  lifecycle exactly. Replace only proven duplicate traversal or rendering;
  add no watcher abstraction, cache, event backend, compatibility layer, or
  output reordering.

## STOP conditions

Stop without source integration if:

- capture, attribution, output, error, metadata, serialization, or latest
  ordering changes;
- responsive partial success or desktop requirements change;
- pair order, viewport naming, source-boundary discovery, runtime-page
  ownership, or expected-viewport evidence changes;
- responsive and desktop metadata schemas become artificially unified;
- missing-dependency or fatal-error policy changes;
- consolidation adds a helper, model, cache, compatibility layer, runtime pass,
  or parallel authority;
- production LOC, complexity, cognitive complexity, or duplicated orchestration
  does not improve;
- controlled timing regresses materially;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
