# Plan 043: Python receiver-prefix scan consolidation

## Status

DONE

## Magic moment

Python router and blueprint prefixes retain exact factory, source-position,
assignment, mount, and layering semantics while existing assignment/mount
regexes capture the first eligible prefix directly, deleting every nested
per-match argument scan.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `fcc9a57c67b5d0f9154e14a6e10f33e34c2b2d4b`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 042 is DONE; Plan 043 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,816 edges and is bound to Plan 042 source commit
  `2d25e188d82d946c028176c6a4eb0fb3090291a7`;
- `_python_receiver_prefixes` has CRITICAL blast radius through
  `_extract_python_routes`, then contract observations, `ProjectMap`,
  `FrontendMap`, findings, workflows, redesign, review, and serialization;
- target metrics are 44 lines, cyclomatic complexity 7, cognitive complexity
  12, two loops at depth 1, and two graph-reported linear scans inside loops;
- `contract_adapters.py` contains 1,588 lines;
- production contains 40,061 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- Plan 042's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

Repository source/test fixtures contain 137 Python files. They produce:

| Measure | Count |
| --- | ---: |
| Assignment-shaped matches | 5,063 |
| Qualified router/blueprint assignments | 0 |
| Mount matches | 0 |
| Files with attributed prefix owners | 0 |
| Attributed prefix owners | 0 |

Repository production therefore supplies no live router-prefix fixture.
Existing `test_fastapi_and_flask_decorator_adapters` covers direct
`APIRouter(prefix=...)` and `Blueprint(url_prefix=...)` through string-backed
fixtures, while mount-prefix behavior has no direct repository test. External
differential coverage freezes both paths without changing tests for this pure
refactor.

A deterministic 56,000-case matrix covers:

- direct, aliased, and namespace FastAPI/Flask imports plus unqualified imports;
- `APIRouter`/`Blueprint`, invalid factories, positional args, empty prefixes,
  `prefix`, `url_prefix`, spacing, multiline, duplicate prefix args, mixed
  quotes, nested calls, closing parentheses, comments, strings, and malformed
  values;
- `include_router`/`register_blueprint`, empty and repeated mounts, mount
  prefixes, assignment prefixes, duplicate receivers, and source-order
  permutations;
- 50,000 seeded multi-fragment combinations.

Baseline and candidate produce identical dictionaries for every synthetic and
repository case with zero mismatches and semantic SHA-256
`0a383adb5d4d601b95425a3227f67e99635ba89113c73565ebb4315a3c0b0c9e`.

| Work | Current | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Per-match prefix regex scans | 66,377 | 0 | 100% |
| Argument characters scanned separately | 1,256,591 | 0 | 100% |
| Assignment/mount source traversals | 2 | 2 | 0% |

Final source candidate/baseline median timing ratios are 0.9159 direct, 1.0112
negative, 0.9464 mounted, and 0.9146 mixed. Two fresh-wheel runs span
0.9502–1.0217 direct, 0.9778–1.0443 negative, 0.9352–1.0184 mounted, and
0.9542–1.0114 mixed. Variation crosses zero but no axis materially regresses;
the separately measured nested scan work is eliminated exactly.

## Frozen behavior and boundaries

Preserve exactly:

- `_python_framework_factories` AST provenance and accepted
  `APIRouter`/`Blueprint` constructors;
- `_python_code_positions` comment/string exclusion and malformed-source
  handling;
- assignment regex receiver/factory grammar, DOTALL behavior, left-to-right
  traversal, first closing-parenthesis boundary, and match start;
- mount regex receiver grammar, accepted `include_router` and
  `register_blueprint` methods, DOTALL behavior, left-to-right traversal,
  first closing-parenthesis boundary, and match start;
- first word-bounded `prefix|url_prefix` key inside matched args;
- case sensitivity, whitespace, quote-class behavior, empty values, and
  rejection when a value crosses the first closing parenthesis;
- all assignments process before all mounts regardless of source interleaving;
- later assignment to one receiver overwrites earlier assignment;
- mounts retain source order and layer via
  `_join_routes(mount_prefix, existing_prefix)`;
- mounts remain attributable without framework-factory qualification;
- comments/string matches remain excluded by their starting source position;
- dictionary insertion/overwrite order, keys, values, exceptions, and input
  mutation remain unchanged;
- backend observation order, methods, paths, source identity, adapters,
  confidence, provenance, graph nodes/edges, IDs, fingerprints, maps,
  findings, scans, redesign, review, workflow, prototype, runtime,
  qualification, and serialization remain unchanged.

## History and architecture

- `874a33a` introduced `_python_receiver_prefixes` during contract evidence
  lineage hardening.
- Factory qualification prevents unrelated constructors from becoming
  backend route owners.
- Code-position filtering prevents comments and string literals from becoming
  evidence.
- Assignment attribution establishes receiver-local prefixes.
- Mount attribution intentionally remains separate because it layers a mount
  prefix onto any receiver prefix after every assignment is known.
- `_join_routes(prefix, suffix)` order is observable and must not reverse.
- The duplicate inner regex is traversal residue: both outer regexes already
  own the exact bounded argument region and can capture the same first prefix.

## Architecture decision

- Keep assignment and mount traversals separate.
- Own one local first-prefix argument fragment.
- Preserve every outer match by using prefix-bearing/fallback alternation
  inside the same first-parenthesis boundary.
- Capture the first prefix directly in each existing outer regex.
- Replace nested `re.search` plus match branches with direct optional capture
  guards.
- Add no function, module constant, cache, parser, model, type, enum, index,
  graph, wrapper, facade, adapter, fallback, schema, field, dependency, or
  public interface.
- Keep only if production LOC, per-match scans, cyclomatic complexity, and
  cognitive complexity improve without material timing regression; exact
  dictionaries, serialized artifacts, and all gates must remain unchanged.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect exact target/caller/callee flow.
- [x] Inspect tests, Git history, blame, and architectural owners.
- [x] Measure repository and representative distributions.
- [x] Separate intentional assignment/mount attribution from duplicate nested
      prefix scans.
- [x] Record exact differential, work, and timing baselines.
- [x] Pass focused warning-strict tests before edits.

### Task 2: Consolidate prefix scans

- [x] Capture first prefix inside existing assignment/mount regexes.
- [x] Preserve factory/source-position/order/layering boundaries.
- [x] Reduce production LOC, nested scans, and cognitive complexity.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact baseline-versus-working-tree behavioral equivalence.
- [x] Prove nested regex calls and separately scanned argument characters fall.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 044
      recommendation.
- [x] Commit Plan 043/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `1ef46d9d65ee10b50df84fa5e32ba00b191847d4`.
- Graph refresh commit:
  `0dbca8229534467ea2fcd6b36d1d5fc9e8f3e8ce`.
- Production delta: +17/-21, net -4 lines; `contract_adapters.py`
  1,588→1,584 lines; repository production 40,061→40,057 lines.
- Production symbols remain 979 functions and 132 classes/models.
- Target: 44→40 lines, cyclomatic complexity 7→5, cognitive complexity 12→8,
  and graph-reported linear scans inside loops 2→0.
- Canonical graph: 6,025 nodes / 25,815 edges.
- The 56,000 synthetic and 137 repository-file cases remain exactly
  equivalent with zero mismatches and semantic SHA-256
  `0a383adb5d4d601b95425a3227f67e99635ba89113c73565ebb4315a3c0b0c9e`.
- Nested prefix regex scans fall 66,377→0 and separately scanned argument
  characters fall 1,256,591→0.
- Focused warning-strict pytest: 6 passed before and after. Full
  warning-strict pytest: 1,451 passed in 326.13 seconds with cache disabled.
- Scoped Ruff/format, repository-wide Ruff `F` checks, `compileall`,
  `git diff --check`, test-diff, package metadata/import/CLI/pip checks all
  pass.
- Wheel SHA-256:
  `a499424d5fe8e2f79d328279a0d23c8156db04f17471e9322f7884dd7630bfaa`.
- Sdist SHA-256:
  `ca38ee498ef3c72e93691694369e93ac50b2d19ecaae0d797ad8311b680b2af8`.
- Canonical source/fresh-wheel prototype SHA-256:
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification replay SHA-256:
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still exits 1 exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Multi-axis review: no findings / APPROVE.
- Evidence:
  `/Users/omar/Documents/Projects/.uidetox-qualification/043.oV387U`.

## Remaining risk and Plan 044 recommendation

Remaining risk is regex-engine variation on adversarial Python text. No live
repository file owns a router prefix, so deterministic synthetic coverage is
the primary semantic/performance proof. Exact repository cases, 56,000
synthetic cases, source timing, and repeated fresh-wheel timing show no
material regression.

Plan 044 should measure the duplicated 15-line session-document traversals in
`list_sessions` and `get_pending_reviews`. Both use the same sorted
`_sessions_dir().iterdir()` traversal, directory/existence gates, JSON load,
exception policy, and append lifecycle; only filename and public owner differ.
Their blast radii reach CLI listing and prompt-safety review generation.
Consider one private loader only if replacing both bodies produces negative
module LOC and lower aggregate cognitive complexity after accounting for the
new function. Preserve arbitrary directory names, lexical order, default text
decoding, malformed-file skips, returned dict identity/order, `meta.json`
versus `review_request.json`, public signatures, and prompt isolation. Stop if
the helper accumulates code, changes error behavior, or merely relocates
complexity.

## STOP conditions

Stop without source integration if:

- factory provenance, code-position filtering, regex boundaries, prefix grammar,
  assignment-first processing, receiver overwrite, mount order/layering,
  dictionary order, or `_join_routes` argument order changes;
- any output dictionary, observation, finding, graph node/edge, ID,
  fingerprint, exception, mutation, or serialized field changes;
- assignment and mount traversals are merged or reordered;
- a helper, module constant, cache, parser, model, index, wrapper,
  compatibility layer, schema, interface, dependency, or second owner is added;
- production LOC, nested scans, cyclomatic complexity, or cognitive complexity
  do not fall;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
