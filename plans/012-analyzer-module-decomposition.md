# Plan 012: Separate analyzer policy from execution engine

> **Executor instructions**: This is behavior-preserving extraction. Plans 007-011 are
> complete and live symbols match this plan. Preserve the stacked behavior; stop on any
> unexplained finding-count or issue-shape change. Update plan index when done.
>
> **Drift check (run first)**: `git diff --stat 581bf8b..HEAD -- uidetox/analyzer.py uidetox/analyzer_rules.py uidetox/analyzer_ast.py uidetox/analyzer_custom.py uidetox/analyzer_engine.py tests/test_regressions.py`

## Status

- **Priority**: P3
- **Effort**: L
- **Risk**: MED
- **Depends on**: `plans/007-animation-state-token-matching.md`, `plans/008-true-incremental-scan.md`, `plans/009-unified-file-discovery.md`
- **Category**: tech-debt
- **Planned at**: commit `581bf8b`, 2026-07-16

## Why this matters

`uidetox/analyzer.py` is 3,324 lines versus a 172-line median across 42 package Python
modules. A 1,900-line rule catalog, parser setup, a 180-line AST walker, custom
heuristics/registry, per-file dispatch, project color audit, and concurrency share one
high-churn module. Behavior-preserving seams will reduce review scope, conflicts, and
make rule packs/test isolation possible without breaking public imports.

## Current state

- `uidetox/analyzer.py:32-1934`: public `RULES` list, 218 unique IDs.
- `:1947-2126`: `_analyze_ast`, cyclomatic 39/cognitive 140 at audit time.
- `:3004-3160`: custom handlers and registry.
- `:3163-3323`: rule dispatch, file analysis, traversal/concurrency.
- Tests import `RULES`, `analyze_file`, `analyze_directory`, and several private helpers.

Current public facade must remain:

```python
from uidetox.analyzer import RULES, analyze_file, analyze_directory
```

Follow recent commit intent (`refactor: simplify analyzer custom checks`) and use
incremental extractions with full tests after each move.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Baseline | `python -m pytest -q` | all pass before changes |
| Analyzer tests | `python -m pytest -q tests/test_regressions.py -k 'analyz or rule or slop'` | all selected pass after each extraction |
| Import contract | `python -c "from uidetox.analyzer import RULES, analyze_file, analyze_directory; print(len(RULES))"` | prints `218` unless earlier plans intentionally changed catalog |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/analyzer.py`
- `uidetox/analyzer_rules.py` (create)
- `uidetox/analyzer_ast.py` (create)
- `uidetox/analyzer_custom.py` (create)
- `uidetox/analyzer_engine.py` (create)
- `tests/test_regressions.py`

**Out of scope**:
- Changing rule IDs, regexes, tiers, descriptions, commands, thresholds, or issue order.
- Adding plugin/rule-pack APIs.
- Performance changes beyond removing circular/duplicate work caused by extraction.
- Renaming public facade imports.

## Git workflow

- Branch: `codex/012-analyzer-module-decomposition`
- Commit in logical units, e.g. `refactor: extract analyzer rule catalog`, then
  `refactor: extract analyzer AST checks`.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add behavior/contract characterization

Before moving code, add tests asserting 218 unique rule IDs, representative issue
dict equality/order for regex, AST, and custom checks, public imports, unsupported-file
behavior, explicit-target behavior from plan 008, and shared discovery from plan 009.
Create a small fixture corpus under temporary paths; do not commit generated outputs.

**Verify**: analyzer tests and full suite pass before extraction.

### Step 2: Extract rule catalog

Move `RULES` and catalog-only constants to `analyzer_rules.py`. Keep compiled regexes
and list order byte-for-byte equivalent. Re-export `RULES` from `analyzer.py`. Do not
introduce a new dataclass/schema in this step.

**Verify**: import contract prints expected count; catalog fingerprints/order tests pass.

### Step 3: Extract AST support

Move Tree-sitter imports, `HAS_AST`, `_get_parser`, and `_analyze_ast` plus only their
private dependencies to `analyzer_ast.py`. Re-export private names currently imported
by tests for compatibility. Corrected token behavior from plan 007 must move unchanged.

**Verify**: all AST tests pass; missing-parser fallback contract unchanged.

### Step 4: Extract custom handlers and registry

Move custom-check functions and handler registry to `analyzer_custom.py`. Avoid circular
imports by passing rule/file/content/context explicitly and keeping shared pure helpers
in the narrowest owner. Preserve handler lookup keys and `None`/list return semantics.

**Verify**: custom-rule tests pass with issue equality, not only counts.

### Step 5: Extract execution engine

Move per-rule dispatch, `analyze_file`, and directory/explicit-target analysis to
`analyzer_engine.py`. Consume plan 009 file-set API. Keep `analyzer.py` as compatibility
facade importing/re-exporting public and tested-private symbols.

**Verify**: full suite passes; facade import contract unchanged.

### Step 6: Audit dependency direction and file size

Required direction: rules/AST/custom/fileset → engine → facade. No extracted module
may import facade. Remove dead imports and confirm no cycle using a small import test.

**Verify**: `python -c "import uidetox.analyzer, uidetox.analyzer_engine, uidetox.analyzer_ast, uidetox.analyzer_custom"` → exit 0; `analyzer.py` is a compact facade.

## Test plan

- Catalog uniqueness/order/fingerprint.
- Representative exact issue dicts from regex, AST, custom handlers.
- Public and compatibility-private imports.
- Unsupported extensions and missing parser.
- Full and incremental discovery/ordering.
- Full suite after every extraction commit.

## Done criteria

- [ ] `analyzer.py` is a compatibility facade, not implementation monolith.
- [ ] Rule/AST/custom/engine dependencies are acyclic.
- [ ] Public imports and issue ordering unchanged.
- [ ] No rule catalog semantic diff.
- [ ] Full suite passes after each logical extraction.
- [ ] Plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Plans 007, 008, or 009 are incomplete.
- Baseline full suite is not green.
- Any extraction changes finding count/order/shape on fixture corpus.
- Avoiding a cycle requires changing public API or rule semantics.
- Live analyzer structure differs materially from post-dependency assumptions.

## Maintenance notes

Future rules belong in catalog; AST-only work in AST module; custom handler families in
custom module; traversal/concurrency in engine. A later plugin SDK should build on these
seams but remains separate product work.
