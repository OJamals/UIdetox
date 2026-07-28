# Plan 042: Semantic class-state search consolidation

## Status

DONE

## Magic moment

Semantic CSS interaction evidence preserves exact direct/nested selector truth
while one alternation search replaces two full-stylesheet searches per valid
class token.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `a271ac08bae781b7c221288ee16db774f065aa71`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 041 is DONE; Plan 042 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,808 edges and is bound to Plan 041 source commit
  `5944b722ec7dbe33f1b8e7e47e981e9c5543088d`;
- `_semantic_class_has_state` has CRITICAL blast radius through
  `class_list_has_interaction_state` and interaction finding analysis;
- target metrics are 24 lines, cyclomatic complexity 5, cognitive complexity
  7, one loop at depth 1, and two graph-reported linear scans inside that loop;
- `analyzer_interactions.py` contains 166 lines;
- production contains 40,063 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict interaction baseline passes 8 tests with cache
  disabled;
- Plan 041's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

Repository CSS/source fixtures contain:

| Measure | Count |
| --- | ---: |
| CSS files | 5 |
| CSS characters | 20,032 |
| Selector lists | 138 |
| Class selectors | 278 |
| HTML/JSX/TSX class attributes | 230 |
| `:hover` occurrences | 9 |
| `:focus` occurrences | 2 |
| `:focus-visible` occurrences | 1 |
| Nested `&:` state occurrences | 0 |

The repository exercises direct and global-tag state evidence but has no
nested `&:` fixture. Synthetic coverage therefore freezes nested behavior
instead of treating absence as permission to remove it.

An external 41,489-case matrix covers:

- empty, valid, invalid, escaped, underscored, hyphenated, and multiple class
  tokens;
- direct hover/focus/focus-visible selectors;
- attribute and functional-pseudo chains before the target state;
- nested same-line and multiline `&:` selectors;
- unrelated, prefix/suffix, malformed, and multiple-rule text;
- `hover` and ordered `focus|focus-visible` state tuples;
- `button` and `a` global-tag preemption;
- three-fragment selector ordering permutations.

Baseline and candidate produce 15,139 true and 26,350 false results with zero
mismatches and semantic SHA-256
`1e1d83d2c4b306eed701a459cddb6acd708c4e717961d40b2ff78ad82b7ac99b`.

| Work | Current | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Regex searches | 52,998 | 30,126 | 43.2% |
| Stylesheet characters scanned | 3,422,943 | 1,950,235 | 43.0% |

Final source candidate/baseline median timing ratios are 1.0332 direct, 0.9676
nested, and 0.9595 negative. Fresh-wheel ratios are 1.0185 direct, 0.9986
nested, and 0.9511 negative. No route materially regresses.

## Frozen behavior and boundaries

Preserve exactly:

- project-root discovery, stylesheet signature, 64-entry text cache, ignored
  directories, read-error handling, source order, and joined stylesheet bytes;
- empty stylesheet returns false;
- `_tag_has_state` remains first and global tag evidence preempts class search;
- state tuple order and literal `re.escape` handling remain unchanged;
- class tokens remain whitespace-split and processed in input order;
- valid tokens remain `[A-Za-z_][\w-]*`; invalid tokens are skipped;
- direct pattern remains exact class token followed by zero or more attribute
  selectors/pseudo-classes and the requested state;
- nested pattern remains exact class token, opening rule brace without nested
  braces, and `&:` requested state;
- direct search remains case-sensitive and line-bounded by its character
  classes;
- nested search retains DOTALL behavior;
- class-prefix/suffix non-matches, malformed CSS, first true short-circuit,
  boolean return, exceptions, and input mutation remain unchanged;
- utility-class detection and public `class_list_has_interaction_state`
  behavior remain unchanged;
- analyzer finding IDs, order, lines, snippets, provenance, confidence, state,
  scan, map, redesign, review, workflow, prototype, runtime, qualification,
  and serialization remain unchanged.

Applying DOTALL to the combined alternation does not broaden the direct branch:
that branch contains no dot wildcard. Both branches return only a boolean and
expose no capture groups, match positions, or provenance.

## History and architecture

- `d5898c9` introduced cross-file interaction qualification, stylesheet
  lifecycle ownership, global element selectors, direct semantic class
  selectors, and nested `&:` selectors together.
- `_stylesheet_signature` owns freshness and path ordering.
- `_stylesheet_text` owns bounded cached reads and joined text.
- `_tag_has_state` owns global tag attribution.
- `_semantic_class_has_state` owns validated semantic class attribution.
- `class_list_has_interaction_state` owns utility-versus-semantic routing.
- Direct and nested class patterns are intentionally separate grammar owners
  but currently feed one boolean. They can remain separately named while one
  noncapturing alternation owns the scan.

## Architecture decision

- Preserve separately named `direct` and `nested` pattern construction exactly.
- Own the escaped state suffix once.
- Wrap them in one noncapturing alternation.
- Validate each token with the same `re.fullmatch` in the combined condition.
- Search once with DOTALL and return the same boolean.
- Delete the second search and boolean `or`.
- Add no function, helper, regex cache, selector/parser model, type, enum,
  index, graph, wrapper, facade, adapter, fallback, schema, field, dependency,
  or public interface.
- Keep only if production LOC, graph scan count, cyclomatic complexity, and
  cognitive complexity fall; exact results, artifacts, and all gates must
  remain unchanged.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect exact target/caller/data flow.
- [x] Inspect stylesheet owners, tests, Git history, and blame.
- [x] Measure repository and representative distributions.
- [x] Separate repeated scans from direct/nested grammar attribution.
- [x] Pass focused warning-strict tests before edits.
- [x] Record exact differential, scan-work, and timing baselines.

### Task 2: Consolidate class-state scans

- [x] Search named direct/nested patterns through one alternation.
- [x] Preserve token/state/order/global-tag/grammar boundaries.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 043
      recommendation.
- [x] Commit Plan 042/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `2d25e188d82d946c028176c6a4eb0fb3090291a7`.
- Graph refresh commit:
  `bf8fd6d37a363c2a61a0025350d76d1094d56815`.
- Production delta: +6/-8, net -2 lines; `analyzer_interactions.py`
  166→164 lines; repository production 40,063→40,061 lines.
- Production symbols remain 979 functions and 132 classes/models.
- Target: 24→23 lines, cyclomatic complexity 5→4, cognitive complexity 7→5,
  and full-stylesheet regex searches per valid token 2→1.
- Canonical graph: 6,025 nodes / 25,816 edges.
- The 41,489-case matrix remains exactly equivalent: 15,139 true, 26,350
  false, zero mismatches, semantic SHA-256
  `1e1d83d2c4b306eed701a459cddb6acd708c4e717961d40b2ff78ad82b7ac99b`.
- Regex calls fall 52,998→30,126 and scanned characters
  3,422,943→1,950,235.
- Focused warning-strict pytest: 8 passed. Full warning-strict pytest:
  1,451 passed with cache disabled.
- Scoped Ruff/format, repository-wide Ruff `F` checks, `compileall`,
  `git diff --check`, test-diff, package metadata/import/CLI/pip checks all
  pass.
- Wheel SHA-256:
  `2ec2be800f5edbc53b64ae21a72460d0db58586dacbccd9afa7679b25db1ac82`.
- Sdist SHA-256:
  `9434e79a74c3dd39eda25fb8381e6c842b4f9e9c29604d631955d6fde7cb06d2`.
- Canonical prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Multi-axis review: no findings. Same-file cleanup removed one surplus blank
  line and replaced ignored-directory `any` traversal with exact set
  disjointness; no unrelated production file changed.
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/042.EusZJb`.

## Remaining risk and Plan 043 recommendation

Remaining risk is regex-engine cost variation on adversarial stylesheet text;
the exact matrix, repository fixtures, source timings, and fresh-wheel timings
show no material regression.

Plan 043 should measure `_python_receiver_prefixes`, which has CRITICAL blast
radius, 44 lines, complexity 7, cognitive complexity 12, two loops, and two
linear scans. Both assignment and mount attribution intentionally remain
separate, but duplicate the exact `prefix|url_prefix` argument regex. Freeze
framework provenance, source-code positions, receiver overwrite order, mount
layering, and `_join_routes(prefix, existing)` order; replace only the duplicate
regex owner if exact dictionaries, serialized maps, scan work, production LOC,
and cognitive complexity improve. Stop if consolidation needs a helper, cache,
new model, reordered traversal, or code growth.

## STOP conditions

Stop without source integration if:

- utility/semantic routing, global-tag preemption, class token validation/order,
  state order/escaping, direct grammar, nested grammar, case sensitivity, or
  DOTALL behavior changes;
- alternation changes branch precedence across rule boundaries or matches a
  class prefix/suffix previously rejected;
- any boolean result, finding field/order, exception, mutation, or serialized
  output changes;
- a helper, regex cache, selector/parser model, index, wrapper, compatibility
  layer, schema, interface, dependency, or second owner is added;
- production LOC, graph scans, cyclomatic complexity, or cognitive complexity
  do not fall;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
