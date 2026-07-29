# Plan 047: Persisted-artifact loader consolidation

Status: DONE

## Objective

Measure whether the graph-identical public
`uidetox.frontend_map.load_frontend_map` and
`uidetox.redesign.load_redesign_set` loaders can share one implementation
while preserving their complete public and corruption behavior. Integrate only
if the result reduces total production LOC, branch sites,
cyclomatic/cognitive complexity, and repeated concepts without a new public
interface or compatibility layer. Existing public loaders may remain as
domain adapters; function count is secondary to total code and control-flow
reduction.

## Live baseline

Measured on 2026-07-28 before any production edit:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `073958fe89a3880ad6353f2475ba3dddd23467ce`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- `.beads` is absent and Plan 047 did not exist;
- canonical graph alias
  `Users-omar-Documents-Projects-UIdetox-uidetox` contains 6,023 nodes and
  25,804 edges, with its artifact bound to Plan 046 source commit
  `088b26576d1741deb45682e681146c2e75aabde0`;
- production contains 40,032 lines, 978 functions, 132 classes/models, and
  4,547 measured branch sites across 83 Python files;
- no release, tag, or PyPI action is in scope.

## Graph and history

The canonical graph reports structural similarity 1.000 and the same
fingerprint for both loaders. Both were introduced together by
`83eaab90cb19d67b9f47a2814d68a7c27e622ad5` and every current loader line
still blames to that commit; neither implementation has changed since.

| Loader | Lines | Functions | Branch sites | Cyclomatic | Cognitive |
| --- | ---: | ---: | ---: | ---: | ---: |
| `load_frontend_map` | 17 | 1 | 4 | 4 | 6 |
| `load_redesign_set` | 17 | 1 | 4 | 4 | 6 |
| Aggregate | 34 | 2 | 8 | 8 | 12 |

Both have CRITICAL inbound blast radius:

- `load_frontend_map` has 15 direct graph callers across finding freshness,
  runtime/contract verification, workflow inputs/adapters, scan/rescan,
  review, intent, redesign, visual semantics, and persisted-map tests;
- `load_redesign_set` serves workflow prototype execution, `compare`,
  `prototype`, and persisted-redesign tests.

Both are public interfaces. Their signatures, annotations, docstrings, module
locations, and domain-specific results must remain exact.

## Frozen behavior

The external probe covers both loaders with explicit `Path`, absolute string,
relative `Path`, relative string, `~/artifact.json`, literal `"~"`, and
`None` inputs.

- Explicit paths call `Path(path).expanduser().resolve()` and never call
  `get_uidetox_dir()`.
- `None` calls `get_uidetox_dir()` exactly once and appends the loader's exact
  artifact constant.
- `FRONTEND_MAP_FILE` remains `frontend-map.json`.
- `REDESIGN_SET_FILE` remains `redesigns.json`.
- Literal `"~"` expands to the home directory and therefore follows the
  directory/unreadable path.

Exact public interfaces:

```python
def load_frontend_map(path: str | Path | None = None) -> FrontendMap:
    """Load a persisted frontend map, validating its schema."""

def load_redesign_set(path: str | Path | None = None) -> RedesignSet:
    """Load a persisted redesign set, validating its schema."""
```

Exact loader-owned errors:

- missing frontend map:
  `FileNotFoundError("Frontend map not found: <resolved path>")`, explicitly
  caused by the original `FileNotFoundError`;
- unreadable frontend map:
  `ValueError("Frontend map is unreadable: <resolved path>")`, explicitly
  caused by the original `OSError`, `UnicodeDecodeError`, or
  `json.JSONDecodeError`;
- non-object frontend root:
  `ValueError("Frontend map must contain a JSON object: <resolved path>")`
  with no explicit cause;
- missing redesign artifact:
  `FileNotFoundError("Redesign artifact not found: <resolved path>")`,
  explicitly caused by the original `FileNotFoundError`;
- unreadable redesign artifact:
  `ValueError("Redesign artifact is unreadable: <resolved path>")`,
  explicitly caused by the original `OSError`, `UnicodeDecodeError`, or
  `json.JSONDecodeError`;
- non-object redesign root:
  `ValueError("Redesign artifact must contain a JSON object: <resolved path>")`
  with no explicit cause.

Validation order is path resolution, UTF-8 read, JSON parse, object-root gate,
then domain model construction. Probe results freeze:

- missing file -> loader-specific `FileNotFoundError` with
  `FileNotFoundError` cause;
- directory -> loader-specific unreadable `ValueError` with
  `IsADirectoryError` cause;
- permission denial -> loader-specific unreadable `ValueError` with
  `PermissionError` cause;
- invalid UTF-8 -> loader-specific unreadable `ValueError` with
  `UnicodeDecodeError` cause;
- malformed JSON and UTF-8 BOM -> loader-specific unreadable `ValueError` with
  `json.JSONDecodeError` cause;
- `null`, booleans, number, string, and list roots -> loader-specific
  object-root `ValueError` with no cause;
- object roots reach the domain constructor: `{}` propagates
  `Unsupported frontend map schema 0; expected 1.` or
  `Unsupported redesign schema 0; expected 2.` unchanged.

`FrontendMap.from_dict` and `RedesignSet.from_dict` each receive the parsed
dictionary exactly once. Their returned object identity is returned unchanged;
their exceptions propagate as the same object. Normal loads create fresh
model objects with stable serialization and existing defaults. Every probed
file retains identical bytes, size, and mode.

External evidence:

- root:
  `/Users/omar/Documents/Projects/.uidetox-qualification/047-artifact-loaders.xK0xis`;
- full normalized baseline: `baseline.json`;
- reusable probe: `probe_loaders.py`;
- semantic SHA-256:
  `a990535d136af9153a091d1317c008202d873cd8d4b95c0e958e40c398603a88`.

## Existing-owner search

Graph-first source search found no existing dependency-light owner with these
semantics.

- `uidetox.state.load_config` and `load_state` have domain-specific defaults,
  normalization, and silent recovery behavior; reuse would change errors and
  validation order.
- workflow/onboarding/history loaders likewise own different fallback or
  corruption contracts.
- `frontend_map._atomic_write_json` and state persistence helpers are writers,
  not readers.
- `uidetox.utils` contains no persisted JSON-object loader.
- Making either public loader own the other is invalid because each constructs
  a different model and owns different error text.

## Lower-bound consolidation

The smallest behavior-preserving proposal uses one new private
`_load_json_object(input_path, artifact)` helper in the already imported
`uidetox.state` module and retains both public loaders as path/model wrappers.
Existing imports remain single lines, so they add no LOC or dependency edge.
The proposal was measured in an isolated graph project. It was initially
rejected, then applied after reassessment showed that the function-count gate
misclassified required public adapters as new wrapper debt.

| Metric | Current target | Lower bound | Delta |
| --- | ---: | ---: | ---: |
| Lines | 34 | 28 | -6 |
| Functions | 2 | 3 | **+1** |
| Branch sites | 8 | 5 | -3 |
| Cyclomatic | 8 | 4 | -4 |
| Cognitive | 12 | 6 | -6 |

Hypothetical production totals would be 40,026 lines, **979 functions**, and
4,544 branch sites. The new helper has 10 lines, cyclomatic 4, cognitive 6,
and two parameters. Each retained public loader becomes a 9-line wrapper with
zero graph complexity.

Concept accounting treats default-path selection, explicit-path
normalization, UTF-8/JSON loading, missing-error translation,
unreadable-error translation, object-root validation, message-label
selection, and model construction as distinct reader obligations:

- current implementations contain 14 concept occurrences across two direct
  public owners;
- the lower bound contains 12 occurrences, but adds one private interface and
  exposes its two-parameter/message contract to both public wrappers;
- no capability disappears and callers gain no new behavior.

The initial evaluation treated the added private function and retained public
loaders as disqualifying. Reassessment instead applies the deletion test:
removing the private seam recreates identical path-reading, JSON parsing,
error translation, and object-root validation in two CRITICAL public loaders.
The helper therefore earns its interface.

## Initial decision

REJECTED before production edits.

The hard STOP condition is function count growth: 978 would become 979.
Wrapper accumulation and the new shallow private interface independently
support rejection. Complexity reduction cannot override an explicit function
count and wrapper gate. Tests need no changes because production remains
byte-identical.

Focused warning-strict validation in the repository `.venv` passes:

```text
4 passed in 0.16s
```

The first attempt used the system interpreter and stopped before collection
with the existing environment error
`ERROR: AST support is unavailable for css.` Re-running with
`.venv/bin/python` used the repository's complete dev environment and passed.

Full pytest, build/install, package, canonical qualification, historical
Plan 025 replay, and canonical graph refresh are intentionally not run:
their conditional gate applies only when implementation is viable, and no
production/package/graph input changed.

## Reassessment and implementation

Explicit follow-up direction prioritized root-cause cleanup, replace over
accumulate, and net code/control-flow reduction over isolated function count.
That changes the decision:

- `load_frontend_map` and `load_redesign_set` are existing stable public
  interfaces, not newly accumulated compatibility wrappers;
- their path selection and domain-model construction remain locally owned;
- one private `uidetox.state._load_json_object` now owns UTF-8 reading, JSON
  parsing, missing/unreadable error translation, and object-root validation;
- dependency direction remains `frontend_map/redesign -> state`;
- the private seam has exactly two direct CRITICAL adapters and no cycle;
- deleting the seam recreates the duplicated implementation.

Integrated source results:

- physical production delta: `-4` lines (`16` insertions, `20` deletions);
- target function lines: `34 -> 28`;
- target branch sites: `8 -> 5`;
- target cyclomatic complexity: `8 -> 4`;
- target cognitive complexity: `12 -> 6`;
- production totals: `40,027 -> 40,023` lines and `977 -> 978` functions;
- public function count and every public interface remain unchanged;
- differential semantic SHA-256 remains
  `a990535d136af9153a091d1317c008202d873cd8d4b95c0e958e40c398603a88`;
- focused warning-strict pytest: `4 passed`;
- full warning-strict, cache-disabled pytest: `1,466 passed`;
- scoped Ruff format/import checks, repository-wide Ruff `F`, `compileall`,
  and `git diff --check` pass;
- wheel/sdist build, fresh install, all 82 package imports, `pip check`, and
  `uidetox --version` pass;
- temporary full graph
  `UIdetox-Plan047-reassessment` contains 6,044 nodes and 26,361 edges;
  `_load_json_object` measures 10 lines / cyclomatic 4 / cognitive 6 and has
  exactly two direct callers.
- source commit:
  `bd04ee3eb7e8b53bca7c6098123e4c2f24218851`;
- final integrated source commit:
  `ef8a94cc23b8f0038c4039e07885b4338844b1a4`;
- canonical graph project `UIdetox-final-051` contains 6,059 nodes and 26,447
  edges, bound to the final integrated source commit;
- canonical graph commit:
  `fe48f59dc536d513442fe1ac06408ca11adf2862`.

Live revalidation on 2026-07-29 confirms:

- complete dirty diff review found no behavior, architecture, quality, test,
  or integration issue;
- the external differential ran twice at the exact semantic SHA-256
  `a990535d136af9153a091d1317c008202d873cd8d4b95c0e958e40c398603a88`;
- source, fresh-wheel, and fresh-sdist executions retain that exact semantic
  SHA-256;
- three sandbox mutations covering non-object acceptance, leaked
  `UnicodeDecodeError`, and changed unreadable-error text all changed the
  semantic hash, proving the differential is red-capable;
- the Plan 049 persistence-lock root fix and generated-stack QA fixes leave the
  loader implementation and exact differential unchanged; the combined
  repository now passes `1,466` warning-strict tests;
- focused warning-strict pytest passed `4 passed`;
- full warning-strict, cache-disabled pytest passed `1,466 passed`;
- the canonical graph proves the helper's two direct CRITICAL adapters and no
  new cycle;
- source and graph integration are complete. Five-axis review found no
  blocking or required findings.

## Plan 048 recommendation

Measure the exact-fingerprint private collection normalizers
`uidetox.memory._normalize_progress_log` and
`uidetox.state._normalize_tool_collection`:

| Helper | Lines | Cyclomatic | Cognitive | Direct callers |
| --- | ---: | ---: | ---: | ---: |
| `_normalize_progress_log` | 10 | 3 | 4 | 1 |
| `_normalize_tool_collection` | 9 | 3 | 4 | 1 |
| Aggregate | 19 | 6 | 8 | 2 |

Both already depend on entry-specific normalizers and both owner modules
already import `uidetox.utils`. Plan 048 should measure whether one private
callback-driven collection normalizer in that existing dependency-light owner
can delete both helpers, update their two private callers directly, reduce
function count from two to one, and avoid public wrappers or import cycles.
Freeze malformed/non-list inputs, order, dropped entries, input mutation,
normalizer call order/count, exception propagation, returned list identity,
and state/memory serialization before editing.

## STOP conditions

No production integration if:

- any accepted path, resolution, exception type/message/cause, validation
  order, model construction, serialization, default, lifecycle, CLI/workflow
  behavior, public interface, package content, or corruption behavior changes;
- tests require changes;
- a schema, model, enum, cache, facade, adapter, fallback, dependency, public
  interface, or compatibility layer is required;
- production LOC, branch sites, cyclomatic complexity, or cognitive complexity
  fail to fall;
- public function count grows or a compatibility wrapper accumulates;
- the one private function increase is not offset by strict code and
  control-flow reduction across both existing public adapters;
- imports cycle;
- archived stashes or qualification artifacts require mutation;
- any gate remains unexplained.
