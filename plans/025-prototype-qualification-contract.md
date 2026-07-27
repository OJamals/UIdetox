# Plan 025: Prototype qualification contract and runtime-state handoff

## Status

DONE.

## Magic moment

One generated `uidetox prototype` brief is the complete provider-agnostic
handoff. A disposable implementation agent can verify source freshness,
preserve ordered contracts and source anchors, acknowledge blockers and
unknowns, carry every named runtime scenario/state and viewport through its
report, recover from one bounded runtime failure, and return an externally
checkable v1 result without a benchmark-only controller prompt.

## Measured baseline

Repository baseline at `df929abad24ca5176b83d58131b14d4f46afb7a7`:

- `HEAD`, `master`, `origin/master`, and GitHub
  `refs/heads/master` are identical;
- root is clean; one worktree; local and remote contain only `master`;
- preserved Plan 015/016 archival stashes remain unchanged;
- no UIdetox pytest, qualification, Codex-agent, Vite, or Playwright driver
  process is running; unrelated long-lived Chrome Playwright helpers are
  outside this repository and must not be touched;
- Plan 024 warning-strict baseline is 1,425 passing tests;
- focused Plan 025 baseline is 32 passing tests;
- canonical Plan 022 brief is 48,349 bytes with SHA-256
  `96cb4c066d67416b276e2250d1d83a1a2355e6fea0a162423239e045d6c7cd9d`;
- the redundant benchmark controller prompt is 6,843 bytes and 131 lines with
  SHA-256
  `a013bad95f9e961577768271c88a748112c3eb59af9624e40d56c109ac7bf266`;
- a four-state `RuntimeObservation` maps `authenticated`, `triggered`, `empty`,
  and `error` into `FrontendMap.evidence.runtime_capture_matrix`;
- the same map also owns `runtime_diagnostics`, `runtime_coverage`, and
  `runtime_semantic_coverage`;
- `_proposal_evidence_freshness` drops all four canonical runtime fields;
- the resulting prototype brief is 41,840 bytes and 458 lines with SHA-256
  `0c60a7c8ef9705546c7404d00867bbf9556464fa2e50d1cafe808c4b81741e56`;
- that brief contains zero `authenticated`, `triggered`, or `empty` state
  identities. Incidental prose contains `error`, so string presence alone is
  not an acceptable state-preservation check.

Blast radius:

- `_proposal_evidence_freshness` is CRITICAL through `_build_proposal` and all
  redesign generation;
- `build_prototype_brief` is CRITICAL through persisted brief output, CLI,
  workflow, and direct tests.

## Root cause

Plan 018 already established the canonical runtime scenario/capture model.
`map_frontend` serializes its capture matrix, diagnostics, coverage, and
semantic coverage into the canonical `FrontendMap` evidence dictionary.
Plan 021's redesign freshness projection retained only runtime status, time,
URLs, viewports, discovery, screenshots, and stale reason. Prototype
generation therefore cannot emit the existing scenario/state evidence.

Plan 024 compensated with a second benchmark-owned prompt containing report and
runtime rules. That prompt fixed the qualification run but duplicated the
handoff contract instead of repairing the production brief boundary.

## Pre-registered acceptance contract

### Canonical evidence preservation

- Reuse only these existing `FrontendMap.evidence` paths:
  `runtime_capture_matrix`, `runtime_diagnostics`, `runtime_coverage`, and
  `runtime_semantic_coverage`.
- Preserve their JSON values and list order exactly through
  `RedesignProposal.evidence_freshness.runtime` and the isolated evidence block
  in the prototype brief.
- Preserve `capture_id`, `scenario`, `state`, URL, viewport, status, readiness,
  coverage, timing, and diagnostics without reclassification.
- Preserve source manifest, contracts, source targets/anchors, blockers,
  unknowns, viewports, discovery, screenshots, and observable checks exactly.
- Never infer a runtime state absent from canonical evidence.

### Versioned disposable-agent appendix

Emit one `Disposable-agent qualification contract (v1)` outside
`BEGIN_UIDETOX_EVIDENCE` / `END_UIDETOX_EVIDENCE`.

The appendix must:

- be provider-agnostic and require no transcript/event parser;
- require SHA-256 verification of both source-manifest groups before editing;
- hard-stop stale input with zero implementation attempts and zero prototype
  output;
- define exact completed and stale report keys and ordered identity fields;
- require one disposition/evidence row for every ordered contract, source
  anchor, blocker, unknown, runtime capture, and viewport;
- require `runtime_state_handoffs` to preserve capture-matrix order and exact
  `capture_id`, `scenario`, `state`, URL, and viewport identity;
- distinguish captured error UI states from browser/console/resource failures;
- keep unknown or blocked states unknown or blocked rather than inventing
  successful execution;
- require local or inline assets, an inline `data:` favicon, HTTP 200, zero
  console errors/warnings, zero failed or 4xx/5xx resources, and zero
  horizontal overflow at every named viewport;
- permit at most one localhost/browser-capture attempt and require bounded
  blocker reporting after the first sandbox bind/browser denial;
- require commands, exit codes, wall times, failures, recoveries, retry count,
  output file count/bytes, and pursue/revise/reject decision.

### Size and architecture limits

- Full-stack canonical brief may grow only by the report/runtime appendix and
  existing runtime evidence; no repeated contract catalog is allowed.
- Static appendix target: at most 8 KiB and 120 lines.
- Production scope: `uidetox/redesign.py` and `uidetox/prototype.py`.
- Prefer deletion: remove the 6,843-byte, 131-line benchmark prompt and its
  exact-hash test.
- Do not add a launcher, provider parser, cache, graph, evidence type,
  compatibility wrapper, renderer-specific model, or alternate preservation
  identity.
- `frontend_map.preservation_contract` remains the only preservation-contract
  identity.

## Scope

In scope:

- canonical runtime evidence projection from `FrontendMap` to redesign;
- provider-agnostic v1 report/runtime appendix in generated prototype briefs;
- exact unit/integration tests for evidence order and isolation boundaries;
- one multi-state map → redesign → brief qualification;
- regeneration and identity comparison against the canonical Plan 022
  full-stack redesign artifact;
- deletion of redundant benchmark prompt duplication;
- focused/full/package/invariant/review gates;
- production/test/total LOC and generated-artifact size measurements.

Out of scope:

- a new `uidetox` command or CLI option;
- launching an agent from production code;
- provider JSONL normalization or transcript parsing;
- changing runtime observation, `FrontendMap`, `ProjectMap`, visual evidence,
  or preservation-contract identity;
- applying or dropping the Plan 015/016 archival stashes;
- release, tag, or PyPI work.

## Steps

### Step 1: Freeze baseline and write regression tests

Record Git/worktree/branch/stash/process/remote parity, focused tests, brief
sizes/hashes, prompt duplication, and the four-state loss above.

Add tests that construct canonical runtime captures for `authenticated`,
`triggered`, `empty`, and `error`.

**Verify**: tests fail because canonical capture evidence and v1 appendix are
absent from the generated brief.

### Step 2: Preserve canonical runtime evidence

Extend `_proposal_evidence_freshness` with the four existing runtime evidence
paths. Do not reshape them.

**Verify**: exact deep equality and ordering hold at map, proposal, serialized
redesign, and brief boundaries.

### Step 3: Emit the v1 qualification appendix

Add one compact static appendix in `build_prototype_brief` after the isolated
evidence block. Reference evidence sections by name; do not repeat their
contents.

**Verify**: exact report keys, stale hard stop, ordered identities, bounded
runtime recovery, browser acceptance, and prompt-isolation position all pass.

### Step 4: Delete prompt duplication

Delete `benchmarks/handoff-qualification-prompt.md` and its exact-hash/semantic
contract test. Preserve the Plan 023 schema and deterministic runner.

**Verify**: no active code or test references the deleted prompt; generated
brief owns every non-provider-specific requirement.

### Step 5: Qualify multi-state and canonical full-stack handoffs

Run the four-state map → redesign → brief pipeline twice and compare bytes.
Regenerate the canonical Plan 022 full-stack brief from its persisted redesign
artifact and compare all ordered contracts, source manifests, blockers,
unknowns, viewports, discovery records, screenshots, and acceptance checks.

**Verify**:

- four-state capture matrix, diagnostics, coverage, and semantic coverage are
  byte-identical inside the evidence block;
- each runtime state has one exact ordered `runtime_state_handoffs` obligation;
- repeated generation is byte-identical;
- all prior Plan 022 identities remain present and ordered;
- v1 appendix is outside untrusted evidence;
- stale-source and bounded-runtime rules require no controller prompt.

### Step 6: Run repository and package gates

Run focused tests, full warning-strict pytest with cache disabled, scoped Ruff
and format checks, compileall, wheel/sdist metadata/build, fresh install, all
module imports, CLI smokes, `pip check`, Git/stash/process/artifact isolation,
and `git diff --check`.

**Verify**: all pass. Review correctness, simplicity, architecture, security,
performance, evidence isolation, and deterministic output.

### Step 7: Integrate and prove parity

Record execution results, distributions, production/test/total LOC delta,
deleted code, remaining risks, and Plan 026. Commit only reviewed passing
scope, merge to `master`, push, refresh graph after source changes, and prove
local/origin/server SHA parity. Delete temporary branch only after parity.

## Done criteria

- [x] canonical multi-state evidence survives map → redesign → prototype;
- [x] authenticated, triggered, empty, and error identities remain exact and
      ordered;
- [x] generated brief owns one provider-agnostic v1 attempt-report/runtime
      contract;
- [x] stale source hard-stops before implementation;
- [x] runtime recovery is bounded to one attempt;
- [x] every named contract, source anchor, freshness field, blocker, unknown,
      and viewport remains exact;
- [x] redundant benchmark prompt and test are deleted;
- [x] no parallel model/cache/graph/parser/wrapper/renderer seam is added;
- [x] full repository/package/invariant/review gates pass;
- [x] archival stashes remain unchanged;
- [x] local/origin/server SHA parity is proven.

## Execution results

Production now projects the existing `runtime_capture_matrix`,
`runtime_diagnostics`, `runtime_coverage`, and
`runtime_semantic_coverage` values through redesign freshness after one JSON
canonicalization. That canonicalization fixed the tuple/list persistence
boundary and keeps in-memory redesigns equal to their saved/loaded form.
Prototype generation emits the four values only inside the untrusted evidence
block and appends one trusted 4,898-byte, 39-line
`uidetox.disposable-agent-attempt.v1` contract.

The canonical Plan 022 brief retained every prior byte before the evidence
sentinel, every prior evidence byte after removing the four new empty fields,
and every prior acceptance/handoff byte. It grew from 48,349 to 53,358 bytes
(+5,009) with SHA-256
`dd6ecd44546a331c15bd7cb363657ba22b6b54dea7c8334f1285574d81e1a894`.

The final four-state full-stack brief is 49,670 bytes and 501 lines with
SHA-256
`1b9320ac6b559cf6e329e2ba8e038fdacd36f2e3e5640e8e600765bc8fb2ea10`.
Two independent generations were byte-identical. A final clean-fixture
regeneration after all code changes reproduced the same hash. It contains:

- 44 ordered source paths;
- 69 ordered preservation contracts;
- 34 ordered source anchors;
- 24 feasibility blockers;
- 3 runtime unknowns;
- 4 ordered runtime captures: authenticated, triggered, empty, and error;
- 3 ordered viewports: mobile, tablet, and desktop.

Every agent received only that brief plus a 140-byte controller prompt:
`Read UIDETOX-PROTOTYPE-BRIEF.md completely and execute its disposable-agent
qualification contract. Return only the required one-line final response.`
Its SHA-256 is
`3f1d5557b93c0cc7a471e433772a8653dd3d993b5f3140f7412dab19ed52b774`.

The first fresh disposable run preserved all 69 contracts but exposed two
appendix ambiguities: broad `completed-*` wording allowed
`completed-with-runtime-capture-failed`, and source-anchor wording duplicated
34 affected-module rows. The contract was narrowed to two exact completed
statuses and one row per Source target. The entire attempt restarted under a
fresh artifact root.

The recovery run passed every controller gate:

- exact status `completed-with-runtime-capture-blocker`;
- 44/44 source paths fresh before and after agent execution;
- 69/69 contracts exact, ordered, preserved, and evidenced;
- 34/34 source anchors exact, ordered, existing, and preserved;
- 24/24 blockers and 3/3 unknowns exact and ordered;
- 4/4 runtime captures exact through `capture_id`, scenario, state, URL, and
  full viewport value, with unknown states left unknown;
- 3/3 viewports exact and ordered;
- one implementation attempt, one report-generation retry, and one bounded
  localhost bind denial;
- no parent/repository/memory reads and no writes outside the disposable
  prototype path.

After the agent exited, controller capture returned HTTP 200 with zero console
errors/warnings, zero failed or 4xx/5xx resources, and zero horizontal
overflow at all viewports. Screenshot results:

- mobile: 390×934 PNG,
  `3470841a1bf285eb1c00caf5e4de0dfbc4b2804ed7c97588263eeb8478ace07a`;
- tablet: 768×1024 PNG,
  `aeff94575b89f8d6538900830cb62dffe7321cddfbaed5ff8be37d903f32309d`;
- desktop: 1440×900 PNG,
  `277b4652a327ef3dd85766a274d5dd8ca2531d95b188a8bf9c3540e29364aa52`.

The injected stale run checked all 44 paths, found exactly the mutated
`frontend/src/App.tsx`, returned `blocked-stale-source`, made zero
implementation/retry attempts, and created zero prototype files/bytes.

Fresh-attempt distributions, including the failed first contract version and
passing recovery:

- wall seconds: samples `[122.71, 135.23]`; min `122.71`, median/mean
  `128.97`, p90 `133.978`, max `135.23`;
- input tokens: samples `[334458, 511912]`; min `334458`, median/mean
  `423185`, p90 `494166.6`, max `511912`;
- output tokens: samples `[6513, 8320]`; min `6513`, median/mean `7416.5`,
  p90 `8139.3`, max `8320`;
- reasoning output tokens: samples `[989, 943]`; min `943`, median/mean
  `966`, p90 `984.4`, max `989`;
- retry count: samples `[0, 1]`; min `0`, median/mean `0.5`, p90 `0.9`, max
  `1`;
- prototype output bytes: samples `[10024, 10948]`; min `10024`,
  median/mean `10486`, p90 `10855.6`, max `10948`;
- report bytes: samples `[56982, 51913]`; min `51913`, median/mean `54447.5`,
  p90 `56475.1`, max `56982`;
- contract-preservation accuracy: both `1.0`; full-handoff gate: first failed,
  recovery passed.

The stale attempt measured 23.95 seconds, 165,137 input tokens, 1,527 output
tokens, zero retries, and zero prototype output.

Failure recovery also caught one repository defect: the first full suite run
had 1 failure and 1,424 passes because nested viewport tuples changed to lists
after redesign JSON persistence. The JSON boundary fix made the focused
round-trip regression and full suite pass.

Final gates:

- 33 focused warning-strict tests;
- 1,425 full warning-strict tests with cache disabled;
- scoped Ruff import/core checks and format;
- compileall and `git diff --check`;
- wheel and sdist build;
- fresh wheel install, metadata, 82 module imports, CLI version/map/redesign/
  prototype smokes, installed prototype generation, and `pip check`;
- installed canonical brief hash matched checkout;
- multi-axis review verdict: APPROVE;
- graph refresh: 6,005 nodes and 24,591 edges.

Package artifacts:

- wheel SHA-256:
  `7b38bd86fb6f11313048623443829f628f8a3c08025db9a3fc8740bdaf57456c`;
- sdist SHA-256:
  `d30f82b321fadd9c8123ad569ef60994b2c4bf17fa8cd71f5dd520a51ff8e4d7`.

Core qualification artifacts:

- final verification:
  `56351355c0afefd8ea719ea15a2092cbc503d39c90ed5b88c3faa063331b9cc3`;
- final agent report:
  `c82f0addb6b0d64399998e739d5fb844383f7ce48cb342cb493a9834d976e9d2`;
- stale verification:
  `ec826fbfc439fea05c54e385586b04fd5fbe966268f72418cf67b15122b091ae`;
- canonical preservation:
  `b9aa31383a107cfa15276a69b85d2ffcf01e8f6c87eaa13ea9f84db659fef1c0`;
- distributions:
  `8372d628aa7683ba6795c353e867a4fbba9d654fbc68048c03fe5c23c02c72d1`;
- 263-file, 7,246,145-byte evidence manifest:
  `f3913eccd0aadf0844b89726e0102c1f95f9a825d4b86d9912a83180b8887fb2`.

Exact artifacts live under:

- `/Users/omar/Documents/Projects/.uidetox-qualification/025-run-1`;
- `/Users/omar/Documents/Projects/.uidetox-qualification/025-recovery-1`;
- `/Users/omar/Documents/Projects/.uidetox-qualification/025-stale-1`.

Production LOC delta is +65: +51 in `prototype.py` and +14 in `redesign.py`.
Deleted/replaced code is the 131-line benchmark-only prompt and its 30-line
exact-hash test. Tests net +93 lines. Non-plan repository delta is +27 lines;
the executable/report contract paths themselves net -66 lines before tests.
No launcher, provider parser, cache, graph type, evidence type, compatibility
wrapper, renderer model, dependency, release, tag, or PyPI action was added.

Remaining risks:

- the final disposable agent needed one report-assembly retry after selecting
  the explanatory sentinel mention instead of the final evidence sentinel;
- authenticated, triggered, empty, and error identities survived exactly but
  remained honestly unknown in the disposable prototype rather than being
  re-executed as distinct browser states;
- the v1 report contract is emitted as trusted prose; the existing Plan 023
  runner does not yet validate `runtime_state_handoffs` directly;
- controller browser capture remains machine/toolchain dependent.

Plan 026 should extend the existing Plan 023 runner—not add a parallel
validator—to consume the emitted v1 report, validate exact runtime-state
handoffs, and qualify executable state-specific captures through the existing
`RuntimeScenario`/`FrontendMap` paths.

## STOP conditions

Stop and investigate before further changes if:

- canonical Plan 022 artifacts or source hashes drift;
- runtime evidence cannot be preserved without a parallel model;
- any runtime state must be inferred rather than read from canonical evidence;
- appendix placement crosses the evidence trust boundary;
- generated brief repeats the evidence catalog or exceeds the size target;
- a negative isolation/freshness case passes;
- archival stash identity changes;
- release, tag, or PyPI action becomes necessary.
