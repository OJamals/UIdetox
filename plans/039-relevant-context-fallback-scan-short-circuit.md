# Plan 039: Relevant-context fallback scan short-circuit

## Status

DONE

## Magic moment

`uidetox next` and subagent fix prompts preserve exact rule/context bytes while
the existing first-seen context owner short-circuits already-routed fallback
contexts before later regex scans.

## Live baseline

Measured on 2026-07-28 before production changes:

- `HEAD`, `master`, `origin/master`, and remote `refs/heads/master` are
  identical at `d384ec7ee3bb1613938922aa6250447c506fc760`;
- root is clean; one worktree; only `master` exists locally/remotely;
- Plan 015/016 archival stashes remain
  `200608c499cd4e2ca509d0a32be1b3f376dbdef2` and
  `047d61901a7a85fdee06fb9eb984f6b8a85efbad`;
- no UIdetox pytest, qualification, Playwright, or Chromium workload runs;
- Plan 038 is DONE; Plan 039 did not exist;
- graph alias `Users-omar-Documents-Projects-UIdetox-uidetox` contains
  6,025 nodes and 25,802 edges and is bound to Plan 038 source commit
  `6d1d3771a9bb4c82065f8524e9d009d938abf770`;
- `uidetox.commands.next._get_relevant_context` has CRITICAL blast radius
  through `next.run`, `subagent._fix_prompt`, generated stage prompts,
  prompt-safety tests, and rule-registry tests;
- graph metrics are 29 lines, cyclomatic complexity 7, cognitive complexity
  19, 3 loops, loop depth 2, one hidden linear scan in a loop, and two
  loop-local allocations;
- `next.py` contains 897 lines and 8 functions;
- production contains 40,074 lines, 979 functions, and 132 classes/models
  across 83 Python files;
- focused warning-strict rule/prompt baseline passes 27 tests with cache
  disabled;
- Plan 038's full warning-strict baseline remains 1,451 passing tests.

## Measured distributions and work

Canonical owners:

- `SKILL_CONTEXT` owns 145 insertion-ordered keyword-to-context/reference
  entries;
- all 145 context snippets are unique in the current table;
- `RULE_REGISTRY` owns 217 immutable `RuleSpec` records;
- each rule routes through 3–4 context keys (median 4);
- every registry context key resolves in `SKILL_CONTEXT`;
- exact rule IDs perform no fallback regex scan;
- unknown/manual issue IDs intentionally use token-boundary fallback matching.

The live normalized queue contains 214 unknown/manual `SCAN-*` issues. Its
selected `src` batch contains 12 issues in one file:

| Workload | Issues | Known | Unknown | Current regex/escape scans | Contexts |
| --- | ---: | ---: | ---: | ---: | ---: |
| Selected batch | 12 | 0 | 12 | 1,740 | 14 |
| Live queue | 214 | 0 | 214 | 31,030 | 52 |
| Repeated representative | 1,000 | 0 | 1,000 | 145,000 | 4 |

Current fallback traversal tests all 145 keywords for every unknown issue,
even after a context snippet has already won first-seen deduplication.
Checking the existing dedup owner before regex evaluation preserves output
while reducing deterministic scans to:

| Workload | Proposed scans | Removed scans | Reduction |
| --- | ---: | ---: | ---: |
| Selected batch | 1,661 | 79 | 4.5% |
| Live queue | 23,075 | 7,955 | 25.6% |
| Repeated representative | 141,004 | 3,996 | 2.8% |

Per-issue fallback traversal remains intentional attribution: issue order must
precede keyword order so the first matching issue determines output order.
Only scans for contexts already present in the dedup owner are redundant.

## Frozen behavior and boundaries

Preserve exactly:

- `get_rule(issue.get("id"))` remains exact-rule authority;
- exact rule IDs route only `RuleSpec.context_keys` and never description
  guesses;
- unknown, manual, empty, and falsey IDs use fallback matching;
- fallback description remains lowercased `issue + " " + command`;
- ASCII token boundaries remain
  `(?<![A-Za-z0-9_])... (?![A-Za-z0-9_])`;
- keywords remain escaped literally, including punctuation and multiword keys;
- issue order precedes `SKILL_CONTEXT` insertion order;
- context snippets deduplicate by exact snippet string, not keyword or
  reference path;
- the first routed occurrence owns order and reference path;
- missing registry context keys are ignored;
- reference `None` remains valid;
- duplicate issues, duplicate keys across issues, malformed input errors, and
  zero input mutation remain unchanged;
- returned type remains `list[tuple[str, str | None]]`;
- `next.run` SKILL.md block, deep-dive paths, blank lines, ANSI/text bytes, and
  agent instructions remain unchanged;
- `subagent._fix_prompt` context order, bullet bytes, deep-dive paths,
  prompt-safety isolation, and codebase-memory guidance remain unchanged;
- rule registry, analyzer catalog, finding lifecycle, state, scan, review,
  workflow, map, redesign, prototype, qualification, and serialization remain
  unchanged.

`seen_snippets` owns deduplication while `contexts` owns the public ordered
return shape. Both remain ephemeral and local. Measurement rejects replacing
them with one ordered mapping because that slows the exact-rule path. The safe
change only moves the existing ownership check before fallback regex work.

## History and architecture

- `a3a2d0e` introduced issue-order then keyword-order context matching and
  first-seen deduplication.
- `74564a8` attached reference paths while preserving snippet-based
  first-occurrence semantics.
- `e4384e8` introduced exact rule-ID-first routing, guarded missing context
  keys, and ASCII token-boundary fallback to prevent substring guesses such as
  `any` inside `company`.
- `RULE_REGISTRY` and `_CATEGORY_CONTEXT` already own exact routing.
  `SKILL_CONTEXT` already owns fallback keyword order and context provenance.
- The regex scan cannot move outside the issue loop without changing
  first-occurrence ordering. A compiled-pattern cache or reverse context index
  would create a second owner and is rejected.
- An ordered-dictionary replacement produced identical output and improved the
  live manual queue, but slowed 1,000 exact-rule issues by 14.2% and empty
  calls by 63.3%. It is rejected rather than accumulating a nominally cleaner
  structure that regresses a canonical path.
- Preserving the current set/list owners keeps exact-rule execution unchanged.
  Short-circuiting set membership before fallback matching removes only work
  whose result cannot affect output.

## Exact differential evidence

An external probe freezes:

- empty input;
- exact rule-ID routing with opaque descriptions;
- exact routing preemption over unrelated fallback keywords;
- unknown/manual fallback matches;
- ASCII token-boundary matches and non-matches;
- punctuation, underscore, digit, and multiword keys;
- issue order and keyword insertion order;
- duplicate issues and exact/fallback deduplication;
- first reference-path ownership;
- missing registry context-key tolerance;
- malformed input exception type/message;
- zero input mutation;
- exact `next.run` output bytes under controlled state/config/memory;
- exact `subagent._fix_prompt` bytes under controlled memory/deconfliction;
- live/selected regex and escape call counts.

The semantic SHA must remain identical. Tests remain unchanged because this is
a pure refactor; external differential evidence measures behavior and work.

Baseline evidence:

- 14-case semantic SHA-256:
  `1db51522f7a94fab3269d79e92033d18976a0cf93df51a79aaf20264ec0d807b`;
- controlled subagent fix-prompt SHA-256:
  `642a8d995832572825445f55515e21db4a5f75cc3851ae49332c08f95274583d`;
- controlled `next.run` output SHA-256:
  `a3a2b505d8440915cb877af1876a2d354e4e4971a5dd25c0c58f5b94b8421ae1`;
- 16,952 canonical bytes, zero mutated cases;
- accepted candidate median ratios: 1.0000 empty, 0.9899 exact-rule 1,000,
  0.9761 selected manual batch, 0.7690 live manual queue, and 0.9721 repeated
  manual 1,000.

## Rejected experiment

The measured ordered-dictionary consolidation produced these median
candidate/baseline ratios:

| Workload | Ratio | Verdict |
| --- | ---: | --- |
| Empty | 1.6328 | reject |
| 1,000 exact-rule issues | 1.1416 | reject |
| Selected manual batch | 0.9738 | improves |
| Live manual queue | 0.7728 | improves |
| 1,000 repeated manual issues | 0.9992 | neutral |

The exact path performs no regex work and is a canonical registry route. Its
regression is not offset by live fallback gains. A second dict variant reduced
the exact regression to 3.3% but retained the same control complexity, so it
was also rejected.

## Architecture decision

- Preserve `seen_snippets` and `contexts`; they own distinct deduplication and
  return-shape contracts.
- In fallback matching, check `context not in seen_snippets` before invoking
  `re.search`.
- Inline the search result into that condition and delete the temporary
  `matched` value.
- Leave exact-rule routing byte-for-byte unchanged.
- Add no function, helper, type, model, enum, cache, regex registry, reverse
  index, graph, wrapper, facade, adapter, fallback, schema, field, dependency,
  or public interface.
- Keep only if production LOC falls, graph complexity does not increase,
  deterministic regex scans fall, exact bytes remain identical, the exact
  route remains timing-neutral, and controlled fallback timing does not
  materially regress.

## Tasks

### Task 1: Freeze contracts

- [x] Rebaseline Git, refs, worktree, branches, stashes, processes, graph, and
      remote parity.
- [x] Trace CRITICAL callers and inspect exact target/caller/data flow.
- [x] Inspect registry/context owners, tests, Git history, and blame.
- [x] Measure live/selected/representative distributions and scan work.
- [x] Pass focused warning-strict tests before edits.
- [x] Record exact differential and timing baselines.

### Task 2: Short-circuit redundant fallback scans

- [x] Preserve set/list ownership and exact-route execution.
- [x] Short-circuit already-owned fallback contexts before regex evaluation.
- [x] Preserve exact route/fallback/order/reference/error semantics.
- [x] Reduce production LOC and scan work without a new symbol or model.
- [x] Keep tests unchanged.

### Task 3: Verify repository/package/artifact boundaries

- [x] Pass exact HEAD-versus-working-tree behavioral equivalence.
- [x] Prove live fallback scans fall 31,030 -> 23,075.
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
- [x] Record exact metrics, hashes, removed code, remaining risk, and Plan 040
      recommendation.
- [x] Commit Plan 039/index, push `master`, and prove local/origin/server parity.
- [x] Preserve clean root, one worktree, archival stashes, and zero UIdetox
      workloads.
- [x] Perform no release, tag, or PyPI action.

## Execution results

- Source commit:
  `9a18248c4c20132f04799a8ae64e593ef470b058`.
- Graph refresh commit:
  `3cd890e8c4e8288a6ecc5e29690fd2bcfbabd391`.
- Production delta is +4/-7, net -3 lines. `next.py` falls 897 -> 894
  lines; production falls 40,074 -> 40,071 lines.
- Production symbols remain 979 functions and 132 classes/models across 83
  Python files. No test changed.
- `_get_relevant_context` falls 29 -> 28 lines. Cyclomatic complexity 7,
  cognitive complexity 19, 3 loops, loop depth 2, one graph-reported hidden
  scan, and two loop-local allocations remain unchanged. Deterministic regex
  work falls because the graph metric cannot distinguish the new guard.
- Refreshed canonical graph contains 6,025 nodes and 25,809 edges and is bound
  to source commit `9a18248c4c20132f04799a8ae64e593ef470b058`.
- Selected/live/repeated fallback scans fall 1,740 -> 1,661,
  31,030 -> 23,075, and 145,000 -> 141,004.
- Post-change median candidate/baseline timing ratios are 0.9076 empty,
  0.9517 exact-rule 1,000, 0.9671 selected manual batch, 0.7366 live manual
  queue, and 0.9577 repeated manual 1,000. No workload regresses.
- Source and fresh-installed differential probes preserve all 14 cases,
  16,952 canonical bytes, zero input mutations, semantic SHA-256
  `1db51522f7a94fab3269d79e92033d18976a0cf93df51a79aaf20264ec0d807b`,
  fix-prompt SHA-256
  `642a8d995832572825445f55515e21db4a5f75cc3851ae49332c08f95274583d`,
  and `next.run` SHA-256
  `a3a2b505d8440915cb877af1876a2d354e4e4971a5dd25c0c58f5b94b8421ae1`.
- Focused warning-strict pytest passes 27 tests before and after. Full
  warning-strict pytest passes 1,451 tests in 76.36 seconds with cache
  disabled.
- Scoped Ruff `F,I`, target formatting, repository-wide Ruff `F`,
  `compileall`, package imports, CLI smokes, `pip check`, and
  `git diff --check` pass. Broad target Ruff still reports the pre-existing
  `S110`/`BLE001` broad exception and 150 long prompt-literal `E501` findings;
  Plan 039 does not expand into that unrelated sweep.
- Wheel SHA-256:
  `c7dbaf906dd66df9083c4d21d489af67e783d9e2a1eefae63efb7c0dcd86c11c`.
- Sdist SHA-256:
  `18c85bb44e7dfbea9f857c824db18e5fefc9ca64915d0a1e454ed9705906fc93`.
- Source and fresh-installed canonical prototype SHA-256 remains
  `4b7e2695fca88d84031866f5a5c608e61a801771de169528efe983069351a068`.
- Canonical qualification SHA-256 remains
  `902b4a5dee14fbe25cf5830c48cf15880bf196b8b2a9ef315d80e05afb3fe70f`.
- Historical Plan 025 still fails exactly with
  `Runtime capture identity is not executable: expected
  'qualification:authenticated:mobile:9160ab53a1f6', got
  'qualification-authenticated'.`
- Multi-axis correctness, readability, architecture, security, and
  performance review reports no findings: APPROVE.
- Evidence is preserved at
  `/Users/omar/Documents/Projects/.uidetox-qualification/039.XU3T33`.
- No release, tag, PyPI action, archived-stash mutation, or qualification
  artifact rewrite occurred.

Removed code is the fallback `matched` temporary and its second condition.
The existing set/list owners, registry lookup, description construction,
token-boundary regex, output order, provenance, reference ownership, prompt
rendering, serialization, and all public interfaces remain unchanged.

## Remaining risk

The fallback remains intentionally O(issues x keywords). It must preserve
issue-first attribution, so Plan 039 removes only scans whose context snippet
is already owned. Future duplicate snippets or runtime mutation of
`SKILL_CONTEXT` remain governed by exact snippet first occurrence; moving the
guard after search or indexing keywords separately could change that contract.

## Plan 040 recommendation

Measure `_has_submit_binding` in `uidetox/analyzer_project.py`. It has CRITICAL
blast radius and graph-reports three searches inside its selector loop.
Evaluate consolidating only the repeated direct
`getElementById`/`querySelector` submit-listener search. Preserve selector
kind, quote backreferences, whitespace, case-insensitive matching, first
assignment per selector, suffix-only variable binding, false/true outputs,
issue order, and finding bytes. Do not replace the current first-assignment
semantics with `finditer`, add a regex cache/helper/index/model, or accept
production/code-complexity growth. Stop if exact differential evidence,
negative LOC, reduced scan work, and unchanged canonical artifacts cannot all
hold.

## STOP conditions

Stop without source integration if:

- exact-rule-first or token-boundary fallback semantics change;
- issue order, keyword order, snippet deduplication, first reference ownership,
  prompt bytes, exception behavior, or input mutation changes;
- fallback traversal moves outside issue order;
- consolidation replaces the exact-path set/list owners or adds a
  compiled-pattern cache, index/model, helper, wrapper,
  compatibility layer, schema, interface, dependency, or second owner;
- production LOC does not fall or graph complexity increases;
- deterministic regex scans do not fall;
- controlled timing materially regresses;
- tests must change;
- package/canonical/historical gates change;
- archived stashes or qualification artifacts require mutation;
- any unexplained or contested gate remains.
