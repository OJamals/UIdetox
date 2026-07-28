# Implementation Plans

Generated and extended by the `improve` skill. Plans 001-012 were generated
against commit `55fc6f3`; plans 013-018 were generated on 2026-07-25 against
commit `d5898c9`; Plan 019 was refreshed on 2026-07-26 against `a97a7ad` after
plans 015-018 landed. Execute in dependency order. Each executor must read its
plan fully, honor STOP conditions, and replace superseded paths instead of
accumulating parallel implementations. Root reviewer owns status updates.

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

## Findings considered and rejected

- Thread-pool/GIL concern: no benchmark showed a regression; Tree-sitter and file I/O may benefit from threads.
- Missing application lockfile: UIdetox is a published library/CLI using compatibility ranges; absence alone is not a defect.
- Root/package-data duplication: 37 source-to-wheel asset pairs were hash-identical and appear intentional.
- `tests/test_regressions.py` size: 788 tests run in roughly 1.5 seconds; size alone has no demonstrated cost.
- Pillow pixel loop: real capture-only micro-hotspot, lower leverage than correctness and coverage work.
- Formatter/linter command execution: commands use argv without `shell=True`; configured local tooling is an intended trust boundary.

## Audit limits

The 2026-07-25 audit was standard and hotspot-weighted. Its unresolved limits
are implementation scope in plan 014:

- qualify all 218 rules with positive/negative expectations;
- verify every bundled provider/design asset against canonical sources;
- add Windows qualification;
- run deterministic live Playwright scenarios;
- smoke-test the installed wheel outside the checkout;
- install and run dependency advisory checks.

Until plan 014 is DONE, capability claims in those areas remain unqualified.
