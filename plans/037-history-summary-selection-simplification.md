# Plan 037: History summary selection simplification

## Status

DONE

## Magic moment

`uidetox history` preserves exact empty, summary, full, JSON, malformed-data,
ordering, and scan behavior while deleting duplicate coercion helpers and
unreachable post-empty selection branches.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `d8945237ae73b684871aae9346cb4c47836c6e08`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest or qualification workload runs;
- Plan 036 is DONE; Plan 037 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,789 edges and is bound to Plan 036 source commit
  `482db87ca53b1a1031ae6042960873f9dd4734aa`;
- `uidetox.commands.history_cmd.run` is dynamically dispatched and renders
  normalized summaries plus optionally raw malformed snapshots. Treat blast
  radius as CRITICAL;
- graph metrics are 105 lines, cyclomatic complexity 10, cognitive complexity
  18, 2 loops, loop depth 1, and zero loop-local scans/allocations;
- production contains 40,083 lines, 981 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict baseline passes all 7 history command/storage tests
  with cache disabled;
- Plan 036's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

The live repository contains 27 valid snapshots totaling 4,550,481 bytes.
Normalized scores range from 0 to 94. Current output sizes are:

| Mode | Output bytes | History scans |
| --- | ---: | ---: |
| summary text | 2,406 | 1 |
| summary JSON | 5,236 | 1 |
| full text | 12,585 | 2 |
| full JSON | 4,792,539 | 2 |

`compare_runs()` owns normalized summary projection and internally calls
`load_run_history()`. Full modes intentionally call `load_run_history()` again
to retain raw fields. That duplicate I/O is real, but consolidating it would
require a signature/model/lifecycle change outside this plan. Preserve it.

Current command selection performs:

- `compare_runs()` once for every mode;
- `load_run_history()` once more when `show_full` is true, including empty
  summary output;
- eager `runs` selection before empty-history handling, although only JSON
  consumes `runs`;
- two `summary_runs` truthiness checks for first/latest scores after an earlier
  `if not summary_runs: ... return`, so both false branches are unreachable;
- summary list indexing only for non-empty normalized data;
- full JSON uses raw `full_runs` for `runs`/`total` but normalized
  `summary_runs` for first/latest/delta;
- full text applies `_safe_text` 3–4 times, `_safe_int` 6–7 times, and
  `_safe_count` twice per raw run.

`history_cmd._safe_text` and `history._coerce_history_text` are byte-equivalent.
`history_cmd._safe_int` and `history._coerce_history_int` are equivalent for
all seven live command calls, which use one argument and therefore default
zero. Fourteen representative values spanning `None`, booleans, integers,
floats, strings, lists, and dictionaries produce identical results. Graph
shows each command-local helper has only `run` as caller.

Both duplicate command helpers and both canonical history helpers were
introduced together in `e582819`. The duplication protected malformed raw and
summary output but did not establish distinct semantics. `_safe_count` remains
unique because canonical history has no list-count coercer.

An 11-case exact behavioral probe freezes:

- missing/default args;
- all four `--full`/`--json` combinations with empty and populated summaries;
- raw/full length differing from normalized summary length;
- increasing and equal score trends;
- numeric and malformed raw fields;
- compact empty JSON and indented non-empty JSON;
- summary/full output bytes;
- `compare_runs` then optional `load_run_history` call order;
- compare/load exception type, message, output, and call boundary.

Baseline SHA-256:

`64da7f2237321a19c9c1d2f66e1c330cde837dd5097db2c5ca9438a5eeccf4b3`.

Alternating 200,000-run selection-only timing is mixed and overlapping:

- empty text `14.459 -> 16.982 ms`;
- empty full JSON `15.095 -> 14.099 ms`;
- summary text `16.354 -> 15.497 ms`;
- summary JSON `74.625 -> 79.809 ms`;
- full text `17.027 -> 16.088 ms`;
- full JSON `72.912 -> 69.395 ms`.

No runtime-speed claim is justified. Snapshot I/O and output dominate. Retain
only for deleted symbols/LOC, lower complexity, and no material whole-command
regression.

## Frozen behavior and side-effect contract

Preserve exactly:

- `full` and `json` defaults when attributes are absent;
- `compare_runs()` before any optional `load_run_history()` call;
- one summary scan in non-full modes and two scans in full modes;
- eager full-history loading when `show_full` is true, even if summary is
  empty or text/JSON later returns;
- propagation of compare/load exceptions before output;
- empty-history detection from `summary_runs`, not `full_runs`;
- exact compact empty JSON and no full raw payload when summary is empty;
- non-empty JSON indentation, key order, raw-vs-summary selection, totals,
  score endpoints, and delta;
- text headings, spacing, box drawing, arrows, emoji, rows, trends, totals,
  progression, and blank lines;
- summary and full insertion order, duplicates, and raw fields;
- normalized summary coercion and raw full-detail coercion;
- boolean rejection, float-to-int truncation, defaults, malformed values,
  issue/resolved counts, and visual evidence state;
- every public signature, CLI argument, persisted schema, and history file;
- all error and output boundaries.

## History and architecture

- `a3a2d0e` introduced summary text history and progression.
- `b766c92` added JSON output.
- `e582819` added project-root hardening, raw full modes, malformed snapshot
  resilience, canonical summary coercers, and duplicate command-local coercers.
- `eb15515` added visual evidence state to full details.
- `1571409` reformatted the module without semantic change.
- `load_run_history` remains raw snapshot authority.
- `compare_runs` remains normalized summary authority.
- `_coerce_history_text` and `_coerce_history_int` remain canonical history
  coercers; reuse them directly instead of command-local copies.
- `_safe_count` remains command-owned raw list-count policy.
- Full-mode double loading is a lifecycle/API concern, not selection
  redundancy. Do not change it here.
- No other stale/orphaned history symbol was found.

## Architecture decision

- Delete `_safe_text` and `_safe_int`.
- Import existing `_coerce_history_text` and `_coerce_history_int` under the
  command's existing call-site names; add no wrapper.
- Keep `_safe_count`; no canonical equivalent exists.
- Move `runs` selection into the non-empty JSON branch where it is consumed.
- Inside that branch, use `show_full` alone because `use_json` is already true.
- Remove unreachable `if summary_runs else 0` score fallbacks after the early
  empty return.
- Preserve `compare_runs`, `load_run_history`, full-history loading, scan count,
  all rendering, and all malformed-data behavior.
- Add no helper, function, type, model, enum, cache, graph, wrapper, facade,
  adapter, fallback, schema, field, dependency, or public interface.
- Keep tests unchanged because this is a pure refactor; use external
  differential evidence for complete mode/call/output coverage.
- Keep only if production LOC, function count, cyclomatic complexity, and
  cognitive complexity improve; exact behavior remains identical; and
  whole-command timing shows no material regression.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the CRITICAL CLI and inspect exact source/callers.
- [x] Inspect canonical coercers, storage/projection authorities, tests, Git
      history, and blame.
- [x] Measure live snapshot/output distributions, scan work, helper
      equivalence, selection timing, and exact behavior.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Simplify history selection/coercion

- [x] Delete two duplicate command coercers.
- [x] Reuse canonical history coercers without a wrapper.
- [x] Move JSON-only selection to its consumer branch.
- [x] Delete two unreachable post-empty score fallbacks.
- [x] Reduce production LOC/functions/complexity without a new symbol or pass.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 038
      recommendation.
- [x] Commit Plan 037/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `6397f85c88ac27956371b4fc90dcad3b044d4ecd`.
- Graph refresh commit:
  `2ca3800e8c5903aa82f95d63c46242061265cb6c`.
- Production delta: 6 insertions, 13 deletions, net -7 LOC. Production is now
  40,076 lines, 979 functions, and 132 classes/models across 83 Python files.
- The history command module now has 2 functions instead of 4. Aggregate
  module cyclomatic complexity fell 11 -> 10 and cognitive complexity fell
  19 -> 18. `run` remains 105 lines with complexity 10/cognitive 18; no
  traversal or rendering logic was moved into a helper.
- Removed `_safe_text`, `_safe_int`, eager non-JSON `runs` selection, and two
  unreachable post-empty score fallbacks. Added no function, type, model, enum,
  cache, graph, wrapper, facade, adapter, fallback, schema, field, dependency,
  traversal, or public interface.
- The exact 11-case differential probe remains
  `64da7f2237321a19c9c1d2f66e1c330cde837dd5097db2c5ca9438a5eeccf4b3`.
  Summary modes still scan history once; full modes still scan twice.
- Whole-command median ratios span 0.8161 to 1.0150 across empty, summary,
  full, text, and JSON modes. The maximum measured increase is 1.5%, with no
  material regression.
- Focused warning-strict pytest: 7 passed. Full warning-strict pytest with the
  cache provider disabled: 1,451 passed in 194.72 seconds.
- Scoped Ruff/check-format, repository-wide Ruff `F` checks, `compileall`,
  `git diff --check`, test immutability, and unrelated-production boundaries
  pass.
- Fresh package metadata remains `uidetox 1.9.0`, Python `>=3.11`, 14
  dependency records, and 82 importable modules. CLI and `pip check` pass.
- Wheel SHA-256:
  `024dd5baad8912ced5e0bc08155129aafe60b4d4b8848b13398de05a9396183a`.
- Sdist SHA-256:
  `7e03550d117d324cb9484cfcf733bb8ddb529668b4e70cd4e445d41a12020882`.
- Checkout and fresh-installed canonical prototype remain
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two canonical qualification replays remain byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Multi-axis review found no correctness, readability, architecture, security,
  or performance issue; verdict APPROVE.
- Refreshed graph contains 6,025 nodes and 25,788 edges, is bound to the source
  commit, and confirms the two deleted command helpers are absent.
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/037.Zql8ZM`.
- Remaining risk is limited to byte-sensitive CLI rendering and malformed raw
  snapshots. Exact differential coverage, focused/full tests, canonical
  replays, and unchanged scan/call order bound that risk.
- Plan 038 recommendation: measure and consolidate the two top-level
  `issues` traversals in `uidetox.commands.show._render_grouped` into the
  existing grouping pass, reducing whole-list scans from 2 to 1. Preserve the
  intentional per-file tier/row traversals, file/tier ordering, duplicate and
  default-tier behavior, ANSI bytes, truncation/location formatting, prompt
  safety, and all malformed legacy queue behavior. Treat blast radius as
  CRITICAL; require exact output probes, negative LOC, and lower
  loop/cognitive complexity. Add no renderer helper, group model, cache,
  wrapper, or `show.run` expansion.

## STOP conditions

Stop without source integration if:

- summary/full scan count, order, loading, normalization, or raw preservation
  changes;
- output bytes, JSON formatting/key order/selection, text grouping, scores,
  trends, totals, malformed coercion, or visual state change;
- compare/load exception timing or output changes;
- helper consolidation changes any live call result;
- simplification adds a helper, cache, compatibility layer, runtime pass,
  schema, interface, or dependency;
- production LOC, function count, cyclomatic complexity, or cognitive
  complexity does not improve;
- whole-command timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
