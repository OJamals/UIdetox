# Plan 024: Disposable-agent handoff repeatability matrix

## Status

DONE.

## Magic moment

Three fresh, isolated disposable agents receive the same canonical full-stack
prototype brief and independently return implementations that preserve every
ordered contract, source anchor, freshness check, blocker, unknown, and
viewport. One stale-source run stops before implementation. Deterministic
missing, reordered, and malformed mutations fail with exact diagnostics. A
controller recovers browser evidence without crossing the prompt-isolation
boundary. The existing Plan 023 runner emits the final distributions.

## Measured baseline

Repository baseline at `acd7d525028cb69e9c71dee089ed80695f60bf26`:

- root, `master`, `origin/master`, and remote server are identical;
- root is clean; one worktree; local and remote contain only `master`;
- preserved Plan 015/016 archival stashes remain unchanged;
- no pytest, qualification, Codex agent, Vite, or Playwright benchmark process
  is running;
- Plan 023 warning-strict baseline is 1,424 passing tests;
- Plan 023 qualification report is 5,356 bytes with SHA-256
  `98ff4b9899df516820a1aa1c10163e44c5857191ce573f7bcf9fbe44ad91c2a0`;
- canonical Plan 022 brief is 48,349 bytes with SHA-256
  `96cb4c066d67416b276e2250d1d83a1a2355e6fea0a162423239e045d6c7cd9d`;
- completed Plan 022 attempt measured 165.0 wall seconds, 1,030,675 input
  tokens, 13,450 output tokens, 2 retries, 775,963 output bytes, and 1.0
  contract-preservation accuracy;
- stale Plan 022 attempt measured 30.03 wall seconds, 185,033 input tokens,
  zero retries, and zero prototype output.

The Plan 023 runner already validates the canonical `FrontendMap`,
`ProjectMap`, redesign, prototype brief, visual evidence, and
`frontend_map.preservation_contract` identities. Its `qualify` blast radius is
CRITICAL through the CLI and direct tests. Do not change it unless a live
matrix failure proves a runner defect.

## Pre-registered regression thresholds

Apply these thresholds only to the three fresh completed attempts. Stale-stop
metrics remain reported but cannot make a completed cohort appear faster or
smaller.

- completed attempts: exactly 3, all passing;
- stale stops: at least 1 passing, followed by a passing completed attempt;
- contract-preservation accuracy: minimum 1.0;
- wall time: p90 at most 330.0 seconds (2.0× Plan 022);
- input context: p90 at most 1,546,013 tokens (1.5× Plan 022, rounded up);
- output tokens: p90 at most 20,175 (1.5× Plan 022);
- output size: p90 at most 1,163,945 bytes (1.5× Plan 022, rounded up);
- retries: maximum 3;
- runtime: HTTP 200, zero console errors/warnings, zero horizontal-overflow
  viewports, and all three named screenshots verified for every completed
  attempt.

Any threshold change after the first disposable-agent launch invalidates the
run and requires a fresh matrix under a new artifact directory.

## Scope

In scope:

- one exact Plan 022 brief and controller prompt reused byte-for-byte;
- one injected stale-source attempt and three fresh completed attempts;
- separate disposable working directories and ephemeral agent sessions;
- exact prompts, event streams, stderr, last messages, timing, source hashes,
  reports, prototypes, runtime screenshots, normalized manifests, and verdicts;
- controller-side runtime recovery after each agent session ends;
- Plan 023 normalized manifests and deterministic qualification runner;
- deterministic missing, reordered, and malformed negative mutations;
- completed-cohort distribution and pre-registered threshold evaluation;
- focused/full repository gates, package gates, invariants, review, LOC, and
  artifact hashes.

Out of scope:

- a production agent launcher, browser launcher, or `uidetox` command;
- parsing provider event formats in production or benchmark code;
- a new cache, graph, evidence type, compatibility wrapper, renderer model, or
  alternate contract identity;
- changing `FrontendMap`, `ProjectMap`, redesign, prototype, runtime observer,
  visual evidence, or preservation-contract production behavior without a
  reproduced root-cause defect;
- applying or dropping the Plan 015/016 archival stashes;
- release, tag, or PyPI work.

## Architecture decision

Use `codex exec --ephemeral --ignore-user-config --ignore-rules` with one
workspace-write sandbox per attempt. Each fresh directory starts from fixture
commit `a80c9d8` plus only the canonical brief and its explicitly named
`.uidetox` evidence. The prompt forbids parent-directory, transcript, memory,
and unlisted evidence reads.

Run attempts sequentially while the machine is otherwise uncontended. Preserve
provider JSONL as opaque evidence; a controller-only normalization step writes
the Plan 023 manifest. The repository must not gain a provider parser.

Agent browser/server failure is an expected isolation outcome. After the agent
session closes, the controller may install/run the returned prototype and
capture the three canonical viewports. Those bytes enter only the normalized
runtime manifest and never return to the disposable agent.

Negative cases are copies of preserved normalized inputs. Mutate one dimension
per case and prove the existing runner rejects it. Never mutate the canonical
brief, redesign, source tree, positive reports, or screenshots.

## Steps

### Step 1: Freeze baseline and thresholds

Record Git/worktree/stash/process/remote parity, Plan 023 report metrics, exact
brief/prompt hashes, tool versions, machine facts, and the thresholds above
before launching an agent.

**Verify**: baseline artifact is immutable and hashes match preserved Plan
022/023 inputs.

### Step 2: Materialize isolated attempts

Create one stale and three fresh directories from fixture commit `a80c9d8`.
Copy only canonical named evidence and the byte-identical brief. Write a
controller artifact manifest covering every input byte and prompt-isolation
boundary.

**Verify**: tracked source hashes match the brief; fresh directories have no
prototype or agent report; attempt paths are mutually disjoint.

### Step 3: Prove stale-stop behavior

Change one tracked source byte after copying the brief, run a fresh ephemeral
agent, and preserve its complete output.

**Verify**: `blocked-stale-source`, exact mismatch, zero implementation
attempts, zero prototype files/bytes, and no unrelated source mutation.

### Step 4: Run three fresh disposable agents

Run the same byte-identical controller prompt against each fresh directory,
sequentially and without session resume. Preserve exact JSONL, stderr, last
message, wall time, and output tree.

**Verify**: three distinct ephemeral sessions; unchanged source fixture; one
report and one isolated prototype per attempt.

### Step 5: Recover and verify runtime evidence

After each fresh agent exits, run its returned prototype outside the agent
sandbox. Capture desktop, tablet, and mobile screenshots at the exact named
dimensions. Check HTTP status, browser console, horizontal overflow, and PNG
dimensions/hashes.

**Verify**: HTTP 200; clean console; zero overflow; 3/3 viewport screenshots;
no runtime evidence fed back into an agent.

### Step 6: Normalize and qualify the positive matrix

Write four Plan 023 manifests in execution order: stale, fresh-1, fresh-2,
fresh-3. Run `benchmarks/handoff_qualification.py` against the canonical
redesign proposal.

**Verify**: every ordered contract, anchor, source hash, blocker, unknown,
freshness field, acceptance check, viewport, and screenshot passes. Repeating
the command emits byte-identical report bytes.

### Step 7: Inject negative cases

From copied normalized inputs, create:

- missing: remove one named contract disposition;
- reordered: swap two ordered source-anchor identities;
- malformed: add an unknown manifest field and use a boolean numeric metric;
- runtime-recovery failure: alter one copied screenshot hash.

Run each separately and preserve exit status plus shortest exact diagnostic.

**Verify**: every mutation fails; no canonical or positive artifact changes.

### Step 8: Evaluate thresholds and distributions

Compute fresh-completed min, median, mean, p90, maximum, and samples for wall
time, input tokens, output tokens, retries, output bytes, output file count,
and contract accuracy. Compare against the pre-registered thresholds.

**Verify**: threshold artifact names the exact positive qualification SHA and
contains no timestamp or absolute path; repeated evaluation is byte-identical.

### Step 9: Run repository and package gates

Run focused tests, full warning-strict pytest with cache disabled, scoped Ruff
and format checks, compileall, wheel/sdist metadata/build, fresh install,
all-module imports, CLI smokes, `pip check`, artifact isolation, process,
stash, Git, and `git diff --check` invariants.

**Verify**: all pass. Review correctness, simplicity, architecture, security,
performance, prompt isolation, and artifact fidelity.

### Step 10: Integrate and prove parity

Record execution results, production LOC delta, deleted/replaced code,
remaining risks, and Plan 025. Commit only passing reviewed scope, merge to
`master`, push, refresh the graph if source changed, and prove
local/origin/server SHA parity. Delete temporary branch/worktree only after
parity.

## Done criteria

- [x] one passing stale stop plus three passing fresh completed attempts;
- [x] exact end-to-end accounting for all named handoff identities;
- [x] missing, reordered, malformed, and runtime mutations rejected;
- [x] browser recovery preserves prompt isolation;
- [x] distributions and threshold verdict are deterministic;
- [x] all pre-registered thresholds pass or a root cause is fixed and the
      entire matrix is rerun under a new artifact directory;
- [x] no production orchestration/provider parser/parallel model is added;
- [x] full repository/package/invariant/review gates pass;
- [x] stashes remain preserved;
- [x] local/origin/server SHA parity proven.

## Execution results

Final successful matrix:
`/Users/omar/Documents/Projects/.uidetox-qualification/024-recovery-3`.
All four attempts received the same 48,349-byte brief with SHA-256
`96cb4c066d67416b276e2250d1d83a1a2355e6fea0a162423239e045d6c7cd9d`
and the same controller prompt with SHA-256
`a013bad95f9e961577768271c88a748112c3eb59af9624e40d56c109ac7bf266`.
The prompt now also lives at
`benchmarks/handoff-qualification-prompt.md` and is protected by an exact-hash
contract test.

The stale attempt stopped with 43 fresh paths, one exact mismatch, zero
implementation attempts, and zero prototype output. Three distinct fresh
ephemeral sessions completed. Each preserved:

- 44/44 checked source paths;
- 94/94 ordered preservation contracts;
- 34/34 ordered named source anchors;
- 24/24 feasibility blockers;
- 3/3 runtime unknowns;
- 3/3 ordered viewports;
- 1.0 contract-preservation accuracy.

Controller capture produced three PNGs per fresh attempt after the disposable
session closed. Every viewport returned HTTP 200 with zero console
errors/warnings, zero failed or 4xx/5xx resources, and zero horizontal
overflow. Event-log review found zero agent screenshot writes, zero
out-of-root file changes, zero forbidden command paths, unchanged fresh source
manifests, four unique thread IDs, and no runtime evidence returned to an
agent.

Completed-cohort distributions:

- wall seconds: samples `[130.34, 161.96, 110.56]`; min `110.56`, median
  `130.34`, mean `134.286666666667`, p90 `155.636`, max `161.96`;
- input tokens: samples `[646520, 668861, 453667]`; min `453667`, median
  `646520`, mean `589682.6666666666`, p90 `664392.8`, max `668861`;
- output tokens: samples `[11422, 12121, 9833]`; min `9833`, median `11422`,
  mean `11125.333333333334`, p90 `11981.2`, max `12121`;
- retry count: samples `[2, 3, 1]`; min `1`, median `2`, mean `2`, p90 `2.8`,
  max `3`;
- output bytes: samples `[24750, 28400, 24370]`; min `24370`, median `24750`,
  mean `25840`, p90 `27670`, max `28400`;
- output file count: samples `[6, 4, 4]`; min `4`, median `4`, mean
  `4.666666666667`, p90 `5.6`, max `6`;
- accuracy: samples `[1.0, 1.0, 1.0]`; every statistic `1.0`.

All pre-registered thresholds passed. Positive qualification repeated
byte-for-byte. Missing contract, reordered anchor, unknown field, boolean
numeric metric, and screenshot-hash mutations all failed with exact
diagnostics while positive artifacts remained unchanged.

Failure recovery was root-cause driven and preserved under separate artifact
roots:

1. the original prompt specified semantics but not the Plan 023 report keys;
2. the first correction omitted canonical viewport order and bounded runtime
   failure behavior;
3. the second correction omitted zero-console/resource acceptance, allowing a
   `/favicon.ico` 404;
4. the final prompt fixed those boundaries and restarted the full matrix
   without changing thresholds.

Core artifact SHA-256 values:

- qualification report:
  `024fc104733e146f1dac398005a47983abe36998755b694a7156a986266f1b4e`;
- threshold verdict:
  `a9be61ea1f7da9b0c6a83d420c02a9e10e15130f4d8c1a50f3659d9a1bdc4983`;
- negative summary:
  `88bed4337b0cc4a20d595fde154872ff044c1cf449cbea3b50ab5ac3517eb1ac`;
- isolation verification:
  `71ae55264f3d69128c352e3f75b4bef800e4920f3de866d77e213d7cefee24ca`;
- 373-file, 5,866,503-byte evidence manifest:
  `f9a95c128f76c3d191bc88f1ffb2c57508eb5058e18dc6986c9eaf9f692538ee`.

The evidence manifest excludes nested fixture Git metadata, itself, and the
reconstructible fresh-install virtual environment. It includes package build
logs and both distribution artifacts.

Repository gates passed: 18 focused warning-strict tests, 1,425 full
warning-strict tests with cache disabled, scoped Ruff/format, compileall, wheel
and sdist build, fresh install, metadata, 82 module imports, CLI map/redesign/
prototype smokes, and `pip check`. The wheel SHA-256 is
`797452c05d111fc15e5f9c562a5638c4df95a1b033fa645030338e90196f2783`.
The shared code graph was refreshed to 6,007 nodes and 24,459 edges.

Production LOC delta is zero. Removed production code: none. Added production
models, caches, graphs, evidence types, compatibility wrappers, provider
parsers, and renderer-specific models: none. The only executable-repository
change is a benchmark contract test; the formerly unversioned successful
controller prompt is consolidated into one canonical benchmark artifact.

Remaining risks:

- one fresh agent required the allowed maximum of three recovery attempts;
- browser recovery remains machine/toolchain dependent;
- only public static fixture states were exercised, not authenticated,
  triggered, empty, loading, or failure runtime states;
- the exact report/runtime contract is benchmark-owned rather than emitted by
  `uidetox prototype`.

Plan 025 should make the existing prototype brief emit one provider-agnostic,
versioned attempt-report/runtime-acceptance appendix, delete the now-redundant
benchmark prompt duplication, and qualify authenticated/triggered/empty/error
states without adding a launcher, provider parser, cache, graph, evidence type,
or renderer model.

## STOP conditions

Stop and investigate before further changes if:

- canonical Plan 022/023 artifact hashes do not match;
- fixture source hashes disagree before injection;
- any agent reads outside its isolated directory or receives controller
  recovery evidence;
- a fresh run mutates tracked source;
- a stale run creates prototype output;
- normalized identity order cannot be derived from canonical artifacts;
- a negative case passes;
- a threshold fails;
- archival stash identity changes;
- release, tag, or PyPI action becomes necessary.
