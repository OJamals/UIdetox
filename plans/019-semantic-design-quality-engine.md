# Plan 019: Replace guessed color checks with semantic design-quality evidence

> **Executor instructions**: Build on the canonical runtime/application graph
> delivered by plans 015-018. Replace token-name Cartesian products; do not add
> another DOM pass, cache, graph, evidence model, or disconnected design score.
> Extend the existing `RuntimeElement` measurement payload and `FrontendMap`
> runtime nodes in place, consolidate color, hierarchy, rhythm, occlusion, and
> interaction-state evidence, then delete superseded heuristics. Root reviewer
> owns `plans/README.md`; executor must not edit it.
>
> **Drift check (run first)**:
> `git diff --stat a97a7ad..HEAD -- uidetox/color_utils.py uidetox/analyzer_custom.py uidetox/analyzer_engine.py uidetox/runtime_scenarios.py uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/frontend_map.py uidetox/visual_semantics.py uidetox/findings.py uidetox/commands/review.py uidetox/commands/status.py tests/test_color_utils.py tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_visual_semantics.py tests/test_findings.py tests/test_review.py tests/test_status.py tests/test_calibration_matrix.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/015-unified-findings-and-verified-closure.md`, `plans/016-application-semantics-and-source-ownership.md`, `plans/018-scenario-runtime-observation.md`
- **Category**: direction
- **Planned at**: commit `a97a7ad`, refreshed 2026-07-26
- **Refresh note**: the obsolete `d5898c9` base drifted by 3,131 insertions and
  657 deletions across eight originally scoped files while plans 015-018 landed.
  Current `master`, `origin/master`, and `HEAD` are
  `a97a7ad8b1775ad6a296ad29a0f34608f235eb83`. Baseline collection is 1,376
  tests. The root worktree was clean when this refresh was written.
- **Execution branch**: `codex/019-semantic-design-quality` in isolated worktree
  `/Users/omar/Documents/Projects/.uidetox-worktrees/019-semantic-design-quality`
- **Reviewed implementation SHA**:
  `0b60a1dfbe3eb6235836f781971a9622470a16ab`
- **Owner follow-up review**: `APPROVE`. The tangent target boundary is fixed
  and browser-covered; the retired token/config color subsystem, dead analyzer
  parameters, and obsolete tests are deleted. Warning-strict pytest passes with
  1,394 tests. Focused tests, Ruff, format, compileall, diff, wheel/install,
  module-import, CLI, dependency, secret, and orphan gates pass.
- **Performance evidence**: alternating frozen-base/current 6+6 measured
  -0.37% for the generic fixture and +0.06% for controls, both within the ≤10%
  gate.
- **Open gates**: none.

## Why this matters

The static color audit pairs every foreground-like token name with every
background-like token name, inventing combinations the UI never renders while
missing inheritance, alpha, gradients, images, themes, and modern color
formats. Runtime evidence already includes computed styles and geometry. A
single semantic design engine can detect actual contrast, palette-role drift,
weak hierarchy, inconsistent rhythm, collisions, focus/target issues, and
component inconsistency with source-owned evidence.

## Current state

- `uidetox/color_utils.py:223-274` still selects tokens by naming conventions and
  Cartesian-products foreground and background sets.
- `uidetox/color_utils.py:277-308` checks four hardcoded common Tailwind pairs.
- Only hex values enter this contrast path.
- `uidetox/analyzer_custom.py:551-609` separately guesses a Tailwind
  `bg-*`/`text-*` pairing from source classes.
- `uidetox/analyzer_engine.py:232-243` runs the project token audit as a
  separate scan-time producer.
- `uidetox/runtime_observer.py:52-87` is the canonical serializable
  `RuntimeElement`; it already carries bounds, computed styles, states,
  measurements, findings, and source hints.
- `uidetox/runtime_observer.py:1016-1925` owns the only DOM evaluation. Its
  `geometryCache`, `clippingCache`, `descendantCache`, and `measurementCache`
  already measure styles, rectangles, ancestry, text, and peers once and emit
  computed color/background/font/spacing plus scenario-state evidence.
- `uidetox/runtime_layout.py:37-47` currently attaches alignment, clipping,
  spacing, and line spacing.
- `uidetox/frontend_map.py:1094-1222` is the canonical semantic merge seam: it
  persists each runtime page/element as source-owned runtime nodes with
  route/state/viewport/selector/style/measurement/finding provenance.
  `uidetox/frontend_map.py:872-930` retains that graph with explicit freshness.
- `uidetox/visual_semantics.py:143-177` maps those runtime elements to existing
  source-aware visual regions. It must be deepened, not copied.
- `uidetox/commands/review.py:15-115` already records structured A/B/C/D
  judgment with finding links, route/state/viewport coverage, and current
  evidence hashes.
- `uidetox/findings.py:431-608` owns canonical objective/subjective scoring,
  review freshness, and finalization blockers. Design evidence must flow
  through this lifecycle rather than create another score path.
- `docs/decisions/visual-evidence-capability.md` rejects perceptual image
  metrics as an aesthetic oracle pending representative evidence; preserve it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Fresh environment | `python3.12 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e '.[dev,capture]' build ruff` | isolated interpreter; no reuse of root `.venv` |
| Dependency bound | `.venv/bin/python -c "from importlib.metadata import version; from packaging.version import Version; v=Version(version('tree-sitter')); assert Version('0.25') <= v < Version('0.26'), v; print(v)"` | installed `tree-sitter` is `>=0.25,<0.26` |
| Color/static replacement | `.venv/bin/python -m pytest -q -W error -p no:cacheprovider tests/test_color_utils.py tests/test_regressions.py -k 'color or contrast'` | actual-pair cases pass; obsolete guessed-pair cases are removed/replaced |
| Runtime semantics | `.venv/bin/python -m pytest -q -W error -p no:cacheprovider tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_visual_semantics.py` | one-pass semantic graph, source ownership, and deterministic serialization pass |
| Review/lifecycle | `.venv/bin/python -m pytest -q -W error -p no:cacheprovider tests/test_findings.py tests/test_review.py tests/test_status.py` | same evidence hash/coverage consumed; critical findings cannot be outscored |
| Calibration | `.venv/bin/python -m pytest -q -W error -p no:cacheprovider tests/test_calibration_matrix.py` | design TP/FP/FN and unsupported/degraded cases remain within manifest budgets |
| Full | `.venv/bin/python -m pytest -q -W error -p no:cacheprovider` | at least the 1,376-test baseline plus new tests passes, no warnings |
| Ruff | `.venv/bin/python -m ruff check --select E4,E7,E9,F,I uidetox/color_utils.py uidetox/analyzer_custom.py uidetox/analyzer_engine.py uidetox/runtime_scenarios.py uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/frontend_map.py uidetox/visual_semantics.py uidetox/findings.py uidetox/commands/review.py uidetox/commands/status.py tests/test_color_utils.py tests/test_runtime_observer.py tests/test_frontend_mapping.py tests/test_visual_semantics.py tests/test_findings.py tests/test_review.py tests/test_status.py tests/test_calibration_matrix.py tests/test_regressions.py` | exit 0 |
| Compile | `.venv/bin/python -m compileall -q uidetox tests` | exit 0 |

## Scope

**In scope**:
- `uidetox/design_semantics.py` (create only as pure cross-element detector
  policy over existing runtime/map types; no dataclass graph, cache, or
  persistence model)
- `uidetox/color_utils.py`
- `uidetox/analyzer_custom.py`
- `uidetox/analyzer_engine.py`
- `uidetox/runtime_scenarios.py`
- `uidetox/runtime_observer.py`
- `uidetox/runtime_layout.py`
- `uidetox/frontend_map.py`
- `uidetox/visual_semantics.py`
- `uidetox/findings.py`
- `uidetox/commands/review.py`
- `uidetox/commands/status.py`
- `tests/test_color_utils.py`
- `tests/test_runtime_observer.py`
- `tests/test_frontend_mapping.py`
- `tests/test_visual_semantics.py`
- `tests/test_findings.py`
- `tests/test_review.py`
- `tests/test_status.py`
- `tests/test_regressions.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/design-evidence-model.md` (create)

**Out of scope**:
- Generating a replacement visual design or component library.
- Treating one palette/style as universally correct.
- SSIM/LPIPS/OCR as an aesthetic score.
- LLM-only findings without selectors, source targets, screenshots, or
  structured rationale.
- `uidetox/visual_evidence.py` and its worker/protocol modules.
- `docs/decisions/visual-evidence-capability.md` (read-only preservation
  contract).
- New CLI commands, a second persisted artifact, or a second runtime traversal.

## Cleanup and replacement constraints

- `color_utils.py` should shrink to parsing/normalization/compositing utilities;
  remove token-name pair generation, project-wide pair guessing, and hardcoded
  pairing tables. Remove their analyzer-engine producer and stale tests.
- `FrontendMap` runtime nodes plus their existing `RuntimeElement` payload are
  the one semantic evidence graph. Do not introduce `DesignGraph`,
  `SemanticEvidence`, shadow region objects, a sidecar JSON file, or a new
  persistence/cache layer.
- Extend plan 018's `_RUNTIME_EVALUATE_SCRIPT`, `baseMeasurement`, and existing
  caches. One captured state performs exactly one `page.evaluate`; no selector
  re-query or second DOM walk may run in Python or review code.
- Plan 016 `ApplicationSemantics.source_ownership()` remains the only source
  ownership resolver. Do not recreate selector-to-file inference.
- Prefer a few calibrated causal detectors over many overlapping heuristics.
- Deduplicate issues by causal region/component and retain all underlying
  anchors.
- Use actual captured scenario states for hover/focus/disabled/error evidence.
  Never infer an interaction state from class names alone.
- Unknown gradients, images, blend modes, filters, backdrop effects, or
  unresolved colors become typed unresolved coverage, never a clean pass.

## Git workflow

- Branch: `codex/019-semantic-design-quality`
- Commit by detector family: color/compositing, hierarchy/rhythm,
  interaction/occlusion, review integration, cleanup.
- Create the branch/worktree from current `master`
  (`a97a7ad8b1775ad6a296ad29a0f34608f235eb83` at refresh time).
- Do not merge, push, or open a PR.

## Steps

### Step 1: Add rendered design oracles

First prove legacy failure: add paired positive/negative fixtures where the
current token Cartesian product reports a pair that never renders and where a
real inherited/alpha/state pair is missed. Then add oracles for:

- actual text/background contrast in normal and large-text thresholds;
- inheritance, transparency/alpha, overlays, gradients, images, and themes;
- browser-computed RGB/HSL/OKLab/OKLCH/`color()`/CSS variables and unresolved
  dynamic values;
- hover/focus/disabled/error states;
- intentional versus inconsistent palette roles;
- coherent versus broken type scale/hierarchy;
- spacing rhythm and grouping across text/text, text/component, and
  component/component relationships;
- overlap/occlusion/offscreen/sticky-header coverage;
- target size and focus visibility;
- repeated component variants with accidental style drift.

Use WCAG 2.2 AA boundaries exactly: normal text `4.5:1`, large-scale text
`3:1`, target-size minimum `24×24` CSS pixels with the standard spacing,
equivalent-control, inline, user-agent, and essential exceptions. Focus-visible
is required at AA; focus-appearance geometry is evidence/guidance, not
mislabelled as an AA failure.

**Verify**: new characterization tests fail against `a97a7ad`; current token
Cartesian product produces the expected false positive and misses the rendered
cases. Record red-test names before implementation.

### Step 2: Build normalized rendered color/compositing evidence

Record raw computed color strings plus normalized linear-sRGB RGBA values and
the exact element/ancestor layers used. Prefer the browser's computed value for
modern syntax; utility parsing is for normalized browser output and persisted
round trips, not a second CSS cascade. Composite alpha through actual painted
ancestors inside the existing `baseMeasurement`/`measurementCache`. Stop at the
first proven opaque backdrop. Mark image/gradient/blend/filter/unknown backdrops
as unresolved unless the same browser capture proves a safe effective value.
Evaluate the rendered element/state pair, not declared-token combinations.

**Verify**: actual pair fixtures match independently calculated browser
expectations; theme/state captures have distinct provenance; unresolved
backgrounds never report clean contrast; evaluator-call count remains one per
captured state.

### Step 3: Model semantic visual hierarchy

Deepen existing `FrontendMap` runtime nodes; do not build a new graph. Add
derived semantic relationships/metadata for:

- bounds and containment;
- typography scale/weight/line-height;
- color and contrast role;
- spacing/gap/padding relationships;
- interaction/state role;
- repetition/equivalence group;
- visual prominence signals and reading order.

Derive relationships from plan 018 cached measurements and plan 016 source
ownership. Cross-element detector functions receive the existing
`RuntimePage`/`RuntimeElement` collection and return findings to attach before
`_merge_runtime_evidence`. They may use ephemeral local indexes inside one
function call, but no retained cache or copied evidence model.

**Verify**: graph serialization is deterministic and maps every finding back to
route/state/viewport/selector/capture/source. Map round-trip and stale-runtime
retention tests preserve the new evidence without compatibility shims.

### Step 4: Add calibrated causal detectors

Implement separate typed detectors for:

- rendered contrast/accessibility;
- palette-role inconsistency;
- weak/accidentally equal hierarchy;
- type-scale and line-spacing inconsistency;
- spatial rhythm/grouping and edge contact;
- collision, occlusion, offscreen, and sticky coverage;
- focus visibility and target size;
- equivalent-component style drift.

Each finding includes confidence, metrics, causal peers, and remediation
constraints. Suppress only with explicit evidence; never auto-rewrite colors or
spacing. Reuse existing finding IDs where semantics are unchanged. Delete or
migrate older runtime-layout/static detectors when a new causal detector owns
the same defect; do not emit both.

**Verify**: every detector has plan 014-style positive, negative, boundary, and
unsupported/degraded cases and respects explicit false-positive budgets.
Equivalent-component and palette-role checks require evidenced equivalence or
intent; arbitrary visual similarity is insufficient.

### Step 5: Integrate structured subjective review

Build the review brief from the current frontend-map/runtime finding payload:
coverage matrix, screenshots, unresolved coverage, linked findings, and source
regions. Human/agent judgment may assess cohesion/craft/identity but must cite
regions and rationale. Recording remains bound to `current_evidence_hashes()`.
If any current deterministic finding is unresolved and critical, displayed
blended score and finalization eligibility must not let subjective input raise
the result above the objective score.

**Verify**: review becomes stale on any design-evidence hash change; cannot be
recorded without all dimension totals, route/state/viewport coverage, rationale,
and finding/region citations; pending critical evidence cannot be outscored.

### Step 6: Delete guessed and duplicate checks

Remove foreground/background name Cartesian products, hardcoded Tailwind pair
tables, the `analyzer_custom.py` Tailwind class-pair guess, its
`analyzer_engine.py` producer, and runtime/static checks superseded by the
semantic engine. Retain static token inventory only where it provides
design-system provenance. Consolidate duplicated contrast math, source lookup,
region lookup, and finding construction. Remove compatibility wrappers, stale
tests, dead imports, unused fixture paths, and orphaned modules/directories in
scope.

**Verify**:

- `rg -n 'audit_project_colors|_check_common_pairings|WCAG_COMMON_PAIR|WCAG_AA_VIOLATION' uidetox tests` returns no legacy producer/test references;
- `rg -n 'bg_names|fg_names|common_pairs' uidetox/color_utils.py uidetox/analyzer_custom.py` returns no guessed-pair implementation;
- no new persisted design artifact, graph class, cache, DOM evaluate call, or
  selector traversal exists;
- `git diff --exit-code a97a7ad -- docs/decisions/visual-evidence-capability.md`
  exits 0;
- focused, calibration, Ruff, compile, wheel, smoke, and full gates pass.

### Step 7: Qualify packaging, performance, deletion, and orphans

Build a wheel with `.venv/bin/python -m build --wheel` into a temporary
directory. Inspect wheel metadata for `Requires-Dist:
tree-sitter>=0.25.0,<0.26.0`; install that wheel into a second empty temporary
venv; run `uidetox --help`, `uidetox map --help`, `uidetox review --help`, and
an import smoke from outside the checkout.

Record before/after runtime evidence over the same deterministic rendered
fixture: wall time, capture `duration_ms`, candidate/emitted counts, and exact
`page.evaluate` count. Warm/cold noise may vary; required invariant is no
second evaluation/pass and no material median regression over at least five
runs. If median regresses by more than 10%, diagnose before approval.

Report production/test/docs insertions and deletions separately using
`git diff --numstat a97a7ad..HEAD`. List deleted symbols/files and prove no
references remain with `rg`, Ruff F/I, compileall, package import walk, and full
pytest. Do not count generated `.venv`, `dist`, caches, or codebase-memory
artifacts.

## Test plan

- Modern color parsing and alpha compositing.
- Theme/state-specific actual contrast.
- Unknown gradient/image behavior.
- Hierarchy, typography, rhythm, grouping, and occlusion.
- Focus and target size.
- Equivalent-component drift.
- Source ownership and causal deduplication.
- Structured subjective review freshness/coverage.
- One DOM evaluation per captured state and deterministic graph round-trip.
- WCAG boundary/exception cases for large text, target size, focus visibility,
  and focus obscuration.
- Legacy guessed-pair detector deletion and orphan-free imports.

## Done criteria

- [ ] Contrast uses actual rendered element/background pairs.
- [ ] Modern colors, alpha, themes, and states are represented.
- [ ] Hierarchy/rhythm/occlusion/focus/component drift are calibrated.
- [ ] Every finding carries route/state/viewport/source evidence.
- [ ] Subjective review consumes—not duplicates—the evidence graph.
- [ ] Token-name Cartesian products and duplicate detectors are deleted.
- [ ] One DOM evaluation and one canonical runtime/map evidence model remain.
- [ ] Fresh environment proves `tree-sitter>=0.25,<0.26`.
- [ ] Ruff E4/E7/E9/F/I, compileall, wheel metadata/install/CLI smoke pass.
- [ ] Benchmark, LOC/deletion accounting, and orphan checks are reported.
- [ ] `docs/decisions/visual-evidence-capability.md` is byte-for-byte unchanged.
- [ ] Production-code delta and removed code are reported.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- Plans 015, 016, or 018 are incomplete on current `master`.
- A detector needs an unsupported universal aesthetic assumption.
- Browser evidence cannot resolve a backdrop; emit unresolved coverage instead
  of guessing.
- New engine duplicates cached DOM/style/region data, requires a second
  `page.evaluate`, or persists a second graph/cache/evidence artifact.
- Source ownership cannot be expressed through plan 016's existing
  `ApplicationSemantics.source_ownership()` and `FrontendMap` merge.
- Fresh environment resolves `tree-sitter` outside `>=0.25,<0.26`.

## Maintenance notes

Design policy belongs in calibrated detector metadata and review evidence.
Color parsing/compositing stays utility-level; causal findings stay in the
semantic engine. `RuntimeElement` and `FrontendMap` remain serialized public
contracts: new fields require backward-compatible `from_dict` defaults and
round-trip tests, not a legacy shadow model. Delete replaced code in the same
commit family that migrates its final caller.
