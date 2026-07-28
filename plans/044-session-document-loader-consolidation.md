# Plan 044: Session-document loader consolidation

## Status

DONE

## Magic moment

Sub-agent session metadata and pending-review documents preserve exact
directory, ordering, JSON, error, prompt, and CLI behavior while one private
loader replaces two identical 15-line filesystem pipelines.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `8440629e260d191931a1434234959c4d002fca09`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 043 is DONE; Plan 044 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,815 edges and is bound to Plan 043 source commit
  `1ef46d9d65ee10b50df84fa5e32ba00b191847d4`;
- `list_sessions` has CRITICAL blast radius through `uidetox subagent list`;
- `get_pending_reviews` has CRITICAL blast radius through `_verify_prompt`,
  prompt isolation, stage-prompt generation, and subagent orchestration;
- each target has 15 lines, cyclomatic complexity 5, cognitive complexity 12,
  one loop at depth 1, and one allocation inside the loop;
- aggregate target implementation is 30 lines, complexity 10, cognitive
  complexity 24, two loops, and two allocation sites;
- `subagent.py` contains 871 lines;
- production contains 40,057 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- Plan 043's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

Live ignored `.uidetox/sessions` state contains:

| Measure | Count |
| --- | ---: |
| Directory entries | 7 |
| Session directories | 7 |
| Non-directory entries | 0 |
| `meta.json` files | 7 |
| Loaded metadata documents | 7 |
| `review_request.json` files | 0 |
| Loaded pending-review documents | 0 |

A deterministic 512-tree external matrix contains 2,021 directories and 808
non-directory entries. Each session filename independently covers:

- missing files;
- valid JSON dictionaries, lists, strings, numbers, and nulls;
- malformed JSON;
- invalid UTF-8 that must continue propagating `UnicodeDecodeError`;
- directories occupying a document path and producing caught `OSError`;
- arbitrary directory names and lexical ordering.

Baseline public functions and the candidate loader return or raise identically
for every metadata and review case with zero mismatches and semantic SHA-256
`4a83ab3f57bba3e477bfe3757e2e864de9c643665de1f0a57c37d2c64bf889d4`.

| Work | Current | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Source loader implementations | 2 | 1 | 50% |
| Public filesystem traversals per paired calls | 2 | 2 | 0% |
| Public entry points | 2 | 2 | 0% |
| Aggregate implementation lines | 30 | 19 | 36.7% |

Candidate/baseline median timing ratios are 0.9859 for seven metadata files,
1.0011 for 100 metadata files, 0.9884 for seven review files, and 1.0030 for
100 review files. All variation is within 0.3–1.4% noise; no route materially
regresses.

## Frozen behavior and boundaries

Preserve exactly:

- `_sessions_dir()` executes once per public call, retains directory-creation
  side effects, and remains the only session-root owner;
- `sorted(sessions_dir.iterdir())` lexical traversal and arbitrary child names;
- `session_dir.is_dir()` executes before document-path construction;
- `meta.json` and `review_request.json` remain separate public owners;
- existence checks precede reads;
- `Path.read_text()` retains default encoding and error policy;
- `json.loads()` accepts every JSON value without dict/schema validation;
- `json.JSONDecodeError` and `OSError` from read/load remain silently skipped;
- `UnicodeDecodeError`, directory iteration errors, sorting errors, and other
  unexpected exceptions continue propagating;
- output is a new list, values retain JSON-decoded identity/type, and ordering
  follows session-directory order;
- missing files, non-directory children, malformed files, document-path
  directories, symlinks, races, and empty directories retain behavior;
- `list_sessions()` and `get_pending_reviews()` names, zero-argument
  signatures, annotations, docstrings, imports, and callers remain unchanged;
- CLI session order/format, pending-review prompt order/fields, untrusted-data
  isolation, session/review writers, state, workflow, scan, review, prototype,
  runtime, qualification, and serialization remain unchanged.

## History and architecture

- `a3a2d0e` introduced `list_sessions` in the initial release.
- `74081be` later introduced `get_pending_reviews` by copying the same
  directory/JSON pipeline for `review_request.json`.
- `_sessions_dir` owns root creation.
- `create_session` and `_flag_for_review` own the two document writers.
- `_handle_list` owns metadata presentation.
- `_verify_prompt` owns pending-review projection and untrusted-data isolation.
- The distinct public functions and filenames are intentional; the duplicated
  traversal/read/error implementation is not.

## Architecture decision

- Add one private `_load_session_documents(filename)` implementation directly
  beside the public readers.
- Preserve the exact loop, gate, read, parse, exception, append, and return
  order.
- Replace each 15-line public body with one call while preserving its public
  signature and docstring.
- The new private function must earn its existence: total production LOC,
  aggregate cognitive complexity, loops, and allocation sites must fall after
  accounting for the helper.
- Add no cache, model, type, enum, index, graph, wrapper layer, facade,
  adapter, fallback, schema, field, dependency, or public interface.
- Keep tests unchanged because behavior does not change.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect exact target/caller/writer flow.
- [x] Inspect tests, Git history, blame, and architectural owners.
- [x] Measure live and representative distributions.
- [x] Separate intentional public/file ownership from duplicated loading.
- [x] Record exact differential and controlled timing baselines.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate document loaders

- [x] Add one private loader that replaces both duplicated bodies.
- [x] Preserve root/traversal/order/read/JSON/error boundaries.
- [x] Reduce production LOC and aggregate cognitive/loop/allocation complexity.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact baseline-versus-working-tree behavioral equivalence.
- [x] Re-run controlled timing; reject material regression.
- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff/format, repository-wide unused-symbol checks,
      `compileall`, and `git diff --check`.
- [x] Prove tests and unrelated production files remain unchanged.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Complete correctness/readability/architecture/security/performance
      review.

### Task 4: Integrate

- [x] Commit source only after all gates pass.
- [x] Refresh and commit codebase-memory graph after source commit.
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 045
      recommendation.
- [x] Commit Plan 044/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `07763e2b088da4f65761f28c843146687eba074b`.
- Graph refresh commit:
  `325e9e2cdf1ff7c88d5ea1962da95a80edd7c492`.
- Production delta: +17/-26, net -9 lines; `subagent.py` 871→862 lines;
  repository production 40,057→40,048 lines.
- Production symbols are 980 functions (+1 private consolidating helper) and
  132 classes/models (unchanged). No public function, type, model, enum,
  cache, graph, wrapper, fallback, schema, field, or dependency was added.
- Aggregate target implementation is 30→19 lines, cyclomatic complexity
  10→5, cognitive complexity 24→10, loops 2→1, allocation sites inside loops
  2→1, and duplicated loader implementations 2→1. Runtime traversals remain
  two for paired public calls.
- All 512 synthetic trees remain exactly equivalent with zero mismatches and
  semantic SHA-256
  `4a83ab3f57bba3e477bfe3757e2e864de9c643665de1f0a57c37d2c64bf889d4`.
- Source median timing ratios range 0.9932–1.0054; fresh-wheel ratios range
  0.9948–1.0062. No route materially regresses.
- Focused warning-strict pytest: 6 passed before and after. Full
  warning-strict pytest: 1,451 passed in 27.74 seconds with cache disabled.
- Target format, repository-wide Ruff `F`, `compileall`, `git diff --check`,
  test-diff, package metadata/import/CLI/pip checks pass. Whole-file Ruff
  reproduces the same three findings on `HEAD` in untouched lines.
- Wheel SHA-256:
  `e3ed7b9f07da750edeac75c697563073ca499c06f00401a77ee2447894a5d8dc`.
- Sdist SHA-256:
  `7c741b18ab57982c7d5a9f61f32346eb2a2f6936025053578cff60ef35ac4ac1`.
- Canonical source/fresh-wheel prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Two canonical qualification replays remain byte-identical at SHA-256
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Canonical graph: 6,026 nodes / 25,813 edges, bound to the source commit.
- Multi-axis review: no findings / APPROVE.
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/044.mDzFW0`.

## Remaining risk and Plan 045 recommendation

The private loader accepts a filename, but graph evidence proves its only two
callers pass fixed internal names; no user-controlled path reaches it. File
races remain governed by the same `exists()` then `read_text()` behavior and
the same caught/propagated exception boundary.

Plan 045 should measure consolidation of `_normalize_pattern_entries` and
`_normalize_note_entries` in `memory.py`. They duplicate list/dict/string
filtering, field whitelisting, append, and ordering logic. Prefer one private
required-key/optional-fields normalizer called directly by `load_memory`, so
the two specialized helpers are deleted rather than wrapped. Keep
`_normalize_fix_history` separate unless exhaustive legacy/corruption evidence
proves its multi-required-field semantics are truly identical. Preserve exact
field insertion order, accepted/rejected JSON types, unknown-field removal,
timestamps, persistence, CLI output, and memory injection behavior.

## STOP conditions

Stop without source integration if:

- root creation, traversal count/order, directory/file gates, filename
  ownership, decoding, JSON acceptance, exception propagation, output
  order/type, public signature, CLI, or prompt isolation changes;
- runtime filesystem traversal increases or a cache/stateful index appears;
- the helper adds a compatibility/fallback layer or merely relocates duplicate
  branches;
- total production LOC, aggregate cognitive complexity, loops, or allocation
  sites do not fall after accounting for the added private function;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
