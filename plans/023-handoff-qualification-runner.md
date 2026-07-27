# Plan 023: Deterministic handoff qualification schema and runner

> Replace Plan 022's hand-authored qualification accounting with one local,
> tool-agnostic benchmark manifest and deterministic verifier. Keep the agent,
> browser, and production CLI outside this runner. Reuse canonical redesign,
> source-manifest, preservation-contract, runtime-discovery, and screenshot
> evidence instead of creating another graph, cache, or evidence model.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: M
- **Risk**: MEDIUM
- **Depends on**: Plan 022
- **Category**: verification
- **Planned at**: `bcb8deff655e50f56e3496ffadeb9a44c7d622e2`,
  2026-07-27
- **Execution branch**: `codex/023-handoff-qualification-runner`
- **Execution worktree**:
  `/Users/omar/Documents/Projects/.uidetox-worktrees/023-handoff-qualification-runner`
- **Implementation commit**:
  `0f5c8af201fe42397e0757925e4c3c0dc3f1bfd1`
- **Live baseline**: root `HEAD`, `master`, `origin/master`, and remote
  `refs/heads/master` equal the planned-at SHA. Root is clean, one worktree
  existed before this plan, local and remote contain only `master`, and no
  benchmark/test process is running.
- **Archival stashes**: preserve Plan 016 as `stash@{0}` (`200608c`) and Plan
  015 as `stash@{1}` (`047d619`). Do not apply or drop either without explicit
  reconciliation evidence.

## Magic moment

A maintainer receives agent output from any tool, writes one small normalized
attempt manifest, and runs one local command. The command compares the actual
brief and report against the canonical redesign artifact, verifies every
source hash, contract, anchor, blocker, unknown, viewport, and screenshot,
then emits a byte-stable JSON report with exact missing/extra identities and
metric distributions. No hand-edited controller verdict is required.

## Measured baseline

Plan 022 proved the behavior but used manual accounting:

- controller verification JSON: 3,210 bytes, hand-authored after browser
  capture;
- exact identity comparisons: one-off Python commands;
- token and wall-time distributions: another one-off Python command;
- stale-stop and completed reports use different item shapes;
- agent JSONL is tool-specific and must not become a production dependency;
- no executable schema connects the attempt inputs to the final verdict;
- no command can deterministically reproduce the Plan 022 controller result.

The canonical inputs already exist:

- redesign proposal: preserved contracts, source targets, blockers, runtime
  unknowns, source manifest, runtime URLs, named viewports, viewport discovery,
  and screenshot paths;
- prototype brief: exact bounded handoff content and SHA-256;
- agent report: freshness checks, dispositions, implementation attempts,
  retries, output size, decision, and viewport handoff;
- controller/browser evidence: HTTP, console, overflow, screenshot dimensions,
  and screenshot hashes;
- normalized run metrics: wall time and token counts.

The missing seam is a benchmark-only validator and report format.

## Root cause

Plan 022 kept agent execution correctly outside UIdetox, but this also left
qualification orchestration outside executable code. The controller verdict
was assembled manually from canonical artifacts. Manual assembly can omit a
field, compare sets fuzzily, copy the wrong hash, or drift from the controller
prompt without a failing test.

This is not a reason to add an agent runner, browser adapter, or new evidence
model to the production CLI. It is a reason to make the local benchmark
boundary deterministic.

## Scope

In scope:

- one versioned JSON Schema for normalized attempt manifests;
- one benchmark-only Python runner;
- exact proposal lookup and canonical expected-value extraction;
- stale-source stop validation;
- completed-attempt source, identity, viewport, disposition, and artifact
  validation;
- optional normalized browser evidence with PNG dimension/hash checks;
- deterministic report writing and metric distributions;
- focused unit/CLI tests and a live replay of Plan 022 artifacts;
- full repository/package/invariant gates;
- exact LOC, artifact hashes, risks, and next plan.

Out of scope:

- launching or resuming an agent;
- parsing Codex, Claude, or another provider's event stream;
- launching a browser or dev server;
- adding a production `uidetox` command;
- adding a package dependency;
- adding a cache, graph, evidence type, compatibility wrapper, or
  renderer-specific model;
- changing `FrontendMap`, `ProjectMap`, redesign, prototype, runtime, or visual
  evidence production behavior;
- applying or dropping Plan 015/016 archival stashes;
- release, tag, or PyPI work.

## Architecture decision

Add `benchmarks/handoff_qualification.py` and
`benchmarks/handoff-qualification.schema.json`.

The normalized attempt manifest contains:

- schema version and stable attempt name;
- paths to one actual brief and agent report, resolved relative to the
  manifest;
- normalized wall/token metrics, independent of provider event format;
- optional normalized runtime evidence and screenshot paths.

The runner takes:

```text
python benchmarks/handoff_qualification.py \
  --redesigns /path/to/redesigns.json \
  --proposal-id REDESIGN-01-task-flow \
  --attempt /path/to/stale-attempt.json \
  --attempt /path/to/final-attempt.json \
  --output /path/to/report.json
```

It must:

1. extract expectations only from the selected canonical proposal and redesign
   set;
2. hash actual brief/report/screenshot bytes;
3. treat `blocked-stale-source` as a valid safety outcome only with an exact
   checked manifest, at least one exact mismatch, zero implementation attempts,
   and zero prototype output;
4. treat a completed attempt as passing only when ordered canonical identities,
   source hashes, blocker/unknown dispositions, and named viewport dimensions
   match exactly;
5. verify optional browser evidence without interpreting provider output;
6. emit no timestamps or absolute paths, so identical inputs yield identical
   bytes;
7. pass overall only when every supplied attempt passes and at least one
   completed attempt preserves the full handoff.

The JSON Schema documents the normalized boundary. The runner enforces the
security- and correctness-critical invariants directly with the Python standard
library; no JSON Schema runtime dependency is added.

## Steps

### Step 1: Freeze the missing executable contract

Write failing tests for:

- schema version and manifest field constraints;
- exact ordered contracts, anchors, blockers, unknowns, and viewports;
- source-manifest hashes and actual brief/report SHA-256;
- stale-source zero-write safety;
- PNG signature/dimensions/hash;
- deterministic output and distributions;
- missing, extra, duplicate, reordered, stale, and malformed evidence.

**Verify**: focused tests fail because the runner and schema do not exist.

### Step 2: Implement the normalized manifest boundary

Add strict stdlib loaders, relative-path resolution, numeric validation, and
critical schema checks. Reject booleans as numbers, non-finite metrics,
duplicate attempt names, unknown proposal IDs, malformed hashes, missing
files, and unsupported schema versions.

**Verify**: manifest and malformed-input tests pass.

### Step 3: Implement exact qualification accounting

Build one deterministic expected-value projection from the selected redesign
proposal. Validate stale-stop and completed reports without fuzzy matching or
provider-specific parsing. Keep missing, extra, reordered, duplicate, and
invalid-disposition evidence explicit in output.

**Verify**: exact-accounting tests pass; no production module changes.

### Step 4: Add deterministic artifacts and distributions

Hash brief/report/screenshots, parse PNG dimensions, validate normalized
browser evidence, compute stable distributions, and write sorted JSON with one
trailing newline. Preserve attempt order from the CLI.

**Verify**: two identical runs produce byte-identical output.

### Step 5: Replay Plan 022 end to end

Create external normalized manifests for the preserved Plan 022 stale-stop and
final attempts. Run the new verifier against the exact redesign, brief, report,
metrics, and real screenshots.

**Verify**:

- stale stop passes with one exact source mismatch and zero writes;
- final attempt passes 44/44 sources, 94/94 contracts, 34/34 anchors, 24/24
  blockers, 3/3 unknowns, and 3/3 viewports;
- browser evidence passes HTTP/console/overflow/PNG checks;
- metric distributions reproduce Plan 022's measured values;
- output is byte-stable and preserved outside the repository.

### Step 6: Run gates and review

Run focused and full warning-strict pytest, scoped Ruff/format, `compileall`,
wheel/sdist metadata/build, fresh install, all-module imports, CLI smokes,
`pip check`, source/artifact invariants, and `git diff --check`.

Review tests first, then correctness, simplicity, architecture, security,
performance, and artifact isolation. Report benchmark/test/docs/production LOC
delta, deletions, exact hashes, failures, remaining risks, and next plan.

### Step 7: Integrate and prove parity

Commit only after every gate passes. Merge into `master`, push, verify local
`HEAD`, `master`, `origin/master`, and remote server `refs/heads/master`
parity, then remove the short-lived branch/worktree. Refresh the shared graph
only if indexed source changed.

## Execution results

The stdlib-only runner replayed the exact preserved Plan 022 stale-stop and
final attempt artifacts. The stale stop passed with one exact
`frontend/src/App.tsx` mismatch, zero implementation attempts, zero files, and
zero output bytes. The recovered final attempt passed with:

- source manifest: 44/44 paths current;
- preserved contracts: 94/94 exact with valid preservation evidence;
- named source anchors: 34/34 exact with valid existence/preservation status;
- feasibility blockers: 24/24 exact with non-empty dispositions;
- runtime unknowns: 3/3 exact with non-empty dispositions;
- viewports: 3/3 exact;
- normalized runtime evidence: HTTP 200, zero console errors/warnings, zero
  horizontal-overflow viewports, and 3/3 PNG dimensions/hashes;
- recovery: one passing stale stop followed by one passing completed attempt;
- issues: zero in both attempts.

The byte-identical repeated report is 5,356 bytes with SHA-256
`98ff4b9899df516820a1aa1c10163e44c5857191ce573f7bcf9fbe44ad91c2a0`.
Normalized manifest SHA-256 values are
`b861ab9ef8c9b5275d5e12f9a62001dd6e857be14befdffa61b84f8df92aa6bb`
for the stale attempt and
`2a217bde0b6fd48aa9fa1d544a067115bccb5b42d10965866633c668dafc2ab2`
for the final attempt.

### Distribution

| Metric | Samples | Min | Median | Mean | P90 | Max |
|---|---:|---:|---:|---:|---:|---:|
| wall seconds | 30.03, 165.00 | 30.03 | 97.515 | 97.515 | 151.503 | 165.00 |
| input tokens | 185,033, 1,030,675 | 185,033 | 607,854 | 607,854 | 946,110.8 | 1,030,675 |
| cached input tokens | 148,011, 972,854 | 148,011 | 560,432.5 | 560,432.5 | 890,369.7 | 972,854 |
| cache-write input tokens | 37,004, 57,755 | 37,004 | 47,379.5 | 47,379.5 | 55,679.9 | 57,755 |
| output tokens | 1,688, 13,450 | 1,688 | 7,569 | 7,569 | 12,273.8 | 13,450 |
| reasoning output tokens | 394, 1,218 | 394 | 806 | 806 | 1,135.6 | 1,218 |
| retries | 0, 2 | 0 | 1 | 1 | 1.8 | 2 |
| implementation attempts | 0, 1 | 0 | 0.5 | 0.5 | 0.9 | 1 |
| output files | 0, 15 | 0 | 7.5 | 7.5 | 13.5 | 15 |
| output bytes | 0, 775,963 | 0 | 387,981.5 | 387,981.5 | 698,366.7 | 775,963 |

Completed-attempt contract-preservation accuracy is 1.0. The stale stop has no
contract-accuracy sample because it correctly stopped before implementation.

### Repository gates

- focused warning-strict pytest: 82 passed;
- full warning-strict pytest, cache disabled: 1,424 passed;
- scoped Ruff and Ruff format: pass;
- `compileall` for production and benchmarks: pass;
- wheel/sdist metadata and build: pass;
- final wheel: 499,759 bytes, SHA-256
  `9b6fce8b4806884fc1eefb2db2b310709734b2cf6baa34ab51c0b1d64ce55610`;
- fresh wheel install: 82 module imports, CLI
  version/map/redesign/prototype smokes, and `pip check` pass;
- repeated qualification, `git diff --check`, source/artifact/process/stash
  invariants, and five-axis review: pass;
- review verdict: APPROVE; no open correctness, readability, architecture,
  security, or performance blocker.

Production LOC delta is 0. Benchmark code/schema are +1,133 lines, tests are
+680 lines, and plan/docs are +342 lines. No pre-existing production,
test, benchmark, or archival artifact was deleted: the new runner replaces
external hand-accounting while preserving the exact Plan 022 evidence. Shared
strict-object, identity, measurement, and artifact-snapshot helpers removed
intra-runner duplication before commit. No dependency, production command,
cache, graph, evidence type, compatibility wrapper, provider parser, browser
launcher, or renderer-specific model was added.

Remaining risks:

- the two normalized manifests were written from one preserved Plan 022
  qualification, so cross-tool and cross-agent distributions remain
  unsampled;
- HTTP/console/overflow values remain normalized controller inputs; the runner
  verifies their values and screenshot bytes but does not launch or trust a
  browser itself;
- strict identity order intentionally rejects canonical reorderings, so future
  schema evolution must increment the manifest version instead of adding a
  compatibility path;
- triggered, authenticated, and failure runtime states remain unobserved in
  the preserved Plan 022 fixture.

Next plan: Plan 024 should run a repeatability matrix of fresh disposable-agent
attempts through this same schema, including injected stale, missing,
reordered, malformed, and runtime-recovery cases. It should establish
regression thresholds for wall time, tokens, retries, output size, and
contract accuracy without adding production orchestration or provider parsers.

## Done criteria

- [x] Versioned normalized attempt schema exists and rejects drift.
- [x] Runner is benchmark-only and provider/browser-launch agnostic.
- [x] Stale-source safety and completed exact preservation are deterministic.
- [x] Every canonical source, identity, blocker, unknown, and viewport is
      accounted for without fuzzy matching.
- [x] Browser screenshot dimensions/hashes and normalized runtime gates are
      verified when supplied.
- [x] Report bytes are deterministic across repeated runs.
- [x] Plan 022 stale and final artifacts replay successfully.
- [x] Focused, full, package, invariant, and review gates pass.
- [x] No production CLI/model/cache/graph/evidence/dependency is added.
- [x] LOC delta, artifacts, risks, and next plan are recorded.
- [x] Local/origin/server parity is proven after push.

## STOP conditions

- The runner needs provider-specific event parsing.
- The runner needs to launch an agent, browser, or dev server.
- Canonical values must be copied into a second production model.
- Passing requires fuzzy identity matching or dropped evidence.
- A benchmark overlaps unrelated sustained CPU-intensive work.
- Any archival stash changes without explicit reconciliation evidence.
