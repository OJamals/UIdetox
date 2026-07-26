# Plan 020: Reproducible runtime-performance qualification and semantic hardening

> **Executor instructions**: Turn Plan 019's ad hoc timing evidence into a
> checked-in, path-safe benchmark. Profile before changing production code.
> Keep one `page.evaluate`, one `RuntimeElement`/`RuntimePage` capture model,
> one `FrontendMap`, and existing `RuntimeDomBudget` limits. Optimize only
> measured bottlenecks; delete or replace redundant work instead of adding
> caches, graphs, evidence types, or compatibility wrappers.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: HIGH
- **Depends on**: `plans/019-semantic-design-quality-engine.md`
- **Category**: performance
- **Planned at**: `6dd19f25aa84e740b3507a1d7aff4e49a07df090`
- **Execution status**: DONE; all implementation, correctness, packaging,
  invariant, performance, integration, and parity gates pass
- **Integration merge**: `8bda5d4a8b9bd0874fcac10f0e2b2236c0cf0e91`
- **Execution branch**: `codex/020-runtime-performance-qualification`
- **Execution worktree**:
  `/Users/omar/Documents/Projects/.uidetox-worktrees/020-runtime-performance-qualification`
- **Live baseline**: `HEAD`, `master`, `origin/master`, and remote
  `refs/heads/master` all equal `6dd19f25aa84e740b3507a1d7aff4e49a07df090`.
  Root is clean; origin contains only `master`.
- **Preserved worktrees**:
  `/private/tmp/uidetox-plan015.LWPJZ9` and
  `/private/tmp/uidetox-plan016.7aW4xu` remain dirty and untouched. Plan 016
  alone retains `34977dcf615a8688c38a43c5b4c8fc8ee2443738`.
- **Contention note**: an unrelated
  `/Users/omar/Documents/Projects/simpledoctor/.venv/bin/python -` process was
  using about one CPU at planning time. No benchmark evidence collected under
  that contention is admissible. Live execution proved this is a recurring
  batch, not one stale process: PID `60425` read `gmc medicine.pdf`, PID
  `14235` replaced it, and PID `62455` then read `IM corp.pdf`, each at roughly
  one saturated CPU. The accepted final run started and completed with no
  Simpledoctor process present. A macOS `mediaanalysisd` spike lasted under
  three seconds during controls; all samples were retained and its two visible
  outliers did not move the median beyond the required five-point margin.

## Why this matters

Plan 019 passed its ≤10% benchmark gate, but corrected isolated medians left
only 0.07 percentage points of generic full-wall margin and 7.80 points of
control full-wall margin. A separate evaluator-only run left only 0.22 points
of control margin. The benchmark itself was ephemeral, and an earlier result
was invalid because the frozen process imported the current checkout through
Python's working-directory path. Runtime evidence needs a durable,
independently reproducible qualification gate before further detector growth.

## Baseline evidence

- Final evaluator benchmark, alternating frozen `a97a7ad` and current 5+5:
  generic `-8.42%`, controls `+9.78%`, 3,000 emitted, one `page.evaluate`.
- Corrected isolated end-to-end benchmark, alternating 6+6:
  generic `+9.93%`, controls `+2.20%`.
- Warning-strict full suite: 1,396 passed with pytest cache disabled.
- Plan 019 review verdict: APPROVE.

## Scope

**In scope**:

- `benchmarks/runtime_observer.py` (new isolated controller/worker harness)
- `tests/test_runtime_benchmark.py` (harness contract tests)
- `uidetox/runtime_observer.py` only if profiling proves duplicated evaluator
  work or an unbounded geometry path
- `uidetox/design_semantics.py` only if profiling proves redundant Python
  semantic work
- `tests/test_runtime_observer.py`
- `plans/020-runtime-performance-qualification.md`
- `plans/README.md`

**Out of scope**:

- Another runtime traversal, persisted artifact, semantic graph, evidence type,
  cache layer, or compatibility wrapper.
- Changing `RuntimeElement`, `RuntimePage`, `RuntimeObservation`, or
  `FrontendMap` serialized public shapes for benchmark telemetry.
- Relaxing detector correctness, finding precision, DOM budgets, or the
  one-evaluation invariant to win time.
- Publishing a package release.
- Deleting or reconciling the dirty Plan 015/016 worktrees.

## Qualification contract

The checked-in harness must:

1. Launch every measured worker with `python -P`.
2. Use a neutral temporary working directory and an explicit single-code-root
   `PYTHONPATH`.
3. resolve and record the expected checkout root, imported `uidetox.__file__`,
   Python executable/version, platform, Git SHA/tree state, fixture, order,
   and all individual samples;
4. reject an imported package outside the expected root, duplicate checkout
   roots on `sys.path`, an unsafe current-working-directory entry, or any
   base/current root collision;
5. materialize the frozen base by exact Git ref, alternate base/current order
   by pair, and keep warmups separate from measured samples;
6. record full `observe_frontend` wall time and inner `Page.evaluate` time
   separately without adding a second evaluation;
7. require exactly one `page.evaluate`, identical canonical results,
   identical coverage/budgets, and expected candidate/emitted counts for every
   paired sample;
8. emit machine-readable JSON containing each sample plus median, min, max,
   p90, IQR, standard deviation, percent delta, and gate margin;
9. reject any median regression above 10%; Plan 020 targets at least five
   percentage points of margin for both full-wall and evaluator medians.

## Steps

### Step 1: Characterize the harness contract

Add RED tests for:

- `python -P` worker command construction;
- neutral `cwd`, exact import-root acceptance, and current/base/path-shadow
  rejection;
- strict alternating order and retained individual samples;
- independent full-wall/evaluator distributions;
- canonical-result, coverage, budget, emitted-count, and one-evaluate gates;
- deterministic JSON summaries and a failing >10% regression verdict.

Implement the smallest harness that passes. Keep orchestration in one module;
do not create a framework or benchmark package.

**Verify**:

```bash
.venv/bin/python -m pytest -q -W error -p no:cacheprovider \
  tests/test_runtime_benchmark.py
```

### Step 2: Collect uncontended baseline and profiles

Wait until unrelated CPU-intensive processes finish. Run the checked-in harness
against frozen `6dd19f25` and unchanged current code for generic, control, and
pathological-geometry fixtures. Record a warmup plus at least 5+5 measured
alternating samples.

Profile full worker wall time and inner evaluator time separately. Use browser
performance marks or a profiler inside the existing single evaluation to
localize evaluator work. Use Python profiling for post-evaluation semantic
attachment. Do not keep instrumentation that changes production evidence.

**Stop** if contention, thermal drift, path ambiguity, result mismatch, a
second evaluation, or budget drift invalidates the run.

### Step 3: Stress pathological spatial geometry

Add RED browser tests for oversized elements and coordinates that would span
an excessive number of spatial-grid cells. Require:

- exact finding/result parity with the bounded fallback;
- deterministic element/finding order;
- one `page.evaluate`;
- existing scan/candidate/emitted budgets;
- bounded runtime and no allocation proportional to geometric area.

Deepen the existing exact spatial policy only if the characterization exposes
an unbounded path. Do not add a second spatial index or detector.

### Step 4: Remove measured runtime waste

Change one measured root cause at a time. For each attempt:

1. add or preserve a failing characterization;
2. make the smallest replacement/deletion;
3. run focused correctness tests;
4. rerun the same benchmark/profile;
5. keep only gains larger than noise; revert neutral or slower attempts;
6. record kept and rejected attempts here.

Prefer eliminating repeated style, geometry, selector, descendant, paint, or
semantic work within existing caches and passes. Never skip required evidence.

### Step 5: Run all gates

Required:

```bash
.venv/bin/python -m pytest -q -W error -p no:cacheprovider \
  tests/test_runtime_benchmark.py tests/test_runtime_observer.py \
  tests/test_frontend_mapping.py tests/test_visual_semantics.py \
  tests/test_calibration_matrix.py
.venv/bin/python -m pytest -q -W error -p no:cacheprovider
.venv/bin/python -m ruff check --select E4,E7,E9,F,I <changed-python-files>
.venv/bin/python -m ruff format --check <changed-python-files>
.venv/bin/python -m compileall -q uidetox tests benchmarks
```

Also require:

- wheel build and exact metadata inspection;
- install into a fresh venv;
- import every packaged `uidetox` module from outside the checkout;
- `uidetox --help`, `uidetox map --help`, `uidetox review --help`;
- `pip check`;
- `git diff --check`, scoped secret scan, orphan/reference checks;
- one `page.evaluate`, one canonical runtime/map model, unchanged DOM budgets;
- final uncontended alternating benchmark distributions.

### Step 6: Review, integrate, and prove parity

Review tests first, then correctness, simplicity, architecture, security, and
performance. Update this plan with exact profile evidence, benchmark
distributions, production/test/docs LOC delta, deletions, rejected attempts,
remaining risks, and next plan. Commit only after every gate passes, merge into
`master`, push, then verify local `HEAD`, `master`, `origin/master`, and remote
server `refs/heads/master` are identical.

## Execution evidence

### Harness and root isolation

- Added one controller/worker module,
  `benchmarks/runtime_observer.py`. Every worker runs through the controller's
  active virtualenv interpreter with `-P`, a neutral temporary `cwd`, and one
  explicit `PYTHONPATH`.
- Frozen code is materialized from an exact Git ref. Pair order alternates
  base/current then current/base. Warmups and every measured sample remain in
  the JSON report.
- Provenance records and validates `uidetox.__file__`, all loaded
  `uidetox.*` module files, `sys.path`, expected/forbidden roots, `cwd`, Python,
  platform, Git SHA/tree state, fixture, sequence, and order. Mixed-root
  imports, unsafe working-directory entries, and root collisions fail.
- Canonical output, coverage, emitted count, DOM budget, element count, and
  exactly one `Page.evaluate` must match for every pair. Full-wall and inner
  evaluator distributions are independent.
- Fifteen harness contract tests pass. A real `python -P` worker smoke loaded
  11 `uidetox.*` modules, all under the expected root.

### Profile and retained replacement

- A pre-change CPU profile was explicitly marked non-qualification because the
  unrelated Simpledoctor process still used one CPU. It nevertheless localized
  active evaluator work: the pathological 3,200-control fixture spent
  2,749.668 ms of sampled time in `targetSpacingEvidence` and 207.723 ms in
  `addCandidate`; total evaluator wall time was 6.989802 s.
- Root cause: when an oversized target exceeded the spatial-cell budget, the
  exact fallback first materialized every peer in a `Set`, then scanned every
  peer, for every target. The 3,000-emitted case was quadratic even when the
  first peer reached the mathematical minimum shape gap.
- Replaced that fallback in place. Oversized targets iterate the existing
  canonical target records directly; bounded-grid targets keep the existing
  spatial index. The scorer exits only at the global lower bound (`-24` when
  any undersized target exists, otherwise `-12`), so no later peer can improve
  the result and original first-tie ordering remains exact.
- Post-change non-qualification profiling removed both
  `targetSpacingEvidence` and `addCandidate` from the top samples. A contended
  frozen/current smoke preserved the exact digest
  `b682a0b631fb69b9c55492296030803f2e982f5c8b4cddecc89ebf2906d00bd7`,
  one evaluation, and 3,000 emitted elements. Its `-31.36%` full-wall and
  `-38.23%` evaluator deltas are discarded as timing evidence.
- No neutral production attempt was retained. No cache, graph, artifact,
  evidence type, compatibility wrapper, second DOM pass, or second evaluation
  was added.

### Gate ledger

| Gate | Result |
|---|---|
| Exact fallback/browser + harness | 17 passed |
| Runtime/map/visual/harness focused suite | 109 passed |
| Full pytest, cache disabled, `-W error` | 1,412 passed |
| Scoped Ruff and format | pass |
| `compileall` | pass |
| Wheel build + metadata | `uidetox 1.9.0`; Python `>=3.11`; `tree-sitter>=0.25.0,<0.26.0` |
| Fresh wheel install/import walk | 82 modules imported |
| Fresh CLI + dependency checks | `--help`, `map`, `redesign`, `review`, `status`, and `pip check` pass |
| Invariants | one production `page.evaluate`; unchanged 10,000/3,000 DOM budgets; no new model marker |
| Final alternating benchmark | pass; 30 measured samples; every gate has >8.85 percentage points of margin |

### Final alternating qualification

Frozen `6dd19f25` and current alternated for five pairs after one warmup per
fixture. Workers used Python 3.12.13 with `-P`, neutral working directories,
and validated all loaded module roots. Every pair preserved its fixture's
canonical digest, one evaluation, 3,000 emitted elements, the 3,000-element
budget, and exact coverage.

| Fixture | Metric | Base median | Current median | Delta | Gate margin | Base/current IQR |
|---|---|---:|---:|---:|---:|---:|
| Generic | Full wall | 4.746373 s | 4.800831 s | +1.15% | 8.85 pp | 0.046279 / 0.038505 s |
| Generic | Evaluator | 3.739172 s | 3.773766 s | +0.93% | 9.07 pp | 0.041816 / 0.029012 s |
| Controls | Full wall | 5.139022 s | 5.028067 s | -2.16% | 12.16 pp | 0.096191 / 0.767274 s |
| Controls | Evaluator | 3.815528 s | 3.719584 s | -2.51% | 12.51 pp | 0.044224 / 0.784710 s |
| Geometry | Full wall | 7.349390 s | 5.091803 s | -30.72% | 40.72 pp | 0.071174 / 0.010766 s |
| Geometry | Evaluator | 6.005420 s | 3.740571 s | -37.71% | 47.71 pp | 0.074688 / 0.005981 s |

The machine-readable report retained all individual samples at
`/private/tmp/uidetox-plan020-final-benchmark.json` during execution. The
controls spread includes two current outliers (`4.528972` and `4.470465`
evaluator seconds) coincident with the brief system-daemon spike; the other
three current samples were `3.719584`, `3.682505`, and `3.685755` seconds.
Median, exact-result, and margin gates all passed without sample deletion.

### Change accounting, cleanup, and remaining risk

- Production: 13 insertions, 14 deletions, net **-1 LOC**.
- Tests: one new harness contract file plus one exact browser
  characterization; 435 inserted test LOC and no deleted test LOC.
- Tooling/docs: one checked-in benchmark module and this execution plan;
  generated venv/build/cache files remain excluded and are removed after the
  final run.
- Remaining risk is narrow: an undersized target anywhere in a capture lowers
  the safe early-exit bound to `-24`, so oversized peers may still require a
  full exact scan when no peer attains that bound. The existing 3,000-candidate
  cap keeps that work finite; no approximation was introduced.
- Two earlier benchmark attempts were aborted and discarded after a new
  Simpledoctor child appeared during each run. Benchmark worker/browser cleanup
  was verified after both interrupts; neither attempt contributed evidence.
- Next plan: no automatic Plan 021. Rebaseline after Plan 015/016 dirty
  worktrees and Plan 016's unique commit are explicitly reconciled, then choose
  the next measured product-quality gap.

## Done criteria

- [x] Checked-in `python -P` harness rejects path shadowing and records imports.
- [x] Frozen-base/current order alternates and every sample is retained.
- [x] Full wall and evaluator time have separate distributions.
- [x] Generic/control/pathological geometry preserve exact results.
- [x] One DOM evaluation, one runtime/map model, and existing budgets remain.
- [x] Measured regression margin is safely below the 10% gate.
- [x] Only profiled root causes changed; neutral attempts were reverted/logged.
- [x] Focused, full, Ruff, format, compileall, package, import, CLI, dependency,
      invariant, and benchmark gates pass.
- [x] Production LOC delta, cleanup, risks, and next plan are recorded.
- [x] Commits are reviewed, merged, pushed, and local/origin/server parity is
      proved.

## STOP conditions

- Frozen/current imports cannot be proven isolated.
- Unrelated contention or thermal drift makes distributions unreliable.
- Any optimization changes canonical evidence or ordering.
- A proposed fix needs another cache, graph, evidence type, wrapper, DOM pass,
  or relaxed budget.
- A measured attempt is neutral, slower, or inside run-to-run noise.
