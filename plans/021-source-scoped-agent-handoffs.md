# Plan 021: Source-scope contract evidence and bound agent handoffs

> Execute from an isolated branch and worktree. Measure the real golden path
> before changing production code. Reuse the canonical frontend and project
> maps; do not add another graph, cache, evidence model, or compatibility
> wrapper. Run every gate, update this plan with final evidence, then merge and
> push only when all gates pass.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: M
- **Risk**: HIGH
- **Depends on**: plans 017, 019, and 020
- **Category**: product-quality
- **Planned at**: `8d1b58e0f5251c15afebe6924cf65818719ae3e7`,
  2026-07-26
- **Execution branch**: `codex/021-source-scoped-agent-handoffs`
- **Execution worktree**:
  `/Users/omar/Documents/Projects/.uidetox-worktrees/021-source-scoped-agent-handoffs`
- **Live baseline**: root `HEAD`, `master`, `origin/master`, and remote
  `refs/heads/master` all equal the planned-at SHA. Root is clean and origin
  contains only `master`.
- **Reconciliation prerequisite**: Plan 015 and Plan 016 dirty changes were
  preserved as `stash@{1}` (`047d619`) and `stash@{0}` (`200608c`), then both
  temporary worktrees were removed. Plan 015's merged branch was deleted.
  Plan 016's original branch remains as a local audit ref. `git range-diff`
  proves `34977dc` was conflict-aware transplanted as `e18ad76`; its follow-up
  patches have exact master equivalents `e55337e` and `5f54da6`.

## Magic moment

A frontend maintainer runs the documented intent → scan → map → redesign →
compare → prototype → status → loop journey on a real full-stack project. The
selected prototype brief is small enough for an agent to consume, names every
preserved contract exactly once, points each source-backed contract only to its
actual canonical source anchors, marks unanchored intent explicitly, and ends
with one clear next action. No contract truth is dropped or approximated.

## Measured baseline

The cold golden-path walk used a disposable copy of
`examples/fullstack-slop-lab`, the checkout interpreter with `python -P`, an
empty `PYTHONPATH`, and current production commands:

- `intent --require-confirmed --json`: 2,574 bytes, exit 0;
- `scan --path . --output json`: 52 exact findings, 104,232 bytes, exit 0;
- `map . --json`: 377 nodes, 495 edges, 930,677 bytes, exit 0;
- `redesign . --refresh-map --variants 3 --json`: three proposals,
  1,349,637 bytes, exit 0;
- `compare --json`: recommends `REDESIGN-01-task-flow`, exit 0;
- `prototype REDESIGN-01-task-flow --stdout`: 220,633 bytes, exit 0;
- `status --json`: exit 0;
- `loop`: exit 0 and correctly directs the user to `uidetox next`.

The prototype brief's isolated source-evidence section is 217,126 bytes across
452 lines: 98.41% of the whole brief, roughly 55,000 tokens for one proposal.
Proposal payload accounting identifies the growth:

- 34 source targets and 34 source-evidence records;
- 37 migration records;
- 72 preserved-contract evidence records totaling 101,278 characters;
- 100 observable checks totaling 100,599 characters.

## Root cause

`uidetox.redesign._build_proposal` assigns every preserved contract the full
proposal-wide `source_targets` tuple. `_observable_acceptance_checks` repeats
that same full module list for every preserved contract. On the measured
fixture, each of 72 contracts falsely claims representation in all 34 source
modules, producing Cartesian output and losing contract-to-source identity.

This is not a rendering-only issue. The canonical `ProjectMap` already retains
exact `SourceAnchor` records on contract nodes and lineage edges, while the
`FrontendMap` retains exact files for routes, actions, states, regions, and data
nodes. Proposal construction discards that identity, then the prototype
faithfully repeats the inflated evidence.

Codebase-memory inbound tracing classifies `_build_proposal`,
`_observable_acceptance_checks`, and `build_prototype_brief` as **CRITICAL**
blast radius because redesign commands, workflow execution, artifact loading,
prototype generation, and contract tests consume them.

## Scope

In scope:

- exact contract-to-source evidence derived from the existing canonical maps;
- truthful explicit/unresolved provenance when no source anchor exists;
- one structured preservation-evidence path consumed by proposal checks and
  prototype rendering;
- elimination of duplicate contract rendering in the agent-facing brief;
- deterministic scale and golden-path size guards;
- focused documentation for the agent-facing artifact contract.

Out of scope:

- changing static-analysis findings, runtime observation, DOM budgets, or
  contract reconciliation semantics;
- truncating, sampling, approximating, or silently dropping contracts;
- adding a second graph, cache, evidence dataclass, compatibility reader, or
  renderer-specific evidence store;
- optimizing full `map --json` output, whose purpose is exact machine-readable
  evidence;
- unrelated redesign strategy or UI changes.

## Architecture decision

Deepen proposal construction behind one private seam:

`_preserved_contract_evidence(frontend_map, preserved, brief)`

The seam returns the existing `preserved_contract_evidence` records. It must
resolve source modules from:

1. exact `FrontendMap` route/action/state/region/data nodes;
2. normalized canonical `ProjectMap` client-operation and lineage anchors;
3. explicit intent provenance when a user preservation rule has no source
   anchor;
4. explicit unresolved status when neither source nor intent evidence exists.

`_observable_acceptance_checks` consumes those records rather than the global
source-target set. `build_prototype_brief` renders the contract verification
once through observable checks and removes the duplicate raw contract and
contract-evidence lists. The full redesign artifact remains exact and
structured.

## Steps

### Step 1: Freeze the regression and output budget

Add failing tests that reproduce all-to-all attribution and the 220,633-byte
brief. Cover:

- one API contract with two exact frontend anchors among unrelated modules;
- frontend route/action/state preservation;
- explicit intent preservation without a false source claim;
- deterministic ordering and duplicate removal;
- the committed full-stack fixture golden path;
- a synthetic many-contract/many-source case proving output does not grow as
  contracts multiplied by unrelated sources.

The measured full-stack prototype brief must be below 65,536 bytes without
losing a contract, source-backed anchor, blocker, freshness state, lineage
finding, or observable verification.

**Verify**: new focused tests fail against the baseline for the measured
all-to-all attribution and size reasons.

### Step 2: Restore canonical source identity

Implement the private preservation-evidence seam using existing
`FrontendMap`/`ProjectMap` nodes, edges, normalization, and source anchors.
Match by typed contract category and normalized identity; never fuzzy-match
arbitrary prose. Preserve deterministic order. Explicit intent constraints
must cite intent provenance, not pretend to be source-mapped.

**Verify**: focused evidence tests pass; unrelated source modules never appear
on a contract record.

### Step 3: Remove repeated handoff evidence

Make observable checks consume canonical preservation evidence. Render every
preserved contract once in the prototype brief, followed by only cross-cutting
freshness, lineage, constraint, and intent checks. Delete renderer-local
contract duplication and any helper made obsolete.

**Verify**: the isolated evidence delimiters and injection-safety tests remain
exact; every contract still appears; the full-stack brief passes the 64 KiB
budget.

### Step 4: Stress scale and rewalk the product

Run the same disposable golden path under `python -P` and empty `PYTHONPATH`.
Record command wall time and output bytes before/after. Stress unrelated source
modules, repeated normalized routes, dynamic route parameters, source-less
intent constraints, and large contract sets. Confirm deterministic identical
output across repeated runs after removing run identity/timestamps.

**Verify**: no Cartesian contract/source attribution, no missing contract
truth, no new model/cache/graph, and one clear `uidetox next` handoff.

### Step 5: Complete repository gates

Run:

- focused redesign/prototype/project-map tests;
- full pytest with warnings as errors and cache disabled;
- scoped Ruff and format checks;
- `compileall`;
- wheel metadata/build/fresh-install/all-module-import/CLI/pip-check;
- source/artifact invariants and `git diff --check`;
- final golden-path size/timing distribution.

Report production/test/docs LOC delta, deleted code, before/after output
distributions, rejected attempts, remaining risk, and next plan.

### Step 6: Review, integrate, and prove parity

Review tests first, then correctness, simplicity, architecture, security, and
performance. Commit only after every gate passes. Merge into `master`, push,
then verify local `HEAD`, `master`, `origin/master`, and remote server
`refs/heads/master` are identical.

## Done criteria

- [x] Every preserved contract has exact source, explicit intent, or explicit
      unresolved provenance.
- [x] No contract inherits unrelated proposal-wide source targets.
- [x] Full redesign artifacts retain exact contract and lineage truth.
- [x] Prototype brief renders each preserved contract once.
- [x] Full-stack brief is below 64 KiB without truncation or approximation.
- [x] Scale tests prevent Cartesian contract/source growth.
- [x] Existing isolation, freshness, migration, and workflow behavior passes.
- [x] Full repository and package gates pass.
- [x] Production LOC delta, cleanup, risks, and next plan are recorded.

## Execution evidence

### Root-cause fix

- Added one private `_preserved_contract_evidence` seam. It preindexes the
  existing `FrontendMap` and `ProjectMap` once, then resolves each preserved
  contract by typed, normalized identity.
- Source-backed records retain only exact canonical module anchors. Explicit
  setup/brief constraints retain their intent provenance. A contract with
  neither source nor intent evidence is marked `unresolved`; it never inherits
  proposal-wide files.
- `_observable_acceptance_checks` now consumes those records. The prototype
  renderer deletes its duplicate raw-contract and evidence lists, so each
  preserved contract is rendered once.
- Promoted the existing frontend-map `_runtime_route` helper to
  `runtime_route` and reused it in redesign evidence. This fixed the review's
  only required finding: query-bearing runtime routes such as
  `/dashboard?view=all` must retain their exact identity.
- No graph, cache, evidence type, compatibility wrapper, dependency, or DOM
  evaluation path was added.

### Test-first and scale evidence

The initial focused run failed for the intended reasons:

- unrelated source files appeared on a data contract;
- an explicit intent rule falsely claimed source representation;
- the measured full-stack brief was 208,778 bytes, above the 65,536-byte gate.

The final focused set covers exact route, action, state, form, data, query
route, intent, and full-stack source identity. A synthetic case with 25
contracts and 51 unrelated source targets proves records do not multiply by
the unrelated source set and keeps each observable check below 150
characters. Final focused result: **125 passed**.

### Golden-path result

The uncontended final walk reused the same disposable full-stack fixture,
checkout interpreter, `python -P`, empty `PYTHONPATH`, command order, and
confirmed intent as the baseline:

| Command/artifact | Baseline | Final | Delta |
|---|---:|---:|---:|
| `redesign --json` | 1,349,637 bytes | 534,276 bytes | -60.41% |
| prototype brief | 220,633 bytes | 34,680 bytes | -84.28% |
| isolated source-evidence section | 217,126 bytes | 31,172 bytes | -85.64% |

The final artifact still contains all 34 source targets, 72 preserved
contracts, 72 preservation-evidence records, and 100 observable checks.
Every contract is present. Evidence status is 68 `mapped` and 4 `intent`;
zero records retain all 34 proposal files. Mean exact source count is 2.083;
the maximum is 15 for a genuinely shared action contract. The loop still
directs the user to `uidetox next`.

Five final samples, sorted:

- redesign wall ms: `1117.103`, `1122.045`, `1124.970`, `1127.721`,
  `1128.759` (median `1124.970`);
- prototype wall ms: `132.727`, `135.791`, `138.053`, `139.155`, `139.983`
  (median `138.053`);
- every redesign output: `534276` bytes;
- every prototype output: `34680` bytes;
- every artifact has canonical SHA-256
  `4171d32e5b686f7a1ae1f7d0b8b672f1e382aef054f8b20c23e87733313c878a`
  after removing only `generated_at` metadata.

### Repository and package gates

- Full warning-strict suite:
  `python -P -m pytest -W error -p no:cacheprovider -q`:
  **1,416 passed in 26.79s**.
- Scoped Ruff `E9,F,I`, Ruff format check, `compileall`, and
  `git diff --check`: pass.
- Wheel metadata: `uidetox` `1.9.0`, Python `>=3.11`, and exact
  `tree-sitter>=0.25.0,<0.26.0` requirement: pass.
- Fresh Python 3.12 install imports from site-packages, imports all 82 modules,
  passes package/`map`/`redesign`/`prototype` CLI smoke tests, and
  `pip check` reports no broken requirements.
- Existing isolation, freshness, prompt-injection, migration, project-map,
  workflow, and exact-artifact tests remain green.

### Rejected attempts

- Discarded one walk when an unrelated Simpledoctor Python process consumed
  sustained CPU. Its child was terminated and no timing was retained.
- Discarded one fixture copy before measurement because ignored confirmed
  `.uidetox` intent state was absent.
- Discarded one CLI invocation that used nonexistent `uidetox.__main__`.
  Final qualification invokes the installed entrypoint with its interpreter
  under `python -P`.
- Discarded one hash comparison whose volatile-field filter omitted
  `frontend_map_generated_at`. A direct two-run diff proved the only changing
  fields were `generated_at` and `frontend_map_generated_at`; the final
  five-sample canonical comparison removes those metadata fields only.

### Change accounting, review, and next plan

- Production: 106 insertions, 31 deletions, net **+75** lines.
- Tests: 172 insertions, no deletions.
- Plans/docs: 341 insertions, no deletions.
- Cleanup: deleted 12 duplicate prototype-rendering lines and replaced the
  all-to-all contract/source path instead of adding a parallel model.
- Review verdict: **APPROVE**. Correctness, architecture, security,
  determinism, performance, and packaging have no remaining required finding.
- Remaining risk: `redesign.py` is still a large module, and genuinely shared
  generic actions can correctly resolve to many source files. Extracting a new
  module now would add a seam without measured benefit; exact scale tests guard
  the current behavior.
- Next Plan 022 should qualify the generated handoff with a disposable agent
  implementation: consume one prototype brief, preserve every named contract,
  verify failure recovery and freshness, and measure context/output cost
  end-to-end before changing more production code.

## STOP conditions

- Required source identity is absent from both canonical maps.
- Meeting the budget requires dropping, truncating, sampling, or approximating
  contract evidence.
- A proposed fix introduces another evidence model, cache, graph, or
  compatibility wrapper.
- Full-stack contract truth or prompt-isolation behavior regresses.
- A benchmark run overlaps unrelated sustained CPU-intensive work.
