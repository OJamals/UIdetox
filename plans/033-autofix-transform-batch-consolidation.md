# Plan 033: Autofix transform batch consolidation

## Status

DONE

## Magic moment

`uidetox autofix` preserves exact T1 classification, preview text, transform
order, file order, subprocess behavior, change detection, auto-commit safety,
and remaining-issue reporting while each category-to-transform relationship is
projected once instead of rescanning every category for every shared transform.

## Live baseline

Measured on 2026-07-27 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `c6e0ec5aba53ec2c85dc32fe7b44ba4bdb189502`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 032 is DONE; Plan 033 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,027 nodes and 25,737 edges and is bound to Plan 032 source commit
  `7669af6da0c2dbe51c722d80a0b9f4fce6c47b18`;
- `uidetox.commands.autofix.run` is a dynamic CLI entry point with filesystem,
  subprocess, and optional Git side effects. Treat blast radius as CRITICAL
  even though static inbound call tracing cannot see argparse dispatch;
- graph metrics are 223 lines, complexity 34, cognitive complexity 95,
  8 loops, loop depth 2, and zero loop-local linear scans;
- production contains 40,116 lines, 981 functions, and 132 classes/models;
- tests contain 30,700 lines, 1,626 functions, and 40 classes;
- focused warning-strict baseline passes 6 autofix tests with cache disabled;
- Plan 032's full warning-strict baseline remains 1,451 passing tests.

## Measured distribution and scan work

The live ignored UIdetox state contains:

- 214 total issues;
- 42 T1 issues;
- 7 resulting categories;
- 24 unique issue files;
- category counts: accessibility 9, code quality 5, content 18, dead code 1,
  layout 2, other 1, and typography 6;
- extension counts preserve mixed CSS/TS/TSX handling: existing transforms see
  JS/TS files in accessibility, code quality, and typography while layout's
  two live issues are CSS-only.

The category authority contains 15 named categories. Eight categories map onto
three shipped transforms:

- typography and motion use `typography.js`;
- color and materiality use `color.js`;
- layout, states, code quality, and accessibility use `spacing.js`;
- every other category retains the existing `<category>.js` fallback and is
  skipped when that file does not exist.

For the live distribution:

- category-to-transform lookups fall 21 to 7;
- full `grouped.items()` rescans fall 14 to zero;
- relevant issue-file visits remain 22;
- aggregate category mapping plus relevant issue visits fall 43 to 29
  (`-32.6%`);
- transform/file batch projection is exactly equal;
- seven samples of 3,000 pure projections produce medians of 288.583 ms
  baseline and 243.561 ms consolidated, ratio 0.844.

For a representative all-category projection:

- category-to-transform lookups fall 60 to 15;
- full group rescans fall 45 to zero;
- relevant issue-file visits remain 9;
- aggregate projection visits fall 69 to 24 (`-65.2%`);
- transform/file batch projection remains exactly equal.

Runtime is secondary to deletion and cognitive reduction. Keep only if exact
observable behavior remains, production LOC decreases, graph complexity
improves, and controlled projection timing does not regress.

## Frozen behavior and side-effect contract

Preserve exactly:

- `load_state`, `load_config`, and `get_project_root` call order;
- T1 filtering and original issue order;
- no-issue message and return behavior;
- category classification authority, first-match precedence, category insertion
  order, guidance text, issue text, command text, blank lines, and dry-run text;
- dry-run performs no transform discovery, dirty-worktree check, file access,
  subprocess, or Git work;
- category fallback from `<category>.js`;
- transform existence checks and one execution per unique shipped transform;
- transform order determined by the first category occurrence in `grouped`;
- file collection order before set deduplication;
- existing `list(set(files_to_fix))` deduplication and its observable process
  order;
- JS/TS extension filtering after deduplication;
- exact `npx jscodeshift` arguments, parser, timeout, cwd, and per-file order;
- pre/post UTF-8 file reads, `OSError` handling, and content-based change
  detection independent of subprocess stdout;
- nonzero stderr truncation, missing-`npx` break scope, timeout handling, and
  generic child-process `OSError` reporting;
- `changed_files` absolute-path representation and set behavior;
- dirty-worktree auto-commit suppression;
- per-file Git add arguments/order, commit message, `--no-verify`, cwd,
  exception boundary, and success/failure text;
- rescan instruction and remaining-T1 normalized-path comparison;
- first-ten remaining issue order and text truncation;
- fallback agent instruction text and auto-commit notice;
- all return values, exit codes, state/config lifecycle, and filesystem/Git
  side effects.

Live dry-run baseline:

- return code 0;
- 111 stdout lines;
- stdout SHA-256
  `eaf30a2894d5b2d84a51f97771c22d8fa09391a58f2989d62608e3ef1b62cb31`;
- empty stderr SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## History and architecture

- `a3a2d0e` introduced the initial command and dry-run interface.
- `74564a8` introduced category grouping and ordered guidance output.
- `74081be` introduced shared transform mapping, `transforms_run`, and the
  nested all-category rescan so multiple categories could share one transform.
- `168bf26` hardened KeyError/TypeError/exit-code behavior.
- `e582819` added project-root normalization, content-based change detection,
  dirty-worktree protection, and auto-commit lifecycle.
- `1571409` formatted code and added later mapping comments; it did not change
  the core traversal.
- `run(args)` remains the existing deep command interface. Do not split it
  merely to relocate lines.
- `_categorize_issue` and `_CATEGORIES` remain classification authorities.
- `check._auto_commit_changed_files` is not reusable here without observable
  changes: it batches Git add paths, inserts `--`, changes error detail and
  exception behavior, and would couple command implementations through a
  private helper. Preserve autofix's existing Git interface.
- `_normalize_issue_path` earns its local seam across transform execution and
  remaining-issue comparison; retain it.
- `transforms_run` and `transform_key` become stale once transform batches are
  unique by construction. Delete them rather than layer another index beside
  them.

## Architecture decision

- Keep existing T1 category grouping for preview output.
- Project categories once into insertion-ordered transform groups.
- Store existing category issue lists, not a parallel issue/index model.
- Iterate each unique transform group once.
- Flatten issue files only after confirming the transform exists, preserving
  relevant issue visits and avoiding work for unsupported categories.
- Preserve the original flatten, set-dedup, then extension-filter sequence.
- Delete the nested all-category rescan, `transforms_run`, `transform_key`, and
  comments made obsolete by unique transform groups.
- Remove any single-use local that becomes redundant.
- Add no helper, function, type, model, enum, cache, graph, wrapper, facade,
  adapter, compatibility fallback, schema, field, dependency, or public
  interface.
- Keep tests unchanged because this is a pure refactor.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace the dynamic CRITICAL CLI and inspect exact source.
- [x] Inspect category/transform authorities, existing helpers, tests, Git
      history, and blame.
- [x] Measure live/all-category distributions, scan equations, projection
      equality, timing, dry-run output hash, and source/test size.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate transform projection

- [x] Project categories into unique transforms once.
- [x] Delete repeated all-category traversal and redundant dedup state.
- [x] Preserve transform/file/output/subprocess/Git order and behavior exactly.
- [x] Reduce production LOC, complexity, cognitive complexity, and scan work.
- [x] Add no symbol or compatibility layer; keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass focused and full warning-strict pytest with cache disabled.
- [x] Pass scoped Ruff, Ruff format, repository-wide unused-symbol checks,
      `compileall`, and `git diff --check`.
- [x] Prove tests and unrelated production files remain unchanged; verify the
      standard-library `itertools.chain` import with scoped checks.
- [x] Build wheel/sdist; verify metadata, fresh install, all package imports,
      CLI smokes, and `pip check`.
- [x] Replay canonical prototype/qualification artifacts and intentional
      historical Plan 025 failure.
- [x] Complete correctness/readability/architecture/security/performance review.

### Task 4: Integrate

- [x] Commit source only after all gates pass.
- [x] Refresh and commit codebase-memory graph after source commit.
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 034
      recommendation.
- [x] Commit Plan 033/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `4ecb4b5c57cba53b110492062916a3bde7345678`.
- Graph refresh commit:
  `e60c426c2dba6d463b56b7878ed6b4d03d209a57`.
- Production delta: 7 insertions, 17 deletions, net `-10` lines;
  40,116 to 40,106 lines. Functions remain 981; classes/models remain 132.
  Tests remain unchanged at 30,700 lines, 1,626 functions, and 40 classes.
- `autofix.run` graph metrics: lines 223 to 212, complexity 34 to 32,
  cognitive complexity 95 to 89. Eight loops, loop depth 2, and zero
  loop-local linear scans remain unchanged.
- Removed code: the nested full-category transform rescan, `transforms_run`,
  `transform_key`, duplicate transform mapping work, obsolete comments, and the
  single-use `auto_commit` local.
- Added only one standard-library import, `itertools.chain`, to flatten existing
  category issue lists at the point each transform executes. No dependency or
  new production symbol was added.
- Live projection: category-to-transform lookups 21 to 7, full group rescans
  14 to zero, relevant issue visits unchanged at 22, aggregate projection visits
  43 to 29 (`-32.6%`).
- All-category projection: lookups 60 to 15, rescans 45 to zero, relevant issue
  visits unchanged at 9, aggregate visits 69 to 24 (`-65.2%`).
- Controlled final timing, seven samples of 3,000 live projections: 304.515 ms
  baseline to 251.598 ms consolidated, ratio 0.826.
- HEAD-versus-working-tree behavior probing passed 11 no-issue, dry-run,
  unsupported-transform, shared-transform, changed-file, clean/dirty
  auto-commit, nonzero, missing-`npx`, timeout, and `OSError` scenarios. Exact
  stdout, category projection, subprocess calls/kwargs, file contents, return,
  and exception projection SHA-256:
  `0e8a1fcb931aed68ae8b40851c26b25687a01d122b63200189bfdee05029c11a`.
- Exhaustive transform/file batch equivalence passed 111,111 category
  sequences, lengths 0-5 across ten mapped/unsupported categories, including
  duplicate files and mixed CSS/TSX filtering. SHA-256:
  `e5c354dfbcbebfc1cece3bfc7e867cd365ae9ae3e38c2256e25b3c23abcac1d0`.
- Live dry-run remains return code 0, 111 stdout lines, empty stderr, and exact
  stdout SHA-256
  `eaf30a2894d5b2d84a51f97771c22d8fa09391a58f2989d62608e3ef1b62cb31`.
- Warning-strict focused pytest: 6 passed before and after. Warning-strict full
  pytest: 1,451 passed with cache disabled in 482.50 seconds; installed
  Playwright caused optional browser cases to execute instead of skip.
- Scoped Ruff `E4/E7/E9/F`, Ruff format, repository-wide unused-symbol checks,
  `compileall`, and `git diff --check` passed. Scoped full Ruff retains exactly
  the two pre-existing findings `I001` and `PLW1510`; no new finding exists.
- Build, fresh install, all 82 package submodule imports, metadata
  (`1.9.0`, Python `>=3.11`, 14 dependency declarations), CLI smokes, and
  `pip check` passed.
- Canonical prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Wheel SHA-256:
  `512a4413c60e792d4bb6fb67df70e66148b0fc4573b464d2dcfbc1c18e3864e2`.
- Sdist SHA-256:
  `ac0872d6b9e70bc3bdd9c09bd2b94f956ffd83fc6669ae49f45c1e2ed6d65e67`.
- Historical Plan 025 still fails exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/033.MoenxW`.
- Refreshed graph: 6,027 nodes / 25,764 edges, bound to the source commit.
- Multi-axis review verdict: no findings; APPROVE. No behavior, public
  interface, schema, field, model, enum, cache, graph model, wrapper, facade,
  adapter, compatibility fallback, external dependency, test, release, tag, or
  PyPI change occurred.
- Remaining risk: bundled transform existence is now checked once per unique
  transform rather than repeatedly for categories sharing a transform. Bundled
  package assets are immutable during an invocation; concurrent external
  mutation of installed transform files remains unsupported.
- Plan 034 recommendation: measure `uidetox.commands.capture.run` before
  changes. It is the highest remaining production cognitive hotspot at
  171 lines, complexity 26, cognitive complexity 107, two loops, and dynamic
  CRITICAL CLI/runtime blast radius. Consolidate only proven duplicate AFTER
  capture/diff/error-policy orchestration; preserve responsive versus desktop
  output text, `diff_meta.json` schema differences, runtime viewport discovery,
  atomic `latest.png` lifecycle, missing-dependency behavior, exit codes, and
  all screenshot/evidence ordering. Stop if improvement requires helper
  proliferation or moves branches without deleting them.

## STOP conditions

Stop without source integration if:

- preview, dry-run, transform, file, subprocess, Git, or remaining-issue order
  changes;
- category classification or transform mapping changes;
- unsupported categories begin traversing issue files or running transforms;
- consolidation adds a helper, model, cache, compatibility layer, or parallel
  authority;
- error handling, timeout behavior, path normalization, dirty-worktree safety,
  auto-commit, state/config lifecycle, or return/exit behavior changes;
- production LOC, complexity, cognitive complexity, or measured scan work does
  not improve;
- controlled timing regresses materially;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
