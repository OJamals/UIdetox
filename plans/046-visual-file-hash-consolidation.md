# Plan 046: Visual file-hash consolidation

Status: DONE

## Objective

Replace the duplicated private `_sha256_file` implementations in
`uidetox/visual_evidence.py` and `uidetox/visual_worker_protocol.py` with the
existing `visual_evidence` implementation as the single direct owner. Preserve
the complete visual-evidence and isolated-worker trust boundary while reducing
production LOC, functions, complexity, streaming loops, and digest allocation
sites.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `3fc2cc0e64b7049d596a8d759add1d16425203e9`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 045 is DONE; Plan 046 did not exist;
- `.beads` is absent, so no Beads issue can be claimed in this checkout;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,024 nodes and 25,804 edges and is bound to Plan 045 source commit
  `6d678695f4a8befe16b09e09a0e722c99d1c97c6`;
- production contains 40,040 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict baseline is 51 passed in 1.27 seconds with the pytest
  cache disabled.

## Measured duplication

The fresh graph reports exact similarity 1.000 and the same structural
fingerprint for both helpers:

| Helper | Lines | Cyclomatic | Cognitive | Loops | Loop allocations |
| --- | ---: | ---: | ---: | ---: | ---: |
| `visual_evidence._sha256_file` | 6 | 2 | 3 | 1 | 0 |
| `visual_worker_protocol._sha256_file` | 6 | 2 | 3 | 1 | 0 |
| Aggregate | 12 | 4 | 6 | 2 | 0 |

The source duplicates two digest constructions, two binary file opens, two
1-MiB sentinel-read loops, two per-chunk digest updates, two hexadecimal result
conversions, and two digest allocation sites. The only textual difference is
the local file-handle name.

Measured direct-import result:

- 6 target lines, cyclomatic 2, cognitive 3, one loop, zero loop allocations;
- one digest allocation site;
- production function count 979 to 978;
- production LOC decreases by eight;
- no wrapper, new module, facade, compatibility layer, dependency, schema, or
  public interface.

## History and ownership

- `visual_evidence._sha256_file` was introduced by
  `69c27719a2c4f0cf2f85346effc7a920e97fce49` with the deterministic visual
  evidence core.
- `visual_worker_protocol._sha256_file` was copied by
  `28424a9c030d6cd12c6dcd94e29c36efcfadf022` while hardening isolated visual
  evidence.
- The implementations have not semantically changed since introduction.
- Import direction is already `visual_worker_protocol -> visual_evidence`;
  retaining the core helper in `visual_evidence` and importing it into the
  protocol adds no cycle or heavy dependency. Reversing ownership would create
  a cycle.
- `uidetox.utils.canonical_sha256` hashes canonical JSON payloads, not file
  bytes, and is outside this consolidation.

## Blast radius

Both helpers have CRITICAL inbound blast radius:

- `visual_evidence._sha256_file` directly serves `_load_png`,
  `_saved_artifact`, and `inspect_visual_evidence`, then manifest freshness,
  reviewer artifacts, CLI capture/review/status/finish, workflow projection,
  and tamper tests;
- `visual_worker_protocol._sha256_file` directly serves
  `_validate_artifact` and `validate_worker_manifest`, then isolated-worker
  execution and forged/tampered/oversized artifact rejection.

The protocol validates allowed roots, output-directory containment, positive
dimensions, hash syntax, file existence, and maximum bytes before hashing.
This ordering must not change.

## Frozen behavior

The external baseline covers 14 deterministic paths:

- regular files of 0, 1, 8,191, 8,192, 8,193, 1,048,575, 1,048,576,
  1,048,577, and 2,097,169 bytes;
- Unicode filename and symlink;
- missing path, directory path, and permission-denied file.

Both helpers produce identical values or exact exception type, arguments, and
`errno`; leave file content, size, and mode unchanged; open only with `"rb"`;
request exactly 1,048,576 bytes per read; perform a final sentinel read; and
close the file on exit. Empty, exact-chunk, chunk-plus-one, and multichunk
recordings are identical.

Baseline differential result:

- 14 value/error/mutation cases plus four read-protocol recordings;
- zero helper mismatches and zero recording mismatches;
- semantic SHA-256
  `abc1db13f487edda31186c48813fd9141a3a876261500eaa2a8ffcac67ae20e3`.

The refactor must preserve:

- byte-for-byte SHA-256 digests and lowercase 64-character hexadecimal output;
- binary mode, 1-MiB chunking, sentinel termination, close behavior, and
  streaming memory bounds;
- `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, all other
  `Path.open`/read failures, their arguments, and propagation;
- input paths, symlink behavior, file content/metadata, and caller ordering;
- all size checks before hashing and every forged/tampered rejection;
- Pillow-free protocol import behavior, worker process isolation, JSON
  serialization, package contents, CLI behavior, and public signatures.

## Implementation

`uidetox.visual_evidence._sha256_file` remains the one private implementation.
`uidetox.visual_worker_protocol` imports that exact private function in its
existing one-way import block and deletes its duplicate implementation and
unused `hashlib` import. Call sites retain the same local name and ordering.

Tests remain unchanged because this is a pure internal refactor. Exhaustive
equivalence is proved by the external differential probe.

## Tasks

### Task 1: Measure and freeze

- [x] Rebaseline refs, worktrees, branches, dirty state, stashes, processes,
      graph, and remote parity.
- [x] Trace both CRITICAL caller trees and inspect trust-boundary ordering.
- [x] Inspect history, blame, module imports, tests, and existing hash owners.
- [x] Record exact structural metrics and deterministic differential baseline.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate file hashing

- [x] Import the existing private helper into `visual_worker_protocol`.
- [x] Delete the duplicate protocol helper and its unused `hashlib` import.
- [x] Preserve every frozen behavior and keep call sites/tests unchanged.
- [x] Prove negative production LOC/function deltas and lower aggregate
      complexity, loops, and digest allocation sites.

### Task 3: Verify repository/package/artifact boundaries

- [x] Re-run the external differential probe with identical semantic SHA-256.
- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff/format, repository-wide Ruff `F`, `compileall`, and
      `git diff --check`.
- [x] Prove tests and unrelated production files remain unchanged.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Run AST/graph orphan checks and multi-axis review.

### Task 4: Integrate

- [x] Commit source only after every gate passes.
- [x] Refresh and commit the canonical graph after the source commit.
- [x] Record exact metrics, hashes, removed symbol, remaining risk, and Plan 047
      recommendation.
- [x] Commit Plan 046/index, push `master`, and prove local/origin/server
      parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `088b26576d1741deb45682e681146c2e75aabde0`.
- Canonical graph refresh commit:
  `a10edf610750c4c30cc3452ee52170c0d87fec44`.
- Removed definition:
  `uidetox.visual_worker_protocol._sha256_file`. Protocol call sites now
  resolve directly to `uidetox.visual_evidence._sha256_file`; runtime and
  installed-package identity checks confirm both module bindings are the same
  function object.
- Production moved from 40,040 to 40,032 lines and 979 to 978 functions;
  classes/models remain 132 across 83 Python files.
- Target implementation moved from 12 to 6 lines, cyclomatic 4 to 2, cognitive
  6 to 3, two source loops to one, and two digest allocation sites to one.
- All 14 differential value/error/mutation cases and four read-protocol
  recordings remain identical. There are zero mismatches; semantic SHA-256
  remains
  `abc1db13f487edda31186c48813fd9141a3a876261500eaa2a8ffcac67ae20e3`.
- Exact 1-MiB read requests, final sentinel reads, binary mode, close behavior,
  symlink/Unicode handling, mutation behavior, and propagated exception
  type/arguments/`errno` remain unchanged.
- Focused warning-strict pytest: 51 passed in 1.17 seconds. Final isolated full
  warning-strict pytest: 1,451 passed in 27.86 seconds. Cache was disabled.
- Tests and unrelated production files remain byte-identical.
  Repository-wide Ruff `F`, scoped Ruff `I`/format, `compileall`, and
  `git diff --check` pass. A broader scoped Ruff invocation exposed six known
  pre-existing untouched findings; none entered scope.
- Final wheel SHA-256:
  `6bdc9615d33822f74b43ec6aa830dc0871b4f385bf5d196b9bc45475b4de6192`.
- Final sdist SHA-256:
  `c28b033be29e1547be9c22dc4ed75b3f90fc17e9e189528771da2cbbb60e716c`.
- Fresh installation imports all 82 modules as `uidetox` 1.9.0 on Python
  `>=3.11`, exposes 14 dependency records, passes root/scan/map/prototype CLI
  smokes, and passes `pip check`.
- Canonical source and installed prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Both canonical qualification SHA-256 values:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 prototype remains intentionally non-executable with
  exit 1 and exact error:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Canonical graph now contains 6,023 nodes and 25,804 edges and is bound to
  the source commit. It reports exactly one `_sha256_file`, six lines,
  cyclomatic 2, cognitive 3, one loop, zero loop allocations, and all six
  direct CRITICAL callers. AST and graph audits report zero unused private
  production definitions and zero unused private module values.
- Multi-axis verdict: no remaining findings / APPROVE.
- Archived Plan 015/016 stashes and prior qualification artifacts remain
  unchanged. No release, tag, or PyPI action occurred.

## Plan 047 recommendation

Measure the graph-identical public `load_frontend_map` and
`load_redesign_set` persisted-artifact loaders before considering
consolidation. Each is 17 lines, cyclomatic 4, cognitive 6, loop-free, and
similarity 1.000; aggregate is 34 lines, cyclomatic 8, cognitive 12.
`load_frontend_map` has a broad CRITICAL freshness/workflow/scan/review blast
radius, while `load_redesign_set` feeds CRITICAL compare/prototype/workflow
paths. Plan 047 must preserve both public signatures, default-path resolution,
UTF-8 and JSON errors, exact domain-specific error type/message/cause, object
root gate, model construction, and package/qualification behavior. First prove
that an existing owner or one private dependency-light loader reduces total
LOC and complexity without circular imports or pass-through wrapper
accumulation. Reject the work if retaining the required public entry points
merely moves the duplicated branches, grows code, generalizes prematurely, or
changes any error boundary.

## Evidence

External evidence root:
`/Users/omar/Documents/Projects/.uidetox-qualification/046-file-hash.kOxiti`.

Archived qualification roots and Plan 015/016 stashes remain read-only.

## STOP conditions

Stop without source integration if:

- any digest, read size, open mode, close behavior, exception, path, symlink,
  mutation, size-check order, tamper rejection, or worker-isolation behavior
  changes;
- import direction becomes circular or adds a heavy worker dependency;
- a wrapper, new module, facade, compatibility layer, fallback, schema, model,
  enum, cache, dependency, or public interface is required;
- production LOC or function count grows, or aggregate complexity, loops, or
  digest allocation sites fail to fall;
- complexity merely moves into another layer;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
