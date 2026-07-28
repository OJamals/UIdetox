# Plan 040: Submit-binding direct scan consolidation

## Status

DONE

## Magic moment

Native-form reconciliation preserves exact submit-binding truth while one
shared listener suffix and one direct-selector search replace duplicated
per-selector direct scans.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `431c24ca8fa900f540db2f850e7a39767f772396`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 039 is DONE; Plan 040 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,809 edges and is bound to Plan 039 source commit
  `9a18248c4c20132f04799a8ae64e593ef470b058`;
- `_has_submit_binding` has CRITICAL blast radius through
  `_all_native_forms_have_submit_handlers`, `reconcile_project_issues`, and
  `analyze_directory`;
- target metrics are 28 lines, cyclomatic complexity 4, cognitive complexity
  7, one loop at depth 1, and three graph-reported linear scans inside that
  loop;
- `analyzer_project.py` contains 148 lines;
- production contains 40,071 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict form tests pass 7 tests with cache disabled;
- Plan 039's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

Repository fixture/source text across 197 relevant Python/HTML/JS/JSX/TS/TSX
files contains:

| Measure | Count |
| --- | ---: |
| `<form>` occurrences | 17 |
| `<form id=...>` occurrences | 1 |
| `document.getElementById(...)` occurrences | 5 |
| `document.querySelector(...)` occurrences | 6 |
| selector assignments | 5 |
| submit listeners | 1 |

The canonical full-stack fixture uses one identified native form, one
`getElementById` assignment, and one suffix variable submit listener.
Synthetic coverage therefore freezes sparse direct, assigned, negative,
ordering, and selector-crossing routes rather than extrapolating from one
fixture.

An external 1,014-case probe contains 806 true and 208 false results. It
covers both selector kinds, both quote styles, whitespace/case variants,
escaped IDs, direct listeners, `const`/`let`/`var` assignments, listener
position, first-assignment ownership, cross-selector combinations, wrong IDs,
wrong events, mismatched quotes, and three-fragment ordering permutations.

| Work | Current | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Regex searches | 3,196 | 2,383 | 25.4% |
| Characters scanned | 432,465 | 317,615 | 26.6% |

Candidate/baseline median timing ratios are 0.7910 overall, 0.6749 direct,
0.9600 assigned, and 0.9051 negative. No route regresses. Semantic SHA-256 is
`07142a80e10f97a253d8218d4bae06b55a9344c5e1dfbd43448d61d9c5b2fa86`
with zero mismatches.

## Frozen behavior and boundaries

Preserve exactly:

- `form_id` is escaped with `re.escape`;
- selector grammar remains exact `document.getElementById("id")` or
  `document.querySelector("#id")`, with current quote and whitespace rules;
- matching remains case-insensitive;
- direct binding remains exact same-quote `addEventListener("submit", ...)`;
- assignment grammar remains `const|let|var`, current JavaScript identifier
  class, selector pattern, and optional semicolon;
- the first assignment per selector kind remains authoritative;
- selector assignment order remains `getElementById` then `querySelector`;
- variable binding is searched only after that assignment's end;
- current `\b` variable boundary, including `$` behavior, remains unchanged;
- later same-kind assignments do not override the first;
- get/query selector kinds remain independently attributable;
- empty, malformed, partial, unrelated, mismatched-quote, wrong-ID, and
  wrong-event text returns the same boolean;
- no input mutation, exception, I/O, or serialization behavior changes;
- native-form reconciliation, issue suppression, finding order/bytes,
  analyzer catalog, scan, state, map, redesign, review, workflow, prototype,
  runtime, qualification, and package interfaces remain unchanged.

The function returns only a boolean and performs no mutation. Therefore
checking the combined direct-selector boolean before assignment attribution
preserves observable behavior. Assignment searches remain separate and
ordered because combining them would change first-assignment ownership.

## History and architecture

- `db8de07` introduced native-form project reconciliation, both selector
  forms, first assignment per selector kind, and suffix-only variable binding.
- `1571409` only normalized regex formatting; it changed no semantics.
- `_all_native_forms_have_submit_handlers` owns form identification and joined
  inline/linked script source.
- `_has_submit_binding` owns selector/binding recognition.
- `reconcile_project_issues` owns whether project evidence suppresses
  `FORM_NO_SUBMIT_SLOP`.
- No existing index or cache is needed. This is bounded text recognition over
  one already-joined source string.

## Architecture decision

- Hoist the repeated submit-listener suffix into one local pattern.
- Combine only the two direct selectors into one noncapturing alternation and
  search it once before the assignment loop.
- Keep separate ordered assignment searches.
- Combine the `None` guard and suffix listener predicate without changing the
  first assignment match.
- Delete duplicated direct-listener regex/control flow and the temporary
  escaped variable.
- Add no function, helper, type, model, enum, compiled-regex cache, index,
  graph, wrapper, facade, adapter, fallback, schema, field, dependency, or
  public interface.
- Keep only if production LOC, graph scan count, and cognitive complexity fall;
  exact behavior, artifacts, and all gates must remain unchanged.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect exact target/caller/data flow.
- [x] Inspect tests, fixture/source distributions, Git history, and blame.
- [x] Separate direct-selector repetition from intentional assignment
      attribution.
- [x] Pass focused warning-strict tests before edits.
- [x] Record exact differential, scan-work, and timing baselines.

### Task 2: Consolidate direct binding recognition

- [x] Share the existing submit-listener suffix.
- [x] Search both direct selectors once outside the assignment loop.
- [x] Preserve per-selector first-assignment and suffix ownership.
- [x] Reduce production LOC, graph scans, and cognitive complexity.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
- [x] Prove regex calls and scanned characters fall.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 041
      recommendation.
- [x] Commit Plan 040/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `f21f243f9f8bdb1e23b9eb52bc17bb4a8ff3077b`.
- Graph refresh commit:
  `8c4b8ba04ef9a5ccc2fc29a58b377d000a633bad`.
- Production delta is +8/-12, net -4 lines. `analyzer_project.py` falls
  148 -> 144 lines; production falls 40,071 -> 40,067 lines.
- Production symbols remain 979 functions and 132 classes/models across 83
  Python files. No test changed.
- `_has_submit_binding` falls 28 -> 23 lines, cyclomatic complexity 4 -> 3,
  cognitive complexity 7 -> 4, and graph-reported loop scans 3 -> 2. Its one
  loop, loop depth 1, and zero loop-local allocations remain unchanged.
- Refreshed canonical graph contains 6,025 nodes and 25,813 edges and is bound
  to source commit `f21f243f9f8bdb1e23b9eb52bc17bb4a8ff3077b`.
- The 1,014-case source and fresh-installed probes preserve 806 true and 208
  false results with zero mismatches and semantic SHA-256
  `07142a80e10f97a253d8218d4bae06b55a9344c5e1dfbd43448d61d9c5b2fa86`.
- Regex searches fall 3,196 -> 2,383 and scanned characters fall
  432,465 -> 317,615.
- Final source candidate/baseline median timing ratios are 0.7970 overall,
  0.6796 direct, 0.9565 assigned, and 0.9106 negative. Fresh-installed
  ratios are 0.7615 overall, 0.6660 direct, 0.9426 assigned, and 0.9951
  negative. No route materially regresses.
- Focused warning-strict pytest passes 7 tests before and after. Final full
  warning-strict pytest passes 1,451 tests in 311.86 seconds with cache
  disabled.
- Full target Ruff, target format, repository-wide Ruff `F`, `compileall`,
  package imports, CLI smokes, `pip check`, and `git diff --check` pass.
- Target cleanup also replaces legacy `typing.Iterable` with
  `collections.abc.Iterable` and accepts Ruff's required nested-function
  spacing. The broader repository Ruff sweep remains out of scope.
- Wheel SHA-256:
  `310b0612ec65ad8ab1cb82a5d2629ccb2336264f57da23e74a6b2e86f91bb00c`.
- Sdist SHA-256:
  `99e7aa1a0a67dcd54842bfa842d04d42210591648bde223fb0a45b46c3846523`.
- Source and fresh-installed canonical prototype SHA-256 remains
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Two canonical qualification replays remain byte-identical at SHA-256
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Multi-axis correctness, readability, architecture, security, and
  performance review reports no findings: APPROVE.
- Evidence is preserved at
  `/Users/omar/Documents/Projects/.uidetox-qualification/040.62rRxs`.
- No release, tag, PyPI action, archived-stash mutation, or qualification
  artifact rewrite occurred.

Removed code is the duplicated per-selector direct-listener search, repeated
listener suffix, separate `None` guard, and temporary escaped variable. One
local listener suffix and one direct-selector alternation replace them.
Selector assignment searches remain separate and ordered; all finding,
serialization, and public boundaries remain unchanged.

## Remaining risk

Recognition remains regex-based and intentionally models only the existing
two DOM selector spellings. The direct alternation is safe because neither
selector contains a capture group; adding one would shift the listener
backreference. Future selector grammar changes must preserve group numbering,
first assignment per selector kind, and suffix-only variable attribution.

## Plan 041 recommendation

Measure `_javascript_code_positions` in `uidetox/contract_adapters.py`. It has
seven inbound production consumers and graph-reports two `content.find`
searches inside its outer scan. Evaluate replacing the duplicated line/block
comment branches with one delimiter-selecting branch and one search while
preserving that `//` excludes its newline, `/* */` includes its closing
delimiter, unterminated comments mask through EOF, strings/template literals
retain current escaping behavior, and every output tuple position remains
byte-for-byte identical. Require negative production LOC, lower cognitive
complexity, one fewer graph scan, exhaustive position-vector equivalence, and
unchanged route extraction. Add no lexer, helper, parser model, cache, index,
fallback, or compatibility layer; stop if consolidation changes existing
regex-literal limitations or any adapter output.

## STOP conditions

Stop without source integration if:

- selector, quote, whitespace, case, ID escaping, or same-quote semantics
  change;
- first assignment per selector kind, selector order, suffix-only variable
  binding, or current `\b` behavior changes;
- assignment recognition is combined, uses `finditer`, or changes later
  same-kind assignment behavior;
- issue suppression, finding bytes/order, exceptions, mutation, or serialized
  output changes;
- a helper, cache, index/model, wrapper, compatibility layer, schema,
  interface, dependency, or second owner is added;
- production LOC, graph scans, or cognitive complexity do not fall;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
