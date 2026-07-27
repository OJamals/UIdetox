# Plan 032: Pyproject dependency normalization

## Status

DONE

## Magic moment

Backend and database detection accept the same PEP 621, dependency-group, and
Poetry dependency metadata while `_read_pyproject_dependency_names` reads as
one flat normalization pipeline instead of a tree of repeated shape guards.

## Live baseline

Measured on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `e21014bdbe6dccc88891f486ba8157cc3deaefb1`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 031 is DONE; Plan 032 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,725 edges;
- `_read_pyproject_dependency_names` has CRITICAL blast radius through
  `_detect_python_backend_config` and `_detect_python_databases`;
- graph metrics are 63 lines, complexity 28, cognitive complexity 91,
  8 loops, loop depth 2, and zero loop-local linear scans;
- production contains 40,123 lines, 982 functions, and 132 classes/models;
- focused warning-strict baseline passes 879 tests with cache disabled.

`uidetox/tooling.py` has one pre-existing import-order `I001` caused by
`from dataclasses import dataclass, field, asdict`. It predates this plan and
is outside the parser body. Do not combine an import sweep with the measured
refactor; prove the import block remains byte-identical.

## Measured metadata distribution

The repository has one tracked `pyproject.toml`:

- 5 `[project].dependencies` specifications;
- 4 `[project.optional-dependencies]` groups with sizes 4, 1, 2, and 2;
- 14 total visited PEP-style specifications;
- 10 normalized unique dependency names;
- no `[dependency-groups]` or `[tool.poetry]` metadata.

Synthetic large-shape baseline:

- 200 direct specifications;
- 20 optional groups and 20 dependency groups, each with 200 specifications;
- 8,200 visited specifications per call;
- seven samples of 100 calls: 1762.523, 1766.310, 1763.091, 1786.369,
  1763.861, 1823.666, and 1777.736 ms;
- median: 1766.310 ms per 100 calls.

Runtime is a guard, not the primary goal. Keep only if exact behavior remains
and cognitive/LOC metrics improve; reject any material timing regression.

## Frozen behavior matrix

Ten canonical filesystem cases produce SHA-256
`670f9622c79c81047eda6ee10c6f23eebb1e52d4acb70e559807d5600711f77f`:

| Case | Exact normalized result |
|------|-------------------------|
| absent | `[]` |
| empty | `[]` |
| malformed | `[]` |
| PEP 621 core | `["fastapi", "sql-alchemy"]` |
| PEP 621 optional | `["pytest", "ruff"]` |
| dependency groups | `["my-pkg", "ruff"]` |
| Poetry core | `["django", "sql-alchemy"]` |
| Poetry groups | `["pytest"]` |
| mixed/deduplicated | `["django", "fastapi", "pytest", "ruff", "sqlalchemy"]` |
| wrong top-level types | `[]` |

Compatibility includes:

- missing, unreadable, invalid UTF-8, and malformed TOML return an empty set;
- non-dict top-level metadata sections are ignored;
- direct `[project].dependencies` retains its legacy truthy-iterable behavior:
  a string is visited character-by-character and a truthy non-iterable raises
  `TypeError`;
- optional and dependency-group values remain list-gated, with only string
  entries parsed;
- non-list optional/dependency groups are ignored;
- dependency-group inline tables remain ignored;
- only dict Poetry dependency tables contribute their keys;
- non-dict Poetry groups and dependency tables are ignored;
- `_extract_requirement_name` retains marker/comment/option filtering;
- `_normalize_dep_name` retains lowercase and underscore-to-hyphen behavior;
- duplicate names collapse into one set entry;
- Poetry's `python` key remains excluded;
- result type, caller-visible detection ordering, config-file attribution, and
  every `ToolInfo` serialized field remain exact.

## History and ownership

- `e582819` introduced the parser, all supported metadata shapes, defensive
  type gates, normalization, and fail-closed behavior together.
- `1571409` only formatted the file; no later commit changed parser semantics.
- `9f8e6df` added database-detection coverage, while backend detection retains
  a direct PEP 621 regression test.
- `_read_pyproject_dependency_names` is already the deep module: callers know
  only `Path -> set[str]`. No new public/private helper seam is justified.
- `_extract_requirement_name` and `_normalize_dep_name` remain the canonical
  normalization authorities.
- Generated cross-product probing exposed the undocumented direct-dependency
  iterable contract. Preserve it here; any future cleanup requires a red test
  and separate behavior-change plan.

## Architecture decision

- Keep filesystem/TOML parsing and fail-closed behavior unchanged.
- Normalize missing or wrong-shaped project/tool/Poetry sections locally.
- Collect existing PEP-style specification containers, then process them in
  one flat loop.
- Collect existing Poetry dependency tables, then process them in one flat
  loop.
- Remove the nested `add_spec` function; call existing normalization authority.
- Add no function, type, model, enum, cache, adapter, graph, wrapper, facade,
  schema, field, dependency, compatibility fallback, or public interface.
- Keep tests unchanged because this is a pure refactor.
- Do not broaden supported metadata. PEP 735 include-group expansion would be
  a behavior change requiring its own red test and plan.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, worktree, branches, stashes, processes, graph, and remote.
- [x] Trace CRITICAL callers and downstream detect paths.
- [x] Inspect parser, existing normalization functions, tests, history, blame,
      and repository metadata distribution.
- [x] Freeze ten canonical behavior cases and large-shape timing baseline.
- [x] Pass 879 focused warning-strict tests before edits.

### Task 2: Flatten normalization

- [x] Replace nested table-specific guard trees with two flat container passes.
- [x] Preserve every behavior-matrix result and generated shape projection.
- [x] Reduce production LOC, complexity, and cognitive complexity.
- [x] Remove one nested function; add no symbol.
- [x] Keep tests and import block unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff `E4/E7/E9/F`, format, repository-wide unused-symbol,
      `compileall`, and `git diff --check`.
- [x] Prove pre-existing `I001` is unchanged and no new lint finding exists.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Complete correctness/readability/architecture/security/performance review.

### Task 4: Integrate

- [x] Commit source only after all gates pass.
- [x] Refresh and commit codebase-memory graph after source commit.
- [x] Record exact metrics, hashes, remaining risk, and Plan 033 recommendation.
- [x] Commit Plan 032/index, push `master`, prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `7669af6da0c2dbe51c722d80a0b9f4fce6c47b18`.
- Graph refresh commit:
  `58923028a4bdad030a03ebd1ceeb0b0b09d64f4a`.
- Production delta: 42 insertions, 49 deletions, net `-7` lines;
  40,123 to 40,116 lines. Functions fall 982 to 981 by deleting the nested
  `add_spec`; classes/models remain 132. Tests and import block are unchanged.
- `_read_pyproject_dependency_names` graph metrics: complexity 28 to 16,
  cognitive complexity 91 to 27, loops 8 to 5, and lines 63 to 56. Loop depth
  remains 2; loop-local linear scans remain zero.
- Generated cross-product equivalence passed 123 metadata shapes, including
  exact result values and exception type/messages, at SHA-256
  `388d55244ca01f003acee37476710c0b1d8f67c4f7a70d7c61744208e1883438`.
- The ten canonical filesystem cases remain byte-identical at SHA-256
  `670f9622c79c81047eda6ee10c6f23eebb1e52d4acb70e559807d5600711f77f`.
- Controlled interleaved large-shape timing measured 1795.279 ms baseline and
  1779.092 ms candidate median per 100 calls; candidate/baseline median ratio
  is 0.991 and paired-ratio median is 0.9884.
- Warning-strict focused pytest: 879 passed before and after. Warning-strict
  full pytest: 1,451 passed with cache disabled.
- Scoped Ruff, repository-wide unused-symbol checks, Ruff format,
  `compileall`, and `git diff --check` passed. The pre-existing `I001` import
  block remains byte-identical at SHA-256
  `4333449c7e57980b44d01d3cfcca2659687b82f14f7f7eb863305e5ef2dea059`.
- Build, fresh install, all 82 package submodule imports, metadata
  (`1.9.0`, Python `>=3.11`, 14 dependency declarations), CLI smokes, and
  `pip check` passed.
- Canonical prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Wheel SHA-256:
  `7c138408436a9a5f7736002fb7e14e4c950cf80109cbdeebe3b113ff51711143`.
- Sdist SHA-256:
  `cb4e72960a39271cffe66c78b7de65a6b51fea85a6b5626fdc08a6b841c2eb61`.
- Historical Plan 025 still fails exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/032.IrhXuY`.
- Refreshed graph: 6,027 nodes / 25,737 edges, bound to the source commit.
- Multi-axis review verdict: no findings; APPROVE. No public interface, schema,
  field, model, enum, cache, graph model, wrapper, facade, fallback, dependency,
  test, release, tag, or PyPI change occurred.
- Remaining risk: direct `[project].dependencies` intentionally retains its
  undocumented truthy-iterable behavior. Normalizing that malformed shape would
  be observable and requires a separate red-test behavior-change plan.
- Plan 033 recommendation: measure `uidetox.commands.autofix.run` before
  changes. It is a bounded remaining command hotspot at 223 lines, complexity
  34, cognitive complexity 95, eight loops, and loop depth 2. Separate true
  repeated issue/category/file traversal from intentional transformation
  ordering; preserve dry-run text, issue order, changed-file detection, state
  writes, subprocess boundaries, and every exit code. Stop if improvement only
  moves lines into helpers or changes user-visible output.

## STOP conditions

Stop without source integration if:

- any frozen behavior result changes;
- flattening adds a helper/seam or broadens supported metadata;
- fail-closed or type-filtering behavior weakens;
- backend/database detection, config-file attribution, or serialized output
  changes;
- production LOC, complexity, or cognitive complexity does not improve;
- median large-shape runtime regresses materially beyond baseline variation;
- tests or import blocks must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
