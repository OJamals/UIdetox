# Plan 022: End-to-end disposable-agent handoff qualification

> Execute from an isolated branch and worktree. Measure the real handoff before
> changing production code. Reuse the canonical `FrontendMap`, `ProjectMap`,
> runtime/visual evidence, and `frontend_map.preservation_contract`; do not add
> another graph, cache, evidence type, compatibility wrapper, or
> renderer-specific model. Preserve exact qualification artifacts and prompt
> boundaries. Merge and push only after every gate passes.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: M
- **Risk**: HIGH
- **Depends on**: Plan 021
- **Category**: product-quality
- **Planned at**: `dc022fbcd139719021348284c04799c598e3ea7d`,
  2026-07-26
- **Execution branch**:
  `codex/022-disposable-agent-handoff-qualification`
- **Execution worktree**:
  `/Users/omar/Documents/Projects/.uidetox-worktrees/022-disposable-agent-handoff-qualification`
- **Live baseline**: root `HEAD`, `master`, `origin/master`, and remote
  `refs/heads/master` equal the planned-at SHA. Root was clean, one worktree
  existed before this plan, origin contained only `master`, and no unrelated
  benchmark/test process was running.
- **Archival stashes**: preserve Plan 016 as `stash@{0}` (`200608c`) and Plan
  015 as `stash@{1}` (`047d619`). Do not apply or drop either without explicit
  reconciliation evidence.
- **Integration parity**: after the implementation push, local `HEAD`,
  `master`, `origin/master`, and remote server `refs/heads/master` all equaled
  `71407e8d254bf191f15b3423ab415d6c17e80812`; origin contained only `master`.

## Magic moment

A maintainer gives one generated full-stack prototype brief to a fresh,
context-isolated disposable agent. The agent builds a runnable prototype
without hidden project context, preserves every named source/API/database/UI
contract, respects freshness and blockers, reproduces the exact mapped
viewports, and returns measurable launch/verification evidence. A stale or
incomplete handoff stops safely, then succeeds after the canonical artifact is
refreshed.

## Measured baseline

The cold source-only walk used a disposable copy of
`examples/fullstack-slop-lab`, confirmed fixture intent, checkout production
code under safe-path mode, and no production edits:

- redesign artifact: 534,276 bytes;
- prototype brief: 34,679 bytes;
- 34 source targets and source-evidence records;
- 72 preserved contracts and 72 preservation-evidence records;
- 100 observable checks and 24 feasibility blockers;
- source freshness: `current`;
- runtime freshness: `absent`;
- runtime viewports/screenshots: empty.

A second walk started the disposable fixture, captured canonical runtime
evidence with screenshots, and reused that `FrontendMap` without refreshing it:

- runtime map: 4,836,870 bytes;
- redesign artifact: 580,318 bytes;
- prototype brief: 37,763 bytes;
- 94 preserved contracts and 94 preservation-evidence records;
- 123 observable checks and 24 feasibility blockers;
- runtime freshness: `current`;
- captures: mobile `390x844`, tablet `768x1024`, desktop `1440x900`;
- three exact screenshot paths.

The runtime prototype brief rendered neither the source manifest, canonical
preserved-contract identities, viewport names/dimensions, nor screenshot
paths. It only said to recapture at “the recorded viewports” and return
screenshots at “mapped viewports.” An isolated agent could not prove freshness
or recover the exact contract and viewport handoff from the brief.

## Root cause

`uidetox.redesign._proposal_evidence_freshness` reduces canonical runtime
capture evidence to viewport names and screenshot paths. That existing
structured freshness record is retained in the redesign artifact.

`uidetox.prototype.build_prototype_brief` then rendered only runtime status and
stale reason. It dropped the source manifest, canonical
`proposal.preserved_contracts`, and existing runtime `urls`, `viewports`,
viewport-discovery dimensions, and `screenshots` at the final agent boundary.
The first fresh qualification exposed the impact: the disposable agent
returned only 4 of 94 exact canonical contract identities. This was a
rendering omission, not a missing graph or evidence-model problem.

Codebase-memory inbound tracing classifies
`_proposal_evidence_freshness` and `build_prototype_brief` as **CRITICAL**
blast radius because redesign construction, workflow execution, artifact
round-trips, CLI prototype generation, and isolation tests consume them.

## Scope

In scope:

- exact runtime URL, named viewport, and screenshot handoff through the
  existing proposal freshness record;
- one context-isolated disposable agent consuming one generated full-stack
  prototype brief;
- exact artifact/prompt/output hashes and boundaries;
- stale-source failure, refresh, retry, and recovery evidence;
- contract/source-anchor/freshness/blocker/viewport preservation checks;
- input context, output size, wall time, retries, and preservation accuracy
  distributions;
- focused, full, package, and invariant gates.

Out of scope:

- adding an agent runner to the production CLI;
- changing runtime observation, visual-evidence, contract reconciliation, or
  viewport policy;
- adding another cache, graph, evidence type, compatibility wrapper, or
  renderer-specific model;
- merging disposable prototype code into UIdetox or the fixture;
- applying or dropping Plan 015/016 archival stashes;
- release, tag, or PyPI work.

## Architecture decision

Deepen the existing prototype renderer. Render the already-present source
manifest, canonical `proposal.preserved_contracts`, and
`evidence_freshness.runtime.urls`, `.viewports`, `.viewport_discovery`, and
`.screenshots` inside the isolated evidence block. Do not copy source,
contract, or runtime evidence into a new model.

Keep viewport identity canonical:

- redesign freshness retains named viewport values from `FrontendMap`;
- prototype rendering emits those values and canonical discovery dimensions
  exactly and deterministically;
- agent qualification proves output screenshots use each named viewport and
  exact width/height while keeping full-page PNG dimensions separate.

## Steps

### Step 1: Freeze the viewport handoff regression

Add failing tests for current runtime evidence with multiple URLs, ordered
viewport names, and screenshot paths. Assert every value is rendered inside
the untrusted evidence block and never outside it. Preserve legacy/absent
freshness behavior and brief-size bounds.

**Verify**: focused tests fail because current renderer drops all three fields.

### Step 2: Restore the existing freshness projection

Render runtime URLs, viewports, and screenshots from the existing freshness
mapping. Deduplicate and order deterministically at proposal construction;
perform no source probing in the renderer. Delete any duplicated rendering
logic made obsolete.

**Verify**: focused redesign/prototype/isolation/freshness tests pass. Source,
contract, blocker, and viewport counts remain exact.

### Step 3: Qualify an isolated disposable agent

Generate one full-stack brief from a fresh runtime map. Launch a fresh agent
with no conversation fork and an explicit working directory containing only:

1. the disposable fixture source;
2. the generated prototype brief;
3. a small trusted controller prompt that defines output paths and forbids
   reading UIdetox source, parent directories, prior transcripts, or hidden
   context.

Preserve exact input prompt, brief, agent event stream, final response,
prototype diff, screenshots, commands, and hashes.

**Verify**: agent implements only in the disposable target; UIdetox worktrees
remain untouched by agent code.

### Step 4: Exercise failure recovery

After brief generation, change one source file in a second disposable target.
The agent must detect source-manifest staleness and stop before implementation.
Refresh the canonical map/redesign/brief, retry once, and require success.

**Verify**: stale attempt writes no prototype source; recovery attempt consumes
the refreshed brief; retry count and wall time are recorded.

### Step 5: Verify preservation end to end

Compare generated artifacts, agent output, prototype source, runtime behavior,
and screenshots:

- every preserved contract appears and receives mapped, intent, or unresolved
  provenance;
- every named source anchor exists and remains inside the disposable fixture;
- source/runtime freshness is current at implementation start;
- every feasibility blocker/unknown is acknowledged or remains explicitly
  unresolved;
- mobile, tablet, and desktop handoffs survive with exact dimensions;
- backend/API/database sources remain unchanged;
- all fixture tests/build and launch commands pass.

Report exact numerator/denominator accuracy, missing/extra identities, and
retries.

### Step 6: Run repository gates

Run:

- focused redesign/prototype/frontend-map/project-map tests;
- full warning-strict pytest with cache disabled;
- scoped Ruff `E9,F,I` and format checks;
- `compileall`;
- wheel metadata/build/fresh-install/all-module-import/CLI/pip-check;
- source/artifact invariants and `git diff --check`;
- uncontended final qualification distributions.

Report production/test/docs/benchmark LOC delta, removed code, exact artifact
hashes, failures/recovery, remaining risk, and next plan.

### Step 7: Review, integrate, and prove parity

Review tests first, then correctness, simplicity, architecture, security,
performance, and artifact isolation. Commit only after every gate passes.
Merge into `master`, push, then verify local `HEAD`, `master`,
`origin/master`, and remote server `refs/heads/master` are identical.

## Execution evidence

### Qualification artifacts

Exact controller and disposable-agent artifacts live outside the repository at
`/Users/omar/Documents/Projects/.uidetox-qualification/022/agent-run-artifacts`.
The final evidence set is under `final/`.

- final controller prompt: 3,181 bytes,
  SHA-256 `5a641179f94a7f483435d07c03ebe368428fd40f72b4d465dfc9fa9286856e42`;
- final prototype brief: 48,349 bytes,
  SHA-256 `96cb4c066d67416b276e2250d1d83a1a2355e6fea0a162423239e045d6c7cd9d`;
- final agent event stream:
  SHA-256 `66e574f523bfc86161f7686802cfa4f858e99dca8efa5be0c1480de477c1c5cb`;
- final agent report: 48,062 bytes,
  SHA-256 `6d53806223255300ad0c3c7bfc5986ba39ffddbc18e0fdb381ce60d2be0acadf`;
- controller verification:
  SHA-256 `eea3e69431e39a0cfa186afe6930d628d01df52adae01cdaf8d1947bda14cacf`.

The stale attempt changed one mapped source after brief generation. It verified
the manifest, reported `blocked-stale-source`, wrote no prototype, and
preserved the exact expected/actual hash mismatch. The source was restored and
the canonical map/redesign/brief pipeline was regenerated before retry.

The first fresh attempt exposed a second root cause: without a direct canonical
contract list, its report preserved only 4/94 exact identities. A regression
test reproduced the omission. Rendering `proposal.preserved_contracts` fixed
the boundary; the final fresh agent then reported:

- source manifest: 44/44 paths current;
- preserved contracts: 94/94 exact, zero missing/extra;
- named source anchors: 34/34 exact, zero missing/extra;
- feasibility blockers: 24/24 exact, zero missing/extra;
- runtime unknowns: 3/3 exact, zero missing/extra;
- viewport handoffs: 3/3 exact.

The isolated agent could not bind localhost or launch Chromium under its
workspace sandbox. It reported both exact failures and kept reference copies
explicitly marked as placeholders. The controller recovered outside that
sandbox, launched the prototype, and captured real full-page PNGs:

- mobile: viewport `390x844`, PNG `390x1027`, 109,623 bytes,
  SHA-256 `06be06c599cfb65073c3b8f8ca48f4ca69b9af711d7e3e3e97094f7875fd2d9e`;
- tablet: viewport `768x1024`, PNG `768x1094`, 264,931 bytes,
  SHA-256 `a92a73982bb0db05b1f20ab80f4c221d50ed7a13329a38820d6f633c1d6d577b`;
- desktop: viewport `1440x900`, PNG `1440x942`, 346,214 bytes,
  SHA-256 `be5e04f567f30aaba2084b2c3ac1820f859119c957d409e85d0e6bb6fcf24dce`.

All three returned HTTP 200 with zero console errors/warnings and zero
horizontal overflow. The four-stage flow completed through `Choose outcome`,
`Review evidence`, `Set guardrails`, and `Activate`; completion exposed
`ACTIVATION SUMMARY`, `READY`, and an explicit inert-effect boundary.

### Distribution

| Run | Brief bytes | Wall s | Input tokens | Output tokens | Report bytes | Contract accuracy |
|---|---:|---:|---:|---:|---:|---:|
| stale-source stop | 43,282 | 30.03 | 185,033 | 1,688 | 2,436 | n/a |
| fresh before contract fix | 43,282 | 115.21 | 498,078 | 9,846 | 57,173 | 4/94 |
| final fresh | 48,349 | 165.00 | 1,030,675 | 13,450 | 48,062 | 94/94 |

Across three isolated attempts:

- wall seconds: min 30.03, median 115.21, max 165.00, mean 103.41;
- input tokens: min 185,033, median 498,078, max 1,030,675,
  mean 571,262;
- output tokens: min 1,688, median 9,846, max 13,450, mean 8,328;
- reasoning tokens: min 394, median 1,098, max 1,218, mean 903.33.

The final agent recorded one implementation attempt and two recovery retries.
The final prototype contained 14 files and 775,963 bytes before controller
capture, then 997,388 bytes with real screenshots.

### Repository gates

- focused warning-strict pytest: 120 passed;
- full warning-strict pytest, cache disabled: 1,407 passed;
- scoped Ruff `E9,F,I`: pass;
- Ruff format: pass;
- `compileall`: pass;
- wheel/sdist build and wheel archive integrity: pass;
- final wheel:
  SHA-256 `2ab3d2dcd6b6cf8b008dff552f105ea7d505c756c2387c33809774374d266f35`;
- fresh wheel install: 82 module imports, CLI version/map/redesign/prototype
  smokes, and `pip check` pass;
- prototype TypeScript check and production build: pass;
- `git diff --check`, source-preservation, artifact, process, and stash
  invariants: pass;
- code review: APPROVE; no correctness, architecture, security, or performance
  blocker.

Production delta is +22 LOC (`uidetox/prototype.py` +19,
`uidetox/redesign.py` +3); tests are +98 LOC. No baseline production code was
deleted because the defect was missing handoff data, not redundant behavior.
Consolidation removed 17 lines from the first implementation before commit.
No new cache, graph, evidence type, compatibility wrapper, dependency, or
renderer-specific model exists.

Remaining risks:

- triggered, authenticated, and failure runtime states remain unobserved;
- source-to-runtime ownership remains inferred without source maps;
- focus order and computed contrast still need dedicated runtime assertions;
- agent token consumption grows materially when every exact identity is
  reported, despite a 94.4% final input-cache hit rate;
- fixture `npm ci` reported two pre-existing high-severity audit findings;
  dependencies were not changed by this plan.

Next plan: Plan 023 should define a deterministic, tool-agnostic qualification
schema and local benchmark runner for exact handoff accounting, without adding
an agent runner or evidence model to the production CLI.

## Done criteria

- [x] One full-stack prototype brief is consumed by a context-isolated
      disposable agent.
- [x] Every contract, source anchor, freshness state, blocker, and viewport
      handoff is accounted for end to end.
- [x] Input context, output, wall time, retries, failure recovery, and
      preservation accuracy are measured.
- [x] Exact artifacts and prompt-isolation boundaries are preserved.
- [x] Canonical maps, visual evidence, and preservation-contract identities
      are reused.
- [x] No parallel cache, graph, evidence type, compatibility wrapper, or
      renderer-specific model is added.
- [x] Focused, full, package, invariant, and uncontended qualification gates
      pass.
- [x] Production LOC delta, deleted code, remaining risk, and next plan are
      recorded.
- [x] Local/origin/server parity is proven after push.

## STOP conditions

- The disposable agent can access conversation history or UIdetox source
  outside the bounded prompt/fixture.
- Meeting the handoff requires duplicating canonical map, contract, runtime,
  visual, or viewport evidence.
- Any contract, anchor, blocker, freshness state, or named viewport is dropped
  or approximated.
- The stale attempt changes prototype source before reporting the blocker.
- A benchmark overlaps unrelated sustained CPU-intensive work.
- Any archival stash changes without explicit reconciliation evidence.
