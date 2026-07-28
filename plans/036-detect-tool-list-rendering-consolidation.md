# Plan 036: Detect tool-list rendering consolidation

## Status

DONE

## Magic moment

`uidetox detect` preserves exact detection, persistence, optional frontend
compatibility, tool ordering, labels, spacing, AST capability output, and
failure boundaries while deleting redundant truthiness branches around typed
tool lists.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `a3cae7d808cffb3b21c24c257cb96d6ec8ffd9a1`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 035 is DONE; Plan 036 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,784 edges and is bound to Plan 035 source commit
  `14fb3ecbaf23fc6828c8e09d981058f2db29a17b`;
- `uidetox.commands.detect.run` is dynamically dispatched by argparse and
  persists tooling plus AST capability config before rendering. Treat blast
  radius as CRITICAL even though static inbound tracing cannot see dispatch;
- graph metrics are 69 lines, cyclomatic complexity 14, cognitive complexity
  20, 5 loops, loop depth 1, and zero loop-local scans/allocations;
- production contains 40,087 lines, 981 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict baseline passes all 6 detect/database-tooling tests
  with cache disabled;
- Plan 035's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

The four rendered collections are existing `ProjectProfile` list fields in
fixed frontend, backend, database, and API order. Representative detection
produces:

| Root | Frontend | Backend | Database | API | Rendered tools |
| --- | ---: | ---: | ---: | ---: | ---: |
| repository | 0 | 1 | 1 | 0 | 2 |
| full-stack fixture root | 1 | 1 | 1 | 1 | 4 |
| fixture frontend | 0 | 0 | 0 | 0 | 0 |
| fixture backend | 0 | 1 | 1 | 0 | 2 |

The detected names are:

- repository: `python`, `sqlite`;
- full-stack fixture root: `vite`, `python`, `sqlite`, `openapi`;
- fixture backend: `python`, `sqlite`.

Detection itself took 905.141 ms for the repository, 51.367 ms for the
full-stack root, 4.058 ms for the frontend, and 13.185 ms for the backend in
the baseline sample.

Current rendering performs:

- four list truthiness branches;
- four label-specific loops, entering only for non-empty groups;
- four attribute reads plus one repeated read for every non-empty group;
- exactly one traversal and one print per tool;
- one later, independent AST-capability traversal.

Deleting the guards preserves exactly one traversal and print per tool, keeps
all four label-specific loops, and changes the four typed lists from
branch-before-iteration to direct iteration. It removes four branches and the
repeated reads for non-empty groups without adding a group traversal, tuple,
label format, helper, allocation, or field.

An initially considered generic `(prefix, tools)` outer loop was rejected.
It adds four group iterations, eagerly reads later profile fields before
earlier output, and was slower in every isolated distribution: empty
`13.167 -> 37.113 ms` per 100,000 runs, one tool per group
`26.655 -> 34.855 ms` per 50,000, four tools per group
`29.154 -> 32.724 ms` per 20,000, and 100 tools per group
`29.313 -> 31.023 ms` per 1,000.

The guard-deletion candidate has sub-microsecond mixed isolated results:

- empty: `12.113 -> 20.222 ms` per 100,000 runs;
- repository shape: `16.925 -> 17.700 ms` per 50,000;
- full-stack fixture shape: `26.408 -> 25.161 ms` per 50,000;
- two tools per group: `24.856 -> 24.198 ms` per 30,000;
- 100 tools per group: `28.913 -> 29.520 ms` per 1,000.

These mixed nanosecond-scale changes are negligible beside 4–905 ms detection
and do not justify a runtime-speed claim. The retained value must be negative
production LOC and lower branch/cognitive complexity with no material
whole-command regression.

A six-scenario behavioral probe freezes default/`None`/empty/explicit path
resolution, empty/single/multiple groups, an older profile without `frontend`,
tool and AST output, config payload, call order, and save-before-print behavior
at:

`ff7aa1f9502fb30de7a92ef07df93a2107aa723675bccbc1e44c5687ee97aee7`.

## Frozen behavior and side-effect contract

Preserve exactly:

- `path` precedence and project-root resolution for `None`, empty, and `.`;
- one `detect_all` call before config loading;
- `load_config`, `profile.to_dict`, `ast_capabilities`, config mutation, and
  `save_config` order;
- preservation of unrelated config keys;
- save completion before the first output call;
- heading bytes, blank lines, labels, colon alignment, and final message;
- package manager and `not detected` behavior;
- TypeScript, linter, and formatter output and optional fix-command lines;
- frontend, backend, database, and API group order;
- insertion order, duplicates, `name`, and `config_file` for every tool;
- absence of a heading or placeholder for empty tool groups;
- compatibility with older profile objects that omit only `frontend`;
- AST capability insertion order, available/unavailable status, extension
  order, optional error detail, Unicode em dash, and alignment;
- propagation of detection, serialization, capability, save, valid attribute,
  iteration, formatting, and output failures;
- every public/private signature and CLI argument;
- persisted tooling and AST schemas.

`ProjectProfile.frontend`, `backend`, `database`, and `api` are typed lists.
Invalid `None`, falsey custom iterable, mutation-on-read property, and
side-effectful truthiness behavior are outside this data contract. No
compatibility behavior may be added for those invalid shapes.

## History and architecture

- `a3a2d0e` introduced package manager, compiler, linter, formatter, backend,
  database, and API rendering as separate fixed-label groups.
- `8e18fbf` added frontend rendering with `getattr(..., [])` so older profile
  objects without the then-new field remain executable.
- `e582819` made default detection resolve through the canonical project root.
- `e4384e8` added AST capability persistence and rendering after all tool
  groups.
- `1571409` reformatted the module without semantic change.
- `ProjectProfile` remains the canonical typed tooling container and
  `ProjectProfile.to_dict` remains the persistence authority.
- Separate group labels are presentation constants, not parallel models.
- Tool iteration is intentional rendering work. Only the list truthiness
  checks are redundant for valid typed lists.
- A generic group table would add runtime work and move field-evaluation
  boundaries. It is not a valid consolidation.
- No stale or orphaned detect symbol was found.

## Architecture decision

- Replace only four redundant truthiness guards.
- Iterate each existing typed list directly in the existing group position.
- Retain `getattr(profile, "frontend", [])` as the sole optional compatibility
  seam; do not broaden fallback behavior to other fields.
- Retain four fixed-label loops because a generic outer loop adds work and
  changes evaluation timing.
- Preserve output, group evaluation order, persistence, AST rendering, and
  error order.
- Add no helper, function, type, model, enum, table, cache, graph, wrapper,
  facade, adapter, fallback, schema, field, dependency, or public interface.
- Keep tests unchanged because this is a pure typed-list refactor; use external
  differential evidence for exact orchestration and stdout.
- Keep only if production LOC, cyclomatic complexity, and cognitive complexity
  improve; exact behavior remains identical; and whole-command timing shows no
  material regression.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the dynamic CRITICAL CLI and inspect exact source.
- [x] Inspect `ProjectProfile`, CLI registration, tests, Git history, and
      blame.
- [x] Measure repository/fixture distributions, source work, rejected generic
      consolidation timing, guard-deletion timing, and exact behavior.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Simplify typed list rendering

- [x] Delete four redundant tool-list truthiness guards.
- [x] Preserve optional frontend fallback and four fixed-label loops.
- [x] Reduce production LOC and graph complexity without a new symbol or pass.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
- [x] Re-run controlled timing and prove no material whole-command regression.
- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff, Ruff format, repository-wide unused-symbol checks,
      `compileall`, and `git diff --check`.
- [x] Prove tests and unrelated production files remain unchanged.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Complete correctness/readability/architecture/security/performance review.

### Task 4: Integrate

- [x] Commit source only after all gates pass.
- [x] Refresh and commit codebase-memory graph after source commit.
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 037
      recommendation.
- [x] Commit Plan 036/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `482db87ca53b1a1031ae6042960873f9dd4734aa`.
- Refreshed graph commit:
  `cd359b97c541fc62290c8f17749762199a9ab840`.
- Production delta: 9 insertions, 13 deletions, net `-4` LOC
  (`40,087 -> 40,083`); functions remain 981 and classes/models remain 132.
- `uidetox.commands.detect.run`: 69 -> 65 lines, cyclomatic complexity
  14 -> 10, and cognitive complexity 20 -> 12. Loops remain 5, loop depth
  remains 1, and loop-local scans/allocations remain zero.
- Tool-group truthiness branches fall 4 -> 0. Attribute reads fall from
  `4 + non-empty groups` to 4: repository shape 6 -> 4, full-stack fixture
  8 -> 4, empty shape 4 -> 4. Tool element traversals and print calls are
  unchanged.
- Removed code is four redundant list guards, their nested indentation, and
  the second attribute read they required for every non-empty group. No
  helper, function, type, model, table, cache, wrapper, compatibility path,
  schema, field, dependency, or runtime pass was added.
- Exact six-scenario HEAD-versus-working-tree projection remains
  `ff7aa1f9502fb30de7a92ef07df93a2107aa723675bccbc1e44c5687ee97aee7`.
  Path resolution, config payload/save order, all output bytes, group/tool/AST
  order, and optional missing-frontend behavior are identical.
- Alternating 50,000-run whole-command mock medians are within overlapping
  ranges: empty `267.387 -> 266.970 ms`, repository shape
  `437.457 -> 439.188 ms`, and full-stack fixture shape
  `608.221 -> 591.151 ms`. Eleven real full-stack detections also overlap
  broadly at median `34.662 -> 35.410 ms`; no material runtime claim or
  regression is supported.
- Focused warning-strict detect/database-tooling tests pass 6/6 before and
  after. Full warning-strict pytest passes 1,451 tests with cache disabled in
  544.84s.
- Scoped Ruff, Ruff format, repository-wide Ruff unused-symbol checks,
  `compileall`, and `git diff --check` pass. A pre-existing touched-file import
  ordering issue was normalized with zero LOC change. Tests and unrelated
  production files are byte-unchanged.
- Wheel SHA-256:
  `14e8ef19494d6655b3007742dd167cc24f7b56c1d730ea29b07989f0f58880e3`.
- Sdist SHA-256:
  `b88a6b4589696c1e41638c7c222deef6a943014002007ea541bdd1695c51d361`.
- Fresh-install metadata reports version 1.9.0, Python >=3.11, and 14
  dependency declarations. All 82 package modules import; CLI
  help/detect/map/prototype smokes and `pip check` pass.
- Checkout and fresh-installed canonical prototype both remain
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two canonical qualification replays remain byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Qualification evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/036.DGRyPU`.
- Refreshed graph contains 6,027 nodes and 25,789 edges and is bound to source
  commit `482db87ca53b1a1031ae6042960873f9dd4734aa`.
- Multi-axis review: no findings / APPROVE.
- Remaining risk: direct iteration no longer honors invalid `None`,
  falsey-custom-iterable, side-effectful truthiness, or mutation-on-repeat-read
  behavior. Canonical `ProjectProfile` fields are typed lists, all valid
  distributions pass, and the sole intentional missing-frontend fallback is
  preserved. Supporting invalid collection shapes would add compatibility
  behavior outside the model contract.
- Plan 037 recommendation: measure and simplify redundant post-empty history
  selection in `uidetox.commands.history_cmd.run`. Refreshed graph reports 105
  lines, complexity 10, cognitive complexity 18, 2 loops, loop depth 1, and
  four direct malformed/full-history test callers. After the early
  `not summary_runs` return, two `if summary_runs else 0` score branches are
  unreachable, while the precomputed `runs` selection is used only by JSON.
  Preserve `compare_runs`/`load_run_history` call order, empty compact JSON,
  non-empty indented JSON, `--full` raw fields, table/progression bytes,
  malformed coercion, and all summary/full ordering. Remove only proven
  redundant selection; add no renderer helper, model, cache, wrapper, schema,
  fallback, output change, or extra history traversal.

## STOP conditions

Stop without source integration if:

- path/root, detection, persistence, output, field access, tool order, AST
  capability, or error behavior changes for valid `ProjectProfile` data;
- optional missing-frontend compatibility changes;
- tool grouping, order, duplicates, labels, spacing, or serialization changes;
- consolidation adds a group traversal, helper, table, cache, compatibility
  layer, runtime pass, schema, or dependency;
- production LOC, cyclomatic complexity, or cognitive complexity does not
  improve;
- whole-command timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
