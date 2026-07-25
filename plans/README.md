# Implementation Plans

Generated and extended by the `improve` skill. Plans 001-012 were generated
against commit `55fc6f3`; plans 013-019 were generated on 2026-07-25 against
commit `d5898c9`. Execute in dependency order. Each executor must read its plan
fully, honor STOP conditions, replace superseded paths instead of accumulating
parallel implementations, and update its status row.

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
| 013 | Secure repository evidence before persistence or agent injection | P0 | M | — | TODO |
| 014 | Make every capability claim executable and measurable | P0 | L | — | TODO |
| 015 | Replace fragmented issue handling with verified finding lifecycle | P0 | L | 013, 014 | TODO |
| 016 | Replace shallow extraction with adapter-driven application semantics | P1 | L | 014 | TODO |
| 017 | Replace route parity with typed full-stack contract lineage | P1 | L | 015, 016 | TODO |
| 018 | Replace initial-frame capture with efficient scenario observation | P1 | L | 015, 016 | TODO |
| 019 | Replace guessed color checks with semantic design-quality evidence | P1 | L | 015, 018 | TODO |

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
