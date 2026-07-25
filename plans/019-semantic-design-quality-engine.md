# Plan 019: Replace guessed color checks with semantic design-quality evidence

> **Executor instructions**: Build on the runtime/app evidence graph from plans
> 015-018. Replace token-name Cartesian products; do not add another disconnected
> design score. Consolidate color, hierarchy, rhythm, and interaction-state
> evidence, then delete superseded heuristics. Update `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- uidetox/color_utils.py uidetox/analyzer_custom.py uidetox/runtime_observer.py uidetox/runtime_layout.py uidetox/visual_semantics.py uidetox/commands/review.py tests/test_color_utils.py tests/test_runtime_observer.py tests/test_visual_semantics.py tests/test_review.py tests/test_calibration_matrix.py`

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/015-unified-findings-and-verified-closure.md`, `plans/018-scenario-runtime-observation.md`
- **Category**: direction
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

The static color audit pairs every foreground-like token name with every
background-like token name, inventing combinations the UI never renders while
missing inheritance, alpha, gradients, images, themes, and modern color
formats. Runtime evidence already includes computed styles and geometry. A
single semantic design engine can detect actual contrast, palette-role drift,
weak hierarchy, inconsistent rhythm, collisions, focus/target issues, and
component inconsistency with source-owned evidence.

## Current state

- `uidetox/color_utils.py:223-274` selects tokens by naming conventions and
  Cartesian-products foreground and background sets.
- `uidetox/color_utils.py:277-308` checks four hardcoded common Tailwind pairs.
- Only hex values enter this contrast path.
- `uidetox/runtime_observer.py:1080-1129` already records computed color,
  background, font, line-height, spacing/layout, and state-related styles.
- `uidetox/runtime_layout.py:34-44` currently detects alignment, clipping,
  spacing, and line spacing.
- `uidetox/commands/review.py` asks for holistic A/B/C/D judgment; plan 015
  makes that review structured and freshness-bound.
- `docs/decisions/visual-evidence-capability.md` rejects perceptual image
  metrics as an aesthetic oracle pending representative evidence; preserve it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Color | `python -m pytest -q -W error tests/test_color_utils.py` | all pass |
| Runtime semantics | `python -m pytest -q -W error tests/test_runtime_observer.py tests/test_visual_semantics.py` | all pass |
| Review | `python -m pytest -q -W error tests/test_review.py tests/test_status.py` | all pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | design TP/FP/FN within budgets |
| Full | `python -m pytest -q -W error` | exit 0 |

## Scope

**In scope**:
- `uidetox/design_semantics.py` (create)
- `uidetox/color_utils.py`
- `uidetox/analyzer_custom.py`
- `uidetox/runtime_observer.py`
- `uidetox/runtime_layout.py`
- `uidetox/visual_semantics.py`
- `uidetox/commands/review.py`
- `tests/test_color_utils.py`
- `tests/test_runtime_observer.py`
- `tests/test_visual_semantics.py`
- `tests/test_review.py`
- `tests/test_status.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/design-evidence-model.md` (create)

**Out of scope**:
- Generating a replacement visual design or component library.
- Treating one palette/style as universally correct.
- SSIM/LPIPS/OCR as an aesthetic score.
- LLM-only findings without selectors, source targets, screenshots, or
  structured rationale.

## Cleanup and replacement constraints

- `color_utils.py` should shrink to parsing/normalization/compositing utilities;
  remove token-name pair generation and hardcoded pairing tables.
- One semantic-region/evidence graph supplies deterministic and subjective
  review consumers.
- Reuse plan 018 cached computed styles/geometry; no second DOM evaluation pass.
- Prefer a few calibrated causal detectors over many overlapping heuristics.
- Deduplicate issues by causal region/component and retain all underlying
  anchors.

## Git workflow

- Branch: `codex/019-semantic-design-quality`
- Commit by detector family: color/compositing, hierarchy/rhythm,
  interaction/occlusion, review integration, cleanup.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add rendered design oracles

Add paired positive/negative fixtures for:

- actual text/background contrast in normal and large-text thresholds;
- inheritance, transparency/alpha, overlays, gradients, images, and themes;
- RGB/HSL/OKLCH/CSS variables and unresolved dynamic values;
- hover/focus/disabled/error states;
- intentional versus inconsistent palette roles;
- coherent versus broken type scale/hierarchy;
- spacing rhythm and grouping across text/text, text/component, and
  component/component relationships;
- overlap/occlusion/offscreen/sticky-header coverage;
- target size and focus visibility;
- repeated component variants with accidental style drift.

**Verify**: current token Cartesian product produces the expected false-positive
cases and misses rendered cases.

### Step 2: Build normalized rendered color/compositing evidence

Resolve CSS variables and computed colors into a typed color value supporting
modern browser outputs. Walk actual paint ancestry to calculate effective
background layers and alpha compositing. Mark image/gradient/unknown backdrops
as unresolved unless browser evidence can establish a safe value. Evaluate the
rendered element/state pair, not every declared token combination.

**Verify**: actual pair fixtures match browser-computed expectations; unresolved
backgrounds never report clean contrast.

### Step 3: Model semantic visual hierarchy

Build a graph of source-owned runtime regions/components with:

- bounds and containment;
- typography scale/weight/line-height;
- color and contrast role;
- spacing/gap/padding relationships;
- interaction/state role;
- repetition/equivalence group;
- visual prominence signals and reading order.

Derive relationships from plan 018 cached measurements and plan 016 source
ownership. Do not copy raw DOM/style payloads into a second graph.

**Verify**: graph serialization is deterministic and maps every finding back to
route/state/viewport/selector/source.

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
spacing.

**Verify**: every detector has plan 014 positive/negative cases and respects
false-positive budgets.

### Step 5: Integrate structured subjective review

Pre-fill plan 015's A/B/C/D review artifact with deterministic evidence,
coverage matrix, screenshots, and linked findings. Human/agent judgment may
assess cohesion/craft/identity but must cite regions and rationale. The
subjective score cannot override an unresolved critical deterministic finding.

**Verify**: review becomes stale on evidence hash change and cannot be recorded
without dimension totals and coverage.

### Step 6: Delete guessed and duplicate checks

Remove foreground/background name Cartesian products, hardcoded Tailwind pair
tables, and runtime/static checks superseded by the semantic engine. Retain
static token inventory only where it provides design-system provenance.
Consolidate duplicated contrast math and region lookup.

**Verify**: grep finds no token cross-product loop or hardcoded pairing table;
color, runtime, review, calibration, and full suites pass.

## Test plan

- Modern color parsing and alpha compositing.
- Theme/state-specific actual contrast.
- Unknown gradient/image behavior.
- Hierarchy, typography, rhythm, grouping, and occlusion.
- Focus and target size.
- Equivalent-component drift.
- Source ownership and causal deduplication.
- Structured subjective review freshness/coverage.

## Done criteria

- [ ] Contrast uses actual rendered element/background pairs.
- [ ] Modern colors, alpha, themes, and states are represented.
- [ ] Hierarchy/rhythm/occlusion/focus/component drift are calibrated.
- [ ] Every finding carries route/state/viewport/source evidence.
- [ ] Subjective review consumes—not duplicates—the evidence graph.
- [ ] Token-name Cartesian products and duplicate detectors are deleted.
- [ ] Production-code delta and removed code are reported.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- Plans 015, 016, or 018 are incomplete.
- A detector needs an unsupported universal aesthetic assumption.
- Browser evidence cannot resolve a backdrop; emit unresolved coverage instead
  of guessing.
- New engine duplicates cached DOM/style/region data.

## Maintenance notes

Design policy belongs in calibrated detector metadata and review evidence.
Color parsing/compositing stays utility-level; causal findings stay in the
semantic engine.
