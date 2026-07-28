# Plan 045: Session-memory entry normalizer consolidation

## Status

DONE

## Magic moment

Persisted patterns and notes retain exact JSON acceptance, filtering, ordering,
field order, mutation, query, CLI, prompt-injection, and workflow behavior while
one private structured-text normalizer replaces two specialized copies.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `7af836563a845f0b206f64d331cf740b9129b768`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 044 is DONE; Plan 045 did not exist;
- `.beads` is absent, so no Beads issue can be claimed in this checkout;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,812 edges and is bound to cleanup source commit
  `af17769fdf00682a21ce4ad40b4e97647eda3a5a`;
- `load_memory` has CRITICAL blast radius: 33 direct inbound callers, with
  CLI, scan/rescan, batch resolution, subagent prompt, persistence, and
  corruption-resilience paths downstream;
- `_normalize_pattern_entries` has 18 lines, cyclomatic complexity 6,
  cognitive complexity 10, one loop, and one allocation inside the loop;
- `_normalize_note_entries` has 16 lines, cyclomatic complexity 5,
  cognitive complexity 8, one loop, and one allocation inside the loop;
- aggregate target implementation has 34 lines, cyclomatic complexity 11,
  cognitive complexity 18, two loops, and two allocation sites;
- production contains 40,047 lines, 980 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict baseline passes 9 tests with cache disabled;
- tracked `uidetox/memory.py` and tests are unchanged.

## Measured duplication

The two target functions contain:

| Branch/site | Pattern | Note | Aggregate |
| --- | ---: | ---: | ---: |
| Non-list root gates | 1 | 1 | 2 |
| Non-dict entry gates | 1 | 1 | 2 |
| Required-string gates | 1 | 1 | 2 |
| Optional-string gates | 2 | 1 | 3 |
| Whitelist dictionary allocations | 1 | 1 | 2 |
| Append sites | 1 | 1 | 2 |
| Input-order traversal loops | 1 | 1 | 2 |
| Required-first insertion sites | 1 | 1 | 2 |
| Optional ordered insertion sites | 2 | 1 | 3 |

Aggregate AST conditionals are 9. The only semantic variation is:

- pattern: required `pattern`; optional `category`, then `learned_at`;
- note: required `note`; optional `created_at`.

## Live and representative distributions

Live ignored `.uidetox/memory.json` has SHA-256
`84365325aca9b20cf4b7868dcd9eaa2063dac3784077d8eb30996a4857cac58e`.

| Field | Root | Entries | Valid dictionaries | Required values | Optional values | Unknown fields | Duplicates |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| `patterns` | list | 0 | 0 | none | none | 0 | 0 |
| `notes` | list | 30 | 30 | 30 non-empty strings | 30 non-empty `created_at` strings | 0 | 0 |

Every live note key order is exactly `note`, `created_at`.

The external deterministic matrix covers:

- null, boolean, number, string, and dictionary non-list roots;
- null, boolean, number, string, list, and dictionary non-dict entries;
- missing, null, boolean, number, list, dictionary, empty-string,
  non-empty-string, and Unicode-string required and optional fields;
- unknown fields before, between, and after known fields;
- duplicate entries and arbitrary input order;
- new-result-dictionary identity and input non-mutation;
- exact required-first and optional-field insertion order.

Across 828 cases (738 pattern, 90 note), the measured candidate has zero output,
mutation, identity, or field-order mismatches. Required empty strings remain
accepted. Optional empty strings remain retained. Non-string optional values
and unknown fields remain removed. Entry order and duplicates remain unchanged.
Baseline semantic SHA-256 is
`6f6a9b9cb1f8923f0bac8849bd1141133c57a4fd4a88780f25db26ddca92f372`.

## Frozen behavior and boundaries

Preserve exactly:

- `load_memory()` zero-argument name, signature, annotation, docstring, and
  public callers;
- `_memory_path()` ownership and missing-file defaults;
- UTF-8 `json.load()` behavior;
- fallback to `_default_memory()` for `JSONDecodeError`, `OSError`, and
  `UnicodeDecodeError`;
- non-dictionary top-level fallback and existing nested default/type repair;
- non-list pattern/note roots normalize to new empty lists;
- non-dictionary entries are filtered;
- a pattern is retained only when `pattern` is a string;
- a note is retained only when `note` is a string;
- required empty strings are valid because they are strings;
- `category`, `learned_at`, and `created_at` are retained only when strings,
  including empty strings;
- output field insertion order is exactly `pattern`, `category`, `learned_at`
  and `note`, `created_at`;
- unknown fields are removed;
- each retained result is a new whitelisted dictionary;
- source lists and dictionaries are not mutated;
- input entry order and duplicate entries are preserved;
- missing optional fields are not defaulted or fabricated;
- `save_memory()` atomic write, `json.dump(..., indent=2)`, UTF-8, flush,
  `fsync`, and replace behavior;
- `add_pattern`/`add_note` field order, timestamps, caps, and persistence;
- `get_patterns`/`get_notes` ranking, limits, and returned ordering;
- memory CLI rendering and field lookups;
- subagent query filtering, projection order, and untrusted-data isolation;
- scan/rescan/batch-resolution memory mutations;
- workflow state remains a separate schema-versioned artifact;
- every public signature, serialized field, exception, error, side effect,
  default, and lifecycle boundary.

## History and architecture

- `e5828194460d3f3f241df2bbc15046d6183d8989` introduced both specialized
  normalizers together while hardening persistent JSON corruption handling.
  Current blame proves every target line still belongs to that commit.
- Later optional-capability and mapping changes left both normalizers
  semantically unchanged.
- `2b66379c7df3b2f066e398e3eca195bf6b055dc9` later replaced Chroma memory
  with deterministic local JSON matching and separately introduced
  `_normalize_fix_history`.
- `_normalize_fix_history` has three required fields, nested required-field
  validation, two optional fields, two loops, and distinct query/persistence
  contracts. It remains out of scope.
- `8781c8a6bb0c9558a4966797fd5e4774031cfb8b` later removed redundant
  timestamp wrappers without changing the three entry normalizers.
- `memory_cmd.run` renders only normalized required/category values.
- `subagent._build_memory_block` projects normalized patterns/notes into
  isolated untrusted JSON.
- scan, rescan, and batch-resolution mutate other memory fields through the
  same `load_memory`/`save_memory` lifecycle.
- `WorkflowEngine` persists a separate sorted, schema-versioned workflow
  document; this refactor must not touch it.

## Architecture decision

- Add one private `_normalize_text_entries(entries, required_field,
  optional_field, trailing_optional_field=None)` implementation.
- Call it directly from `load_memory` for patterns and notes.
- Delete `_normalize_pattern_entries` and `_normalize_note_entries`; add no
  wrappers around them.
- Preserve exact list/dictionary/string gates, one new-dictionary allocation,
  explicit optional-field order, append order, and return behavior.
- Use the two explicit optional-field positions only to whitelist string values.
  Do not add a
  schema, model, enum, registry, adapter, facade, cache, fallback, dependency,
  or public interface.
- Keep `_normalize_fix_history` separate.
- Keep tests unchanged because behavior does not change.

The accepted candidate has 27 lines, cyclomatic complexity 6, cognitive
complexity 10, one loop, and one dictionary allocation inside the loop. A
lower-complexity tuple/comprehension candidate was rejected during review
because it allocated a temporary optional-field dictionary for every accepted
entry.

| Measure | Current | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Private normalizer functions | 2 | 1 | 50% |
| Implementation lines | 34 | 27 | 20.6% |
| Cyclomatic complexity | 11 | 6 | 45.5% |
| Cognitive complexity | 18 | 10 | 44.4% |
| Loops | 2 | 1 | 50% |
| Allocation sites in loops | 2 | 1 | 50% |

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect target/caller/writer flow.
- [x] Inspect tests, history, blame, CLI, prompt, scan, and workflow owners.
- [x] Measure live JSON and exhaustive representative distributions.
- [x] Record exact differential baseline and candidate complexity.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate structured-text entry normalization

- [x] Add one private required-key/optional-fields normalizer.
- [x] Call it directly from `load_memory`.
- [x] Delete both specialized target helpers without wrappers.
- [x] Preserve every frozen behavior and keep `_normalize_fix_history`
      separate.
- [x] Reduce production LOC, function count, aggregate complexity, loops, and
      allocation sites.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass the 828-case differential probe with identical semantic SHA-256.
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

- [x] Commit source only after all gates pass.
- [x] Refresh and commit the canonical graph after the source commit.
- [x] Record exact metrics, hashes, removed symbols, remaining risk, and
      Plan 046 recommendation.
- [x] Commit Plan 045/index, push `master`, and prove local/origin/server
      parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `6d678695f4a8befe16b09e09a0e722c99d1c97c6`.
- Canonical graph refresh commit:
  `8053828b3d573ba34da9ce0589f9306b37207390`.
- Removed symbols: `_normalize_pattern_entries`,
  `_normalize_note_entries`.
- Added private replacement: `_normalize_text_entries`, called directly only
  by `load_memory`; `_normalize_fix_history` remains unchanged.
- Production moved from 40,047 to 40,042 lines, 980 to 979 functions, and
  remained at 132 classes/models across 83 Python files.
- Target implementation moved from 34 to 27 lines, cyclomatic 11 to 6,
  cognitive 18 to 10, two source loops to one, and two dictionary-allocation
  sites in loops to one.
- All 828 differential cases remain identical: zero output, mutation,
  identity, or field-order failures; semantic SHA-256 remains
  `6f6a9b9cb1f8923f0bac8849bd1141133c57a4fd4a88780f25db26ddca92f372`.
- Live distribution remains zero patterns and 30 valid notes with exact
  `note`, `created_at` field order. The required live-root full-suite run
  exercised two pre-existing batch-resolution tests that persist
  self-healing diagnostics to ignored `.uidetox/memory.json`; its resulting
  SHA-256 is
  `fb7f2eabfdf547a6cce75945cef28af894e03da31a966eaa55904440510ecbf3`.
  The final full-suite gate therefore ran from the exact source copy under the
  evidence root to prevent further live-state writes. Differential evidence
  proves the consolidated normalizer itself does not mutate inputs.
- Focused warning-strict pytest: 5 passed in 0.13 seconds. Final isolated full
  warning-strict pytest: 1,451 passed in 28.25 seconds. Cache was disabled.
- Tests remain byte-identical. Repository-wide Ruff `F`, scoped Ruff format,
  `compileall`, and `git diff --check` pass.
- Final wheel SHA-256:
  `a03ed96830cdd92ab257c52ce87daf40ba7d9ebba80364ccff714a6ad434de76`.
- Final sdist SHA-256:
  `41d8f1af4f39ab60058f54f9ca410b7637bc22a7b562f8618d7a972b54aa08c8`.
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
- Canonical graph now contains 6,024 nodes and 25,804 edges and is bound to
  the source commit. Removed helpers are absent; the replacement measures
  27 lines, cyclomatic 6, cognitive 10, one loop, and one allocation in the
  loop. AST and graph audits both report zero unused private production
  definitions and zero unused private module values.
- Multi-axis verdict: no remaining findings / APPROVE.
- Archived Plan 015/016 stashes and prior qualification artifacts remain
  unchanged. No release, tag, or PyPI action occurred.

## Plan 046 recommendation

Measure the two byte-identical private `_sha256_file` implementations in
`visual_evidence.py` and `visual_worker_protocol.py`. The fresh graph reports
six lines, cyclomatic 2, cognitive 3, one streaming loop, no loop allocation,
and similarity 1.000 for each. Both feed CRITICAL visual-evidence/tamper
validation paths, so Plan 046 must first prove that one dependency-light shared
owner preserves chunked reads, digest bytes, file/error behavior, worker
isolation, import direction, package contents, and every forged/tampered
artifact rejection. Reject consolidation if it creates a circular or heavy
worker dependency, changes the security boundary, adds compatibility wrappers,
or fails negative production LOC/function deltas.

## Evidence

External evidence root:
`/Users/omar/Documents/Projects/.uidetox-qualification/045.3bGGwe`.

Archived qualification root
`/Users/omar/Documents/Projects/.uidetox-qualification/review-cleanup.hAc6oK`
remains read-only and hash-identical.

## STOP conditions

Stop without source integration if:

- accepted JSON values, filtering, field order, entry order, duplicates,
  mutation behavior, corruption fallback, serialization, public signatures,
  CLI, prompt isolation, workflow state, or persistence changes;
- required empty strings stop being accepted or any non-string optional value
  is retained;
- source dictionaries are reused or unknown fields survive;
- wrappers accumulate around the old specialized helpers;
- `_normalize_fix_history` enters scope without exhaustive proof;
- production LOC or function count grows, or aggregate cognitive complexity,
  loops, or allocation sites fail to fall;
- complexity merely moves into another layer;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
