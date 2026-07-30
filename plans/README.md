# Implementation Plans

Generated and extended by the `improve` skill. Plans 001-012 were generated
against commit `55fc6f3`; plans 013-018 were generated on 2026-07-25 against
commit `d5898c9`; Plan 019 was refreshed on 2026-07-26 against `a97a7ad` after
plans 015-018 landed. Execute in dependency order. Each executor must read its
plan fully, honor STOP conditions, and replace superseded paths instead of
accumulating parallel implementations. Root reviewer owns status updates.
Plans 050-056 were generated on 2026-07-30 against `8bfd929` from the
non-security application correctness and performance audit. Security issues
14 and 15 are explicitly deferred and excluded from these plans.

## Execution order and status

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 001 | Establish reproducible contributor verification | P1 | M | — | DONE |
| 002 | Isolate repository data from agent instructions | P1 | M | 001 | DONE |
| 003 | Gate PyPI publication on verification | P1 | S | 001 | DONE |
| 004 | Batch scan queue persistence | P1 | M | 001 | DONE |
| 005 | Emit standalone machine-readable scan output | P1 | S | 001 | DONE |
| 006 | Report mechanical auto-commit failures | P1 | S | 001 | DONE |
| 007 | Eliminate animation-state substring false positives | P1 | S | 001 | DONE |
| 008 | Make `scan --since` truly incremental | P1 | M | 001 | DONE |
| 009 | Unify frontend file discovery and exclusions | P2 | M | 008 | DONE |
| 010 | Split optional capability dependencies into extras | P2 | S | 001 | DONE |
| 011 | Characterize the capture and visual-diff pipeline | P2 | M | 010 | DONE |
| 012 | Separate analyzer policy from execution engine | P3 | L | 007, 008, 009 | DONE |
| 013 | Secure repository evidence before persistence or agent injection | P0 | M | — | DONE |
| 014 | Make every capability claim executable and measurable | P0 | L | — | DONE |
| 015 | Replace fragmented issue handling with verified finding lifecycle | P0 | L | 013, 014 | DONE — reviewed at `ee2d410`; 1,282 tests pass |
| 016 | Replace shallow extraction with adapter-driven application semantics | P1 | L | 014 | DONE |
| 017 | Replace route parity with typed full-stack contract lineage | P1 | L | 015, 016 | DONE — reviewed at `d0ec3b0`; 1,340 tests pass |
| 018 | Replace initial-frame capture with efficient scenario observation | P1 | L | 015, 016 | DONE — reviewed at `43596ae`; 1,376 tests pass |
| 019 | Replace guessed color checks with semantic design-quality evidence | P1 | L | 015, 016, 018 | DONE — merged as `591f306`; post-integration review clean; 1,396 tests pass |
| 020 | Reproducible runtime-performance qualification and semantic hardening | P1 | M | 019 | DONE — merged as `8bda5d4`; 1,412 tests pass; generic ≤+1.15%, controls improved, geometry ≥30.72% faster |
| 021 | Source-scope contract evidence and bound agent handoffs | P1 | M | 017, 019, 020 | DONE — 1,416 tests pass; prototype -84.28%; no all-to-all evidence |
| 022 | End-to-end disposable-agent handoff qualification | P1 | M | 021 | DONE — 1,407 tests pass; 94/94 contracts and 3/3 viewports preserved |
| 023 | Deterministic handoff qualification schema and runner | P1 | M | 022 | DONE |
| 024 | Disposable-agent handoff repeatability matrix | P1 | M | 023 | DONE — 3/3 fresh agents pass; 1.0 accuracy; 1,425 tests; production LOC ±0 |
| 025 | Prototype qualification contract and runtime-state handoff | P1 | M | 024 | DONE — 4/4 states and 3/3 viewports preserved; 1,425 tests; v1 contract emitted |
| 026 | Deterministic v1 report validation and executable state qualification | P1 | M | 025 | DONE — 4/4 states; 1.0 accuracy; 1,440 tests; production +32 LOC |
| 027 | Canonical runtime capture identity | P1 | S | 026 | DONE — 1,443 tests; production -1 LOC; graph 6,031/25,164 |
| 028 | Runtime capture uniqueness and redirect semantics | P1 | S | 027 | DONE |
| 029 | Runtime observation completeness and status derivation | P1 | S | 028 | DONE — 1,451 tests; production -1 LOC; graph 6,027/25,673 |
| 030 | Runtime coverage projection consolidation | P1 | S | 029 | DONE — 1,451 tests; production -2 LOC; graph 6,027/25,725 |
| 031 | Source-fact attribution scan consolidation | P1 | S | 030 | DONE — 1,451 tests; production -3 LOC; cognitive 75→72; graph 6,027/25,725 |
| 032 | Pyproject dependency normalization | P1 | S | 031 | DONE — 1,451 tests; production -7 LOC; cognitive 91→27; graph 6,027/25,737 |
| 033 | Autofix transform batch consolidation | P1 | S | 032 | DONE — 1,451 tests; production -10 LOC; cognitive 95→89; graph 6,027/25,764 |
| 034 | Capture evidence orchestration consolidation | P1 | S | 033 | DONE — 1,451 tests; production -14 LOC; cognitive 107→86; graph 6,027/25,769 |
| 035 | Watch snapshot-delta consolidation | P1 | S | 034 | DONE — 1,451 tests; production -5 LOC; cognitive 32→25; graph 6,027/25,784 |
| 036 | Detect tool-list rendering consolidation | P1 | S | 035 | DONE — 1,451 tests; production -4 LOC; cognitive 20→12; graph 6,027/25,789 |
| 037 | History summary selection simplification | P1 | S | 036 | DONE — 1,451 tests; production -7 LOC/-2 functions; graph 6,025/25,788 |
| 038 | Show grouped issue scan consolidation | P1 | S | 037 | DONE — 1,451 tests; production -2 LOC; loops 5→4; graph 6,025/25,802 |
| 039 | Relevant-context fallback scan short-circuit | P1 | S | 038 | DONE — 1,451 tests; production -3 LOC; live scans -25.6%; graph 6,025/25,809 |
| 040 | Submit-binding direct scan consolidation | P1 | S | 039 | DONE — 1,451 tests; production -4 LOC; cognitive 7→4; loop scans 3→2; graph 6,025/25,813 |
| 041 | JavaScript comment-mask branch consolidation | P1 | S | 040 | DONE — 1,451 tests; production -4 LOC; cognitive 18→16; scan sites 2→1; graph 6,025/25,808 |
| 042 | Semantic class-state search consolidation | P1 | S | 041 | DONE |
| 043 | Python receiver-prefix scan consolidation | P1 | S | 042 | DONE |
| 044 | Session-document loader consolidation | P1 | S | 043 | DONE — 1,451 tests; production -9 LOC; cognitive 24→10; loaders 2→1; graph 6,026/25,813 |
| 045 | Session-memory entry normalizer consolidation | P1 | S | 044 | DONE — 1,451 tests; production -5 LOC/-1 function; cognitive 18→10; graph 6,024/25,804 |
| 046 | Visual file-hash consolidation | P1 | S | 045 | DONE — 1,451 tests; production -8 LOC/-1 function; cognitive 6→3; graph 6,023/25,804 |
| 047 | Persisted-artifact loader consolidation | P1 | S | 046 | DONE — 1,466 tests; production -4 LOC; cognitive 12→6; graph 6,059/26,447 |
| 048 | Private collection-normalizer consolidation | P1 | S | 047 | DONE — 1,451 tests; production -5 LOC/-1 function; cognitive 8→4; graph 6,022/25,816 |
| 049 | Capped memory-entry persistence consolidation | P1 | S | 047, 048 | DONE — 1,466 tests; production -3 LOC; lifecycle sites 4→1; multi-writer loss fixed; graph 6,059/26,447 |
| 050 | Emit JSON-safe canonical evidence projections | P1 | M | — | DONE — reviewed at `2c61550`; 1,471 tests pass; production +14 LOC |
| 051 | Bound and consolidate mechanical command execution | P1 | S | — | DONE — independently reviewed at `fd1c060`; 1,480 tests pass; production +7 LOC; duplicate fix runners 2→0 |
| 052 | Finalize session branches outside the user worktree | P1 | M | — | DONE — independently reviewed at `29ad66c`; 1,480 tests pass; production +321 LOC; destructive original-worktree finalize path removed |
| 053 | Fail closed and delete dead CLI paths | P1 | M | 051 | DONE — independently reviewed at `ab867cc`; 1,500 tests pass; production plus shipped assets -52 LOC; dead CLI flags and paths removed |
| 054 | Consolidate atomic artifact replacement | P1 | M | 050 | DONE — independently reviewed; 1,484 tests pass; production plus shipped assets -1 LOC; text replacement lifecycles 5→1 |
| 055 | Separate backend source discovery from extraction | P1 | M | — | DONE — independently reviewed at `aa4210e`; 1,474 tests pass; 3.49x manifest speedup; route extractors 65→0 |
| 056 | Precompute static-scan semantic facts | P1 | L | — | DONE — independently reviewed at `e5a64ac`; 1,476 tests pass; 2.32x/2.43x speedup; nested-selector parity preserved |

Status values: TODO | IN PROGRESS | DONE | BLOCKED (with reason) | REJECTED (with rationale)

## Dependency notes

- 001 establishes the canonical environment and test gate required by every code plan.
- 003 consumes the contributor command created by 001 instead of inventing a second CI-only gate.
- 009 follows 008 because both change scan target discovery; doing 009 first would create avoidable churn.
- 011 follows 010 so capture tests install and exercise the new `capture` extra.
- 012 runs after 007, 008, and 009 because each changes code that 012 will relocate.
- 013 and 014 can run in parallel. They establish the trust boundary and
  qualification baseline required by later architectural work.
- 015 depends on 013 because every finding must be sanitized before persistence,
  and on 014 because lifecycle/scoring changes need calibrated behavior.
- 016 depends on 014 because new framework/client adapters must prove native,
  degraded, and unsupported behavior.
- 017 depends on 015 and 016 so contract lineage reuses the canonical finding
  lifecycle and semantic adapters instead of creating parallel models/parsers.
- 018 depends on 015 and 016 so scenario findings are lifecycle-aware and
  source-owned.
- 019 depends on 015 and 018 so design-quality findings consume one evidence
  graph and one cached runtime measurement path.
- 050 lands before 054 so capture/runtime payloads are demonstrably JSON-safe
  before persistence lifecycles are consolidated.
- 051 lands before 053 so the CLI result contract consumes one bounded
  mechanical execution policy.
- 052 is independent but should land before lower-risk performance work because
  it removes a user-worktree mutation hazard.
- 053 must not start until active changes in `loop.py`, `state.py`,
  `workflow.py`, and their tests are integrated or cleared by their owner.
- 054 must not start until active `state.py` persistence changes are integrated
  and the code graph is refreshed.
- 055 and 056 are independent of each other. Run them after correctness and
  lifecycle plans; both have strict parity gates and high false-negative risk.

## Cleanup contract for plans 013-019

- Replace before adding: move callers, then delete superseded implementations
  in the same plan.
- No parallel issue lifecycle, parser registry, contract graph, runtime
  observer, score, or design evidence system.
- Reuse existing fixtures, parser caches, semantic maps, runtime measurements,
  and workflow state.
- Every executor reports production-code line delta, deleted symbols/files, and
  any unavoidable net growth.
- New capability code must be offset by deleting stale/orphaned/duplicate
  helpers where feasible. Tests, fixtures, and migration readers are excluded
  from the production-code reduction target but must still avoid duplication.

## Cleanup contract for plans 050-056

- Fix the shared owning seam, not individual symptoms.
- Replace before deleting callers; delete displaced implementations in the
  same plan. No compatibility wrapper may survive merely to preserve dead
  behavior.
- Preserve canonical finding, runtime, map, and analyzer models. No second
  schema, graph, cache, parser, persistence layer, or result hierarchy.
- Plans 053 and 054 must finish with net-negative production plus shipped-asset
  LOC. Plans 050-052, 055, and 056 must report LOC and deleted-symbol deltas and
  justify any unavoidable growth.
- Every performance change requires exact ordered semantic parity plus a
  reproducible relative benchmark. Speed gained by skipping files, rules,
  invalidation, or verification is failure.
- Every executor must report focused/full test results, exact files changed,
  production LOC delta, and removed stale/duplicate symbols.

## Source findings

- Plan 050: GitHub issues 3 and 4.
- Plan 051: GitHub issue 8.
- Plan 052: GitHub issue 9.
- Plan 053: GitHub issues 5, 6, 7, and 10.
- Plan 054: GitHub issue 11.
- Plan 055: GitHub issue 12.
- Plan 056: GitHub issue 13.

## Deferred by maintainer

- GitHub issue 14: project-authored content entering agent instructions.
- GitHub issue 15: runtime URL credentials/query values in evidence artifacts.

These security issues remain open, but no implementation plan or source change
for them belongs in the current application/optimization sequence.

## Findings considered and rejected

- Thread-pool/GIL concern: no benchmark showed a regression; Tree-sitter and file I/O may benefit from threads.
- Missing application lockfile: UIdetox is a published library/CLI using compatibility ranges; absence alone is not a defect.
- Root/package-data duplication: 37 source-to-wheel asset pairs were hash-identical and appear intentional.
- `tests/test_regressions.py` size: 788 tests run in roughly 1.5 seconds; size alone has no demonstrated cost.
- Pillow pixel loop: real capture-only micro-hotspot, lower leverage than correctness and coverage work.
- Formatter/linter command execution: commands use argv without `shell=True`; configured local tooling is an intended trust boundary.
- Raw Ruff output: Ruff is not the configured project gate; its unbaselined
  output is not a valid cleanup backlog.
- Local `pip` advisory: it affects the development environment's installer,
  not a declared UIdetox production dependency.
- Thread-pool removal: sequential execution was not faster after semantic
  precomputation; keep concurrency and remove repeated semantic work.
- New plugin/provider runner: no validated workflow need justifies another
  subsystem.

## Audit limits

The 2026-07-29/30 audit was whole-repository and live for the root package:
1,473 warning-strict tests, 15 browser tests, 13 calibration tests, 12
release/update-skill tests, all 53 help surfaces, runtime map, watch, capture,
and visual-evidence paths.

Current limits:

- `examples/fullstack-slop-lab` backend/frontend dependencies were not
  materialized, so its API, production build, and Playwright suite were not
  requalified in this audit.
- Live qualification ran on macOS; existing release automation owns
  cross-platform/wheel gates.
- Plan 055 and Plan 056 speedups came from controlled runtime prototypes.
  Their committed benchmark scripts and parity gates are implementation work,
  not yet repository guarantees.
