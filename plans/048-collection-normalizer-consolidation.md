# Plan 048: Private collection-normalizer consolidation

Status: DONE

## Objective

Replace two exact-fingerprint private collection-normalization loops with one
callback-driven private utility:

- `uidetox.memory._normalize_progress_log`
- `uidetox.state._normalize_tool_collection`

The consolidation is allowed only if it:

- preserves every accepted and rejected input;
- preserves callback order, count, identity, and exception propagation;
- preserves state and memory serialization;
- deletes both duplicated helpers instead of wrapping them;
- keeps the two entry-specific normalizers as schema owners;
- creates no import cycle or public interface;
- reduces production function count, control flow, loops, and source size; and
- passes focused, full, package, artifact, and graph qualification.

No schema, cache, compatibility wrapper, or lifecycle change is in scope.

## Live baseline

Baseline captured 2026-07-28:

- repository: `/Users/omar/Documents/Projects/UIdetox`
- branch: `master`
- `HEAD`: `6d98260d80182c55825067648aba39885b582f93`
- local `master`: exact `HEAD`
- `origin/master`: exact `HEAD`
- server `refs/heads/master`: exact `HEAD`
- worktree: clean
- worktrees: one, on `master`
- tags at `HEAD`: none
- running UIdetox/pytest processes: none
- Beads: absent
- archived stashes preserved:
  - `stash@{0}` =
    `200608c499cd4e2ca509d0a32be1b3f376dbdef2`
  - `stash@{1}` =
    `047d61901a7a85fdee06fb9eb984f6b8a85efbad`

Pinned interpreter:

```text
/Users/omar/Documents/Projects/UIdetox/.venv/bin/python
```

Full warning-strict, cache-disabled baseline:

```text
1451 passed in 28.79s
```

Command:

```bash
.venv/bin/python -m pytest -p no:cacheprovider
```

The system interpreter is not a valid qualification environment; Plan 047
proved that it lacks the CSS AST development dependency. All Plan 048 Python
gates use the project virtualenv.

## Measured duplication

Canonical graph project:

```text
Users-omar-Documents-Projects-UIdetox-uidetox
```

Persisted artifact:

- source commit:
  `088b26576d1741deb45682e681146c2e75aabde0`
- nodes: `6023`
- edges: `25804`

Commits after the artifact source are documentation-only, so the graph is
source-current at the Plan 048 baseline.

Both target functions have the exact structural fingerprint:

```text
02732deb0830ab6d00cd9578021df86b01b03b9f03e85fd803ebed5001c40baa...
```

Baseline target metrics:

| Metric | Progress helper | Tool helper | Total |
|---|---:|---:|---:|
| Functions | 1 | 1 | 2 |
| Source lines | 10 | 9 | 19 |
| Cyclomatic complexity | 3 | 3 | 6 |
| Cognitive complexity | 4 | 4 | 8 |
| Loops | 1 | 1 | 2 |
| Allocations in loops | 1 | 1 | 2 |
| Direct callers | 1 | 1 | 2 |

Repository production-function baseline under `uidetox/`:

```text
functions=792
cyclomatic=3029
cognitive=5356
loops=523
alloc_in_loop=272
```

The loops differ only in parameter and callback names. Each:

1. accepts only an exact `list` instance or subclass;
2. allocates a fresh result list;
3. calls one entry normalizer once per input entry in order;
4. drops only callback results equal to `None` by identity check;
5. appends every other callback result unchanged; and
6. returns the fresh result list.

## History and ownership

Both duplicated helpers and their private callers were introduced together by:

```text
e5828194460d3f3f241df2bbc15046d6183d8989
2026-05-02T10:19:54-04:00
fix: harden cli workflows and sync docs
```

Ownership remains split correctly:

- `_normalize_progress_entry` owns progress-log schema and metadata
  preservation.
- `_normalize_tool_entry` owns tooling schema and optional command fields.
- proposed shared helper owns only collection iteration/filtering policy.
- `load_memory` remains the memory artifact owner.
- `_normalize_tooling_config` and `load_config` remain config artifact owners.

Both `memory.py` and `state.py` already depend on `uidetox.utils`. `utils.py`
does not depend on either module. Moving the algorithm down to `utils.py`
creates no import cycle.

## Blast radius

Graph-first inbound traces classify both existing helper edits as CRITICAL:

- `_normalize_progress_log`
  - direct caller: `load_memory`
  - transitive consumers: memory commands, scan/rescan, subagent memory,
    batch resolution, and persistence tests
- `_normalize_tool_collection`
  - direct caller: `_normalize_tooling_config`
  - transitive owner: `load_config`
  - transitive consumers: setup, map, scan, review, status, workflow,
    mechanical checks, capture, suppress, zone, intent, and tests

Call-site edits are also CRITICAL:

- `load_memory` has 24 graph callers.
- `_normalize_tooling_config` feeds `load_config`, which serves most CLI
  commands and workflow construction.

Therefore focused tests alone cannot authorize integration.

## Frozen behavior

External qualification root:

```text
/Users/omar/Documents/Projects/.uidetox-qualification/048-collection-normalizer.BJB5w2
```

Baseline probe:

```text
probe_normalizers.py
baseline.json
semantic_sha256=66cb0455014ead1c5721988904aa587df629f6960ddf995c3443f2fb11abaf71
```

The probe freezes:

- accepted container: `list` and list subclasses only;
- rejected containers:
  - `None`
  - tuple
  - dict
  - string
  - bytes
  - integer
  - boolean
  - generator
- rejected containers return fresh empty lists;
- empty input returns a fresh empty list;
- input order and duplicate entries remain unchanged;
- callback invocation occurs once per entry, in order;
- callback results equal to `None` are dropped;
- all non-`None` callback results are appended unchanged;
- callback-returned input-object identity is preserved;
- input containers and entries are not mutated by the collection layer;
- the result list never aliases the input list;
- callback exceptions propagate with the same exception instance;
- processing stops at the raising entry;
- memory progress-log normalization preserves accepted extra metadata;
- tooling normalization preserves list order and duplicates;
- tooling normalization drops invalid entries and unsupported fields;
- malformed collection values normalize to empty lists;
- serialized state/memory projections remain byte-equivalent after canonical
  JSON serialization.

Baseline probe facts:

```text
non-list callback calls=0
ordered callback calls=["alpha", "drop", "beta", "alpha"]
exception callback calls=["before", "raise"]
exception same instance=true
all inputs unchanged=true
fresh invalid result=true
fresh empty result=true
```

## Existing-owner search

Graph search covered normalization, collection, entry, callback, list, and
shared-utility concepts.

Findings:

- no existing callback-driven collection normalizer exists;
- `_normalize_issue_collection` owns `Finding` coercion and has different
  accepted types and exception behavior;
- `_normalize_subjective_state` embeds history-specific policy;
- `_normalize_text_entries` and `_normalize_fix_history` own different schemas;
- utility collection functions track Git status rather than persisted data.

Therefore extending an existing owner would conflate contracts. One new private
utility is the narrowest owner.

## Candidate and lower bound

Isolated candidate project:

```text
UIdetox-Plan048-lower-bound
```

Candidate:

```python
def _normalize_dict_entries(
    entries: object, normalize_entry: Callable[[object], dict | None]
) -> list[dict]:
    if not isinstance(entries, list):
        return []
    normalized: list[dict] = []
    for entry in entries:
        clean_entry = normalize_entry(entry)
        if clean_entry is not None:
            normalized.append(clean_entry)
    return normalized
```

Candidate graph metrics:

```text
functions=1
lines=11
cyclomatic=3
cognitive=4
loops=1
alloc_in_loop=1
fingerprint=exact baseline fingerprint
```

Target-algorithm delta:

```text
functions: 2 -> 1
lines: 19 -> 11
cyclomatic: 6 -> 3
cognitive: 8 -> 4
loops: 2 -> 1
alloc_in_loop: 2 -> 1
```

The candidate earns its interface:

- two real callers use it immediately;
- deleting it recreates the exact duplicate loops;
- neither old helper survives as a wrapper;
- callback injection preserves each module's schema owner;
- no generic registry, class, protocol, cache, or compatibility layer appears.

## Implementation

1. Add private `_normalize_dict_entries` to `uidetox.utils`.
2. Import it in `uidetox.memory` and `uidetox.state`.
3. Replace `load_memory`'s `_normalize_progress_log` call with direct shared
   utility use plus `_normalize_progress_entry`.
4. Replace `_normalize_tooling_config`'s `_normalize_tool_collection` call with
   direct shared utility use plus `_normalize_tool_entry`.
5. Delete `_normalize_progress_log`.
6. Delete `_normalize_tool_collection`.
7. Keep production tests unchanged; this is a behavior-preserving
   consolidation against existing contracts plus external differential proof.

## Tasks

### Task 1: Freeze and measure

- [x] Rebaseline Git, remote, worktree, environment, stashes, tags, and process
  state.
- [x] Run full warning-strict baseline.
- [x] Resolve both candidates graph-first.
- [x] Trace inbound blast radius with risk labels.
- [x] Inspect exact graph snippets and current source.
- [x] Prove exact fingerprints.
- [x] Inspect history and ownership.
- [x] Search for an existing owner.
- [x] Capture exhaustive external baseline probe.
- [x] Measure isolated lower-bound candidate.

### Task 2: Consolidate

- [x] Add one private shared utility.
- [x] Delete both duplicated helpers.
- [x] Update both private callers directly.
- [x] Keep tests byte-identical.
- [x] Prove production source size and function count decrease.

### Task 3: Verify behavior and package

- [x] Run candidate differential probe.
- [x] Require exact semantic hash parity.
- [x] Run focused warning-strict memory/config regression tests.
- [x] Run scoped Ruff format and lint gates.
- [x] Run repository Ruff and compile gates.
- [x] Run full warning-strict, cache-disabled pytest.
- [x] Build wheel and sdist.
- [x] Inspect package metadata and contents.
- [x] Install wheel into a fresh isolated environment.
- [x] Run import, `pip check`, and representative CLI smokes.
- [x] Prove tests and unrelated production modules remain byte-identical.

### Task 4: Integrate

- [x] Perform five-axis review: behavior, architecture, quality, tests,
  integration.
- [x] Commit only the measured source consolidation.
- [x] Refresh the canonical graph from the source commit.
- [x] Verify removed functions are absent and shared helper has two callers.
- [x] Commit graph artifact separately.
- [x] Mark this plan DONE with measured results.
- [x] Commit plan completion separately.
- [x] Push `master`.
- [x] Prove local/origin/server parity and clean final state.
- [x] Do not create a release, tag, or PyPI publication.

## Evidence gates

Integration requires all:

1. baseline semantic SHA-256 equals candidate semantic SHA-256;
2. focused memory/config normalization tests pass warning-strict;
3. full suite passes warning-strict with cache disabled;
4. Ruff and compile gates pass;
5. wheel/sdist build and isolated install pass;
6. representative CLI imports and smokes pass;
7. production function count decreases by one;
8. removed helpers have zero graph definitions;
9. shared helper has exactly two production callers;
10. no import cycle, public interface, wrapper, schema, cache, or lifecycle
    change exists;
11. final Git refs and server branch are identical; and
12. final worktree is clean with archived stashes unchanged.

## Execution results

- Source commit:
  `11ed4b654024c054a486a3d7b30ed228200a3e9a`.
- Canonical graph refresh commit:
  `b23c09957933a6c677fc471f6c5c7327947b8faf`.
- `_normalize_progress_log` and `_normalize_tool_collection` were deleted.
  Their existing callers now pass `_normalize_progress_entry` and
  `_normalize_tool_entry` directly to `uidetox.utils._normalize_dict_entries`.
- Production changed from 40,032 to 40,027 lines and 978 to 977 functions.
  Classes remain 132 across 83 Python files.
- The source diff is 22 insertions and 27 deletions: net `-5` lines.
- Target algorithms changed from two functions, 19 lines, cyclomatic 6,
  cognitive 8, two loops, and two loop allocations to one function, 11 lines,
  cyclomatic 3, cognitive 4, one loop, and one loop allocation.
- External baseline and candidate JSON are byte-identical. Semantic SHA-256:
  `66cb0455014ead1c5721988904aa587df629f6960ddf995c3443f2fb11abaf71`.
- Frozen behavior remains exact for non-list inputs, fresh results, order,
  duplicates, dropped `None`, callback count/order, input mutation, returned
  identity, exception identity/short-circuiting, and state/memory
  serialization.
- Focused warning-strict pytest:
  `16 passed in 0.18s`.
- Full warning-strict, cache-disabled pytest:
  `1451 passed in 25.45s`.
- Tests and unrelated production modules remain byte-identical.
- Scoped Ruff format/import checks, repository-wide Ruff `F`, `compileall`,
  and `git diff --check` pass.
- Broad scoped Ruff reports one known pre-existing `UP017` on unchanged
  `now_iso`; the same finding reproduces from the `HEAD` version of
  `uidetox/utils.py`. It was not changed.
- AST audit reports zero unused private production definitions and zero unused
  private module values.
- Wheel:
  `uidetox-1.9.0-py3-none-any.whl`,
  SHA-256
  `e37bd209cf3d13b0a1f5c43f20597238ab51b2bb8d2dbc5c0d09595cb7736edd`.
- Sdist:
  `uidetox-1.9.0.tar.gz`,
  SHA-256
  `0bd8d28f1da1edfd937dc12f3d5cd93b1f32133450d9ac7b263d106b998730d4`.
- Fresh installation reports UIdetox 1.9.0, Python `>=3.11`, 14 dependency
  records, imports all 82 package submodules, proves removed helpers absent,
  exercises the shared helper, passes detect/status/version CLI smokes, and
  passes `pip check`.
- Source and fresh-installed canonical prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Two canonical qualification reports are byte-identical at SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 remains intentionally non-executable with exit 1 and
  exact error:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Canonical graph now contains 6,022 nodes and 25,816 edges, bound to the
  source commit. Removed helpers are absent. `_normalize_dict_entries` retains
  the exact duplicate fingerprint, measures 11 lines / cyclomatic 3 /
  cognitive 4 / one loop / one loop allocation, and has exactly two direct
  CRITICAL callers: `load_memory` and `_normalize_tooling_config`.
- Five-axis verdict: no findings / APPROVE.
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/048-collection-normalizer.BJB5w2`.
- Archived stashes remain unchanged. No release, tag, or PyPI action occurred.

## Plan 049 recommendation

The refreshed graph has only three remaining exact-fingerprint production
pairs:

1. `load_frontend_map` / `load_redesign_set`, already measured and rejected by
   Plan 047 because public wrappers must survive and function count grows;
2. `add_pattern` / `add_note`, public memory mutators whose field schemas and
   signatures differ; and
3. `get_patterns` / `get_fix_history`, public memory query wrappers whose
   limits and ranked text fields differ.

Plan 049 should measure the two same-module memory pairs together, beginning
with inbound traces, exact snippets, history, public-signature freeze, and a
lower-bound function-count proof. Expected STOP condition: retaining all four
public wrappers while adding a private helper cannot reduce function count.
Proceed only if a wrapper-free design preserves every public signature and
produces strict net-negative source, functions, and control flow.

Do not revisit the Plan 047 loaders, add a compatibility layer, change memory
schema, or centralize only naming rather than policy.

## STOP conditions

Stop and mark Plan 048 REJECTED if any occurs:

- candidate semantic hash differs from baseline;
- a callback is called in a different order or count;
- exception identity or propagation changes;
- accepted/rejected input types change;
- input or output identity changes;
- state or memory serialization changes;
- either old helper must survive as a wrapper;
- the shared helper gains fewer than two real callers;
- production function count or source size does not decrease;
- an import cycle or public compatibility surface appears;
- focused/full/package/CLI/graph gates fail after root-cause correction; or
- unrelated user-owned worktree changes appear.
