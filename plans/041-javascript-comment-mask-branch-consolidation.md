# Plan 041: JavaScript comment-mask branch consolidation

## Status

DONE

## Magic moment

Contract adapters preserve every code/non-code position and downstream route
observation while one comment branch replaces duplicated line/block comment
masking.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `c2d5844a846d9fbd7f10b9cce7dac688f93cbb6b`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 040 is DONE; Plan 041 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,813 edges and is bound to Plan 040 source commit
  `f21f243f9f8bdb1e23b9eb52bc17bb4a8ff3077b`;
- `_javascript_code_positions` has CRITICAL blast radius through seven direct
  consumers covering JavaScript route extraction, receiver prefixes,
  framework factories/receivers, Fastify registration, backend-source
  classification, and route-syntax classification;
- target metrics are 34 lines, cyclomatic complexity 7, cognitive complexity
  18, 2 loops at depth 2, and two graph-reported linear scans inside the outer
  loop;
- `contract_adapters.py` contains 1,592 lines;
- production contains 40,067 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict project-map baseline passes 48 tests with cache
  disabled;
- Plan 040's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

The repository contains 58 relevant JS/JSX/TS/TSX/MJS/CJS source/fixture
files totaling 104,570 characters:

| Measure | Count |
| --- | ---: |
| Newlines | 2,995 |
| `//` substrings | 28 |
| `/*` substrings | 3 |
| `*/` substrings | 4 |
| Double quotes | 2,154 |
| Single quotes | 0 |
| Backticks | 102 |
| Backslashes | 93 |

Raw substring counts intentionally include string/template contents. The
position classifier, not the distribution scan, owns whether each occurrence
is code.

An external probe freezes:

- every string of length 0–6 over `/`, `*`, newline, double quote, single
  quote, backtick, backslash, and `a`: 299,593 exact position vectors;
- 1,350 structured empty/comment/string/template/escape/unterminated/ordering
  cases;
- all 58 repository source files;
- all seven direct consumer outputs over 1,408 actual and synthetic cases.

Baseline and candidate position-vector SHA-256 are identical at
`2f5d1ee8a18e9ddf9feab71755a7bbd35ac77a3e46c231687d0422b640a18317`.
Both contain 1,295,751 false and 482,613 true positions. Position mismatches
and consumer mismatches are zero.

Candidate/baseline median timing ratios are 0.9132 actual repository files,
0.9718 line-comment-heavy, 0.9462 block-comment-heavy, 0.9631 string-heavy,
and 0.9543 mixed. No workload regresses. Runtime still performs one bounded
`find` per recognized comment; the improvement removes a duplicate scan site
and branch, not an attribution pass.

## Frozen behavior and boundaries

Preserve exactly:

- result length equals input length and type remains `tuple[bool, ...]`;
- ordinary code positions remain `True`;
- `//` masks from both slashes through the character before newline;
- the terminating newline of `//` remains `True`;
- unterminated `//` masks through EOF;
- `/* */` masks both delimiters and all content;
- unterminated `/*` masks through EOF;
- double-quoted, single-quoted, and backtick regions mask both delimiters;
- backslash inside any quote skips exactly the next character;
- unterminated quotes mask through EOF;
- comment-like text inside a recognized quote remains part of that quote;
- quote-like text inside a recognized comment remains part of that comment;
- comment recognition remains ordered before quote recognition at each
  unmasked position;
- current JavaScript regex-literal and template-interpolation limitations
  remain unchanged;
- every direct consumer preserves exact dict/set/list/dataclass/bool/string
  output, order, provenance, confidence, source, line, framework, extractor,
  path, and method;
- contract graph, ProjectMap, FrontendMap, finding, scan, review, workflow,
  redesign, prototype, runtime, qualification, mutation, and serialization
  boundaries remain unchanged.

## History and architecture

- `874a33a` introduced `_javascript_code_positions` as shared evidence
  filtering when contract adapters were extracted and hardened. Its purpose is
  preventing comments and quoted text from promoting false framework/route
  evidence.
- Later `d0ec3b0` and `8781c8a` changed neighboring contract/utility policies,
  not the position classifier.
- The classifier is already the single owner used by all seven consumers.
  No parser, AST, source-fact, index, or cache is needed for this refactor.
- Line and block comments differ only in terminator and whether the terminator
  contributes 0 or 2 characters to the exclusive end. Their mask/write/index
  lifecycle is otherwise identical.
- String/template scanning remains a distinct nested traversal because its
  escape and matching-quote semantics differ from comment search.

## Architecture decision

- Recognize `//` and `/*` through one comment branch.
- Derive one `line_comment` boolean.
- Select newline or `*/` as the terminator.
- Add 0 or 2 only when a terminator is found.
- Reuse the existing mask/write/index/continue lifecycle once.
- Leave string/template traversal byte-for-byte unchanged.
- Add no function, helper, parser/lexer, type, model, enum, cache, index,
  graph, wrapper, facade, adapter, fallback, schema, field, dependency, or
  public interface.
- Keep only if production LOC, graph scan sites, cyclomatic complexity, and
  cognitive complexity fall; exact vectors, consumer outputs, artifacts, and
  all gates must remain unchanged.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace seven CRITICAL direct consumers and downstream data flow.
- [x] Inspect exact target/callers, tests, Git history, and blame.
- [x] Measure repository and representative distributions.
- [x] Separate duplicated comment traversal from intentional string traversal.
- [x] Pass focused warning-strict tests before edits.
- [x] Record exhaustive vectors, consumer outputs, and timing baselines.

### Task 2: Consolidate comment masking

- [x] Replace duplicate line/block branches with one terminator-driven branch.
- [x] Preserve newline exclusion, block-delimiter inclusion, and EOF behavior.
- [x] Preserve string/template/escape behavior exactly.
- [x] Reduce production LOC, graph scan sites, and cognitive complexity.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree position-vector equivalence.
- [x] Pass all seven consumer-output comparisons.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 042
      recommendation.
- [x] Commit Plan 041/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `5944b722ec7dbe33f1b8e7e47e981e9c5543088d`.
- Graph refresh commit:
  `230978024c2a07cdf2d0801d9d9763476939d52f`.
- Production delta is +7/-11, net -4 lines. `contract_adapters.py` falls
  1,592 -> 1,588 lines; production falls 40,067 -> 40,063 lines.
- Production symbols remain 979 functions and 132 classes/models across 83
  Python files. No test changed.
- `_javascript_code_positions` falls 34 -> 29 lines, cyclomatic complexity
  7 -> 6, cognitive complexity 18 -> 16, and graph-reported scan sites in the
  outer loop 2 -> 1. Its two loops, loop depth 2, and zero loop-local
  allocations remain unchanged.
- Refreshed canonical graph contains 6,025 nodes and 25,808 edges and is bound
  to source commit `5944b722ec7dbe33f1b8e7e47e981e9c5543088d`.
- Source and fresh-installed probes preserve all 299,593 exhaustive vectors,
  1,350 structured cases, 58 repository files, and all seven consumer outputs
  across 1,408 cases with zero mismatches.
- Position-vector SHA-256 remains
  `2f5d1ee8a18e9ddf9feab71755a7bbd35ac77a3e46c231687d0422b640a18317`;
  true/false position counts remain 482,613 and 1,295,751.
- Final source candidate/baseline median timing ratios are 0.9217 actual,
  0.9493 line-comment-heavy, 0.9015 block-comment-heavy, 0.9890
  string-heavy, and 0.9507 mixed. Fresh-installed ratios are 0.9280, 0.9599,
  0.9344, 0.9492, and 0.9645. No workload regresses.
- Focused warning-strict project-map pytest passes 48 tests before and after.
  Final full warning-strict pytest passes 1,451 tests in 254.41 seconds with
  cache disabled.
- Full target Ruff, target format, repository-wide Ruff `F`, `compileall`,
  package imports, CLI smokes, `pip check`, and `git diff --check` pass.
- Same-file cleanup moves `Iterable`/`Mapping` from legacy `typing` imports to
  `collections.abc` and replaces duplicate OpenAPI/Swagger `startswith`
  calls with one tuple call. The broader repository sweep remains out of
  scope.
- Wheel SHA-256:
  `e1d3d9d54428a5a97f621491dc9ea98a63b3590cb453b19c010f745a8f645575`.
- Sdist SHA-256:
  `2bfbf020ad1276bfa0323a155c928099b531c8485ade5ec12d066ddcd0683be3`.
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
  `/Users/omar/Documents/Projects/.uidetox-qualification/041.Rhka2t`.
- No release, tag, PyPI action, archived-stash mutation, or qualification
  artifact rewrite occurred.

Removed code is one duplicated comment predicate, search, EOF normalization,
mask/write/index lifecycle, and the block-only `close` temporary. One
terminator-driven branch now owns both comment forms. String/template traversal
and every consumer/public boundary remain unchanged.

## Remaining risk

This remains a deliberately bounded scanner, not a JavaScript lexer. Regex
literals and template interpolation retain existing limitations. The shared
branch depends on 0 meaning line terminator exclusion and 2 meaning block
terminator inclusion; future comment kinds must not reuse that arithmetic
without exhaustive position-vector proof.

## Plan 042 recommendation

Measure `_semantic_class_has_state` in `uidetox/analyzer_interactions.py`.
It graph-reports two stylesheet searches per valid class token: direct
pseudo-state and nested `&:` state. Evaluate one alternation search while
preserving stylesheet cache/root/signature ownership, `_tag_has_state`
preemption, class-token order/validation, state order/escaping, direct versus
nested selector grammar, case sensitivity, DOTALL behavior, and exact boolean
results. Require exhaustive CSS/class/state equivalence, negative production
LOC, one fewer graph scan, no timing regression, and unchanged analyzer
findings. Add no regex cache, helper, selector model, parser, index, fallback,
or compatibility layer; stop if alternation changes branch precedence or
matches across rule boundaries.

## STOP conditions

Stop without source integration if:

- any position vector, route/framework/prefix/classification output, order,
  provenance, confidence, path, line, method, or source changes;
- line-comment newline exclusion, block-delimiter inclusion, EOF behavior,
  quote matching, escaping, or comment/string precedence changes;
- the refactor broadens into regex-literal or template-interpolation behavior;
- string scanning is combined with comment search;
- a parser, lexer, helper, cache, index/model, wrapper, compatibility layer,
  schema, interface, dependency, or second owner is added;
- production LOC, graph scan sites, cyclomatic complexity, or cognitive
  complexity do not fall;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
