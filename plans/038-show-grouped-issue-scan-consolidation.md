# Plan 038: Show grouped issue scan consolidation

## Status

DONE

## Magic moment

`uidetox show` renders the exact same grouped queue while one issue pass owns
both file grouping and global tier counting.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `9f863795ae1b55336c1aa5f268a3738e3ab8dc0c`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 037 is DONE; Plan 038 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,788 edges and is bound to Plan 037 source commit
  `6397f85c88ac27956371b4fc90dcad3b044d4ecd`;
- `uidetox.commands.show._render_grouped` is reached through dynamic CLI
  dispatch and renders normalized legacy queue data. Treat blast radius as
  CRITICAL;
- graph metrics are 63 lines, cyclomatic complexity 7, cognitive complexity
  13, 5 loops, loop depth 2, one loop-local allocation, and zero hidden linear
  scans;
- the module has 5 functions and 168 lines;
- production contains 40,076 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict prompt-safety baseline passes 22 tests with cache
  disabled;
- Plan 037's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

The live normalized queue contains 214 issues across 39 files:

- tiers: 42 T1, 141 T2, and 31 T3;
- issues per file: minimum 1, median 3, maximum 21;
- grouped output: 25,532 bytes;
- grouped output SHA-256:
  `4a9c2eca7bcb135267b550588f3e61b95efa3da4b3e051cf065a4e3d596ecdbb`.

Current grouped rendering performs:

1. one complete `issues` traversal to build `by_file`;
2. one complete `issues` traversal to build global `tiers`;
3. one `sorted_files` traversal;
4. one complete traversal of each `file_issues` list to build per-file tier
   counts;
5. one sorted traversal of each `file_issues` list to render rows;
6. bounded tier-summary iteration and sorting.

The first two passes consume the same normalized issue and have no ordering or
lifecycle boundary between them. They are true repeated traversal. The
per-file tier pass and row pass are intentional attribution/rendering work and
remain separate.

For the live queue:

- top-level issue visits: 428 before, 214 proposed;
- intentional per-file issue visits: 428 unchanged;
- bounded Python loop visits, including file/tier loops but excluding sort
  comparisons: 898 before, 684 proposed;
- reduction: 214 visits, or 23.8% of bounded loop work.

The same formulas apply to representative queues:

| Issues | Files | Tiers | Top-level visits before | Proposed |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 |
| 6 | 3 | 4 | 12 | 6 |
| 214 | 39 | 3 | 428 | 214 |
| 1,000 | 50 | 5 | 2,000 | 1,000 |

Wall-clock baseline is contaminated by unrelated repository Playwright
workloads and shows broad overlap. No speed claim is accepted from it. Retain
only if deterministic pass/visit reduction, negative LOC, lower graph
complexity, exact output equivalence, and no material isolated regression all
hold.

## Frozen behavior and boundaries

Preserve exactly:

- `load_state()` remains queue authority and normalization/sanitization
  boundary;
- `run` empty, default, pattern-filter, detailed, grouped, and no-match
  selection;
- no-pattern rendering of every issue in normalized state order;
- pattern matching against ID/file/tier, case behavior, and threshold of five;
- `defaultdict(list)` file ownership and first-file insertion order;
- stable descending file-count sort, including first-occurrence order for ties;
- global tier normalization via `issue.get("tier") or "T4"`;
- per-file tier normalization via the same expression;
- lexicographic global/per-file tier ordering;
- row tier ranking T1, T2, T3, T4, then unknown;
- stable row order within the same rank;
- the distinction where explicit falsey/unknown tier values count as T4 in
  summaries but retain their raw value for row label/color/rank;
- duplicate issues and duplicate IDs without deduplication;
- missing file fallback `unknown`, missing field fallbacks, line truthiness,
  default column 1, path shortening, 80-character threshold, and 77-plus-ellipsis
  truncation;
- ANSI escapes, headings, spacing, blank lines, hints, and every output byte;
- normalized legacy credential redaction and zero persistent-state mutation;
- direct renderer exception type/message/output for invalid normalized shapes;
- all public signatures, schemas, fields, findings, lifecycle, provenance,
  confidence, serialization, scan, review, workflow, and prototype behavior.

`by_file` and `tiers` are ephemeral render indexes. Neither crosses a function,
mutation, persistence, or serialization boundary. Building both during one
source traversal changes no owned model and creates no cache.

## History and architecture

- `a3a2d0e` introduced the initial tier summary.
- `b766c92` introduced color-coded grouped rendering, file ownership, stable
  file-count ordering, per-file tier counts, and row ordering.
- `168bf269` changed global and per-file tier aggregation from
  `get(..., "T4")` to `get(...) or "T4"` so explicit `None` cannot make tier
  sorting raise `TypeError`.
- `1571409` formatted the module without semantic change.
- File grouping and global tier counting have always been adjacent independent
  passes; history provides no distinct source, mutation, output, or lifecycle
  reason.
- `load_state` already owns finding coercion and prompt-safety normalization.
  Do not add a second owner/index model.
- `_render_detailed`, `_shorten_path`, `format_issue_location`, `show.run`,
  state persistence, and filtering remain untouched.

## Exact differential evidence

A 10-case probe freezes:

- direct empty grouped rendering;
- representative multi-file, multi-tier ordering and file-count ties;
- missing, `None`, empty, false, zero, and unknown tier behavior;
- 80/81-character issue boundaries;
- line/column truthiness and defaults;
- duplicate preservation;
- invalid issue exception type/message and partial output;
- no input mutation;
- `run` empty/default/grouped-filter/detailed-filter/no-match modes;
- exact ANSI/text bytes.

Baseline SHA-256:

`aad941cd4475219b9f276506da57f45255437c4d0896a1d17cdbbe2645b204ef`.

The same probe observes two top-level `issues.__iter__()` calls before the
change. Exact output/error records exclude that intentional work metric so the
SHA must remain unchanged while iteration count falls to one.

## Architecture decision

- Initialize `tiers` beside `by_file`.
- During the existing grouping traversal, append the issue to its file and
  increment its normalized global tier count.
- Delete the second complete `issues` traversal.
- Preserve every later sort, per-file attribution pass, and row pass.
- Add no helper, function, type, model, enum, cache, graph, wrapper, facade,
  adapter, fallback, schema, field, dependency, or public interface.
- Do not split `_render_grouped` merely to move lines.
- Keep tests unchanged because this is a pure refactor; use external
  differential evidence for exact byte/error/mutation coverage.
- Keep only if production LOC, loop count, cyclomatic complexity, and cognitive
  complexity improve and deterministic source traversal is halved.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the CRITICAL CLI and inspect exact source/callers/data flow.
- [x] Inspect state authority, prompt-safety test, Git history, and blame.
- [x] Measure live/representative distributions, passes, visits, output, and
      exact behavior.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate global aggregation

- [x] Build global tier counts during existing file-group traversal.
- [x] Delete the second complete issue traversal.
- [x] Preserve per-file tier and row traversals.
- [x] Reduce production LOC/loops/complexity without a new symbol or model.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
- [x] Prove top-level iteration 2 -> 1 and live visits 428 -> 214.
- [x] Re-run controlled timing; reject material regression.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 039
      recommendation.
- [x] Commit Plan 038/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `6d1d3771a9bb4c82065f8524e9d009d938abf770`.
- Graph refresh commit:
  `fe678bd68bb31e78e895af3f7635c6cad5e3394a`.
- Production delta: 4 insertions, 6 deletions, net -2 LOC. Production is now
  40,074 lines, 979 functions, and 132 classes/models across 83 Python files.
- `_render_grouped` fell from 63 to 60 lines, 5 to 4 loops, cyclomatic
  complexity 7 to 6, and cognitive complexity 13 to 12.
- Top-level issue traversal fell from 2 passes to 1. Live top-level visits fell
  428 to 214; bounded loop visits fell 898 to 684, a 23.8% reduction.
  Intentional per-file tier and row visits remain 428.
- Exact 10-case output/error/mutation SHA-256 remains
  `aad941cd4475219b9f276506da57f45255437c4d0896a1d17cdbbe2645b204ef`.
  Probe-observed top-level iteration fell 2 to 1 with zero mutated cases.
- Live source and fresh-installed output both remain 25,532 bytes at
  `4a9c2eca7bcb135267b550588f3e61b95efa3da4b3e051cf065a4e3d596ecdbb`.
- Whole-render timing is neutral within broad measurement variance:
  paired medians are 0.9539 empty, 0.9811 small, 0.9970 live-shape, and 1.0488
  large. Direct aggregation is 0.9926 at live shape and 0.8585 at 10,000
  issues. No wall-clock speed claim is made; exact traversal and complexity
  reduction justify the change, with no material regression.
- Focused prompt-safety pytest: 22 passed. Full warning-strict pytest with
  cache disabled: 1,451 passed in 196.57 seconds.
- Scoped Ruff/check-format, repository-wide Ruff `F` checks, `compileall`,
  `git diff --check`, test immutability, and unrelated-production boundaries
  pass. The target file's pre-existing import-order finding was normalized;
  no repository-wide format/import sweep occurred.
- Fresh package metadata remains `uidetox 1.9.0`, Python `>=3.11`, 14
  dependency records, and 82 importable modules. CLI and `pip check` pass.
- Wheel SHA-256:
  `a6f0585538a320d6f4ee02bdcf45f7c820b4309a48afed8be4cf11c1589c1388`.
- Sdist SHA-256:
  `0b3241234dcce4fc97ceea98189f1a38dd51319b7336fb32edc55b08f685d4a3`.
- Checkout and fresh-installed canonical prototype remain
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
  Two canonical qualification replays remain byte-identical at
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with:
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Added no function, type, model, enum, cache, graph, wrapper, facade, adapter,
  fallback, schema, field, dependency, serialization boundary, or public
  interface. Removed one complete issue pass and its obsolete summary comment.
- Multi-axis review found no correctness, readability, architecture, security,
  or performance issue; verdict APPROVE.
- Refreshed graph contains 6,025 nodes and 25,802 edges, is bound to the source
  commit, and confirms the loop/complexity reduction.
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/038.jWIssN`.
- Remaining risk is limited to byte-sensitive ANSI rendering, falsey tier
  normalization, file-count tie stability, and legacy prompt-safety data.
  Exact differential coverage, live source/install hashes, focused/full tests,
  and unchanged sort/per-file loops bound that risk.
- Plan 039 recommendation: measure the graph-reported
  `linear_scan_in_loop=1` and repeated regex construction in
  `uidetox.commands.next._get_relevant_context`. Preserve exact rule-ID-first
  routing, token-boundary fallback semantics, context order/deduplication,
  reference paths, prompt bytes, and subagent compatibility. Replace repeated
  work only if existing rule-registry/context structures suffice and production
  LOC/cognitive/scan complexity fall. Stop if consolidation requires a new
  compiled-pattern cache, index/model, keyword normalization guess, output
  reorder, compatibility layer, or code growth.

## STOP conditions

Stop without source integration if:

- file/tier/row order, tie stability, normalization, duplicate handling, or
  output bytes change;
- filtering, detailed/grouped threshold, prompt-safety, state mutation, or
  malformed behavior changes;
- per-file attribution/rendering traversal is removed or merged;
- consolidation adds a helper, cache, compatibility layer, schema, interface,
  dependency, or second owner model;
- production LOC, loop count, cyclomatic complexity, or cognitive complexity
  does not improve;
- deterministic top-level traversal does not fall from two passes to one;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
