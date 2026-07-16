# Plan 007: Eliminate animation-state substring false positives

> **Executor instructions**: Change only AST animation-state classification. Preserve
> all other analyzer rules and issue schema. Update plan index after full verification.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- uidetox/analyzer.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: bug
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

AST classification checks raw declaration text for one-character substrings `x` and
`y`. Ordinary state such as `query`, `story`, `text`, or `country` therefore triggers
`ANIMATE_STATE_SLOP`. False T2 findings reduce trust in UIdetox's core analyzer and
can prompt unnecessary rewrites.

## Current state

```python
# uidetox/analyzer.py:2022-2028
animation_signals = ["opacity", "scale", "translate", "rotate", "transform",
                     "position", "top", "left", "right", "bottom",
                     "animat", "transit", "x", "y"]
for sig in animation_signals:
    if sig in text_lower and "useState" in text:
        state["usestate_for_animation"] = True
```

`tests/test_regressions.py:5373-5389` provides one positive `opacity` fixture. Match
existing analyzer issue dictionaries and tempfile cleanup style.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_regressions.py -k 'animate_state'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/analyzer.py`
- `tests/test_regressions.py`

**Out of scope**:
- Changing issue ID, tier, copy, or remediation command.
- Rewriting `_analyze_ast` wholesale.
- Detecting runtime animation performance beyond `useState` declarations.
- Moving analyzer modules; plan 012 owns extraction.

## Git workflow

- Branch: `codex/007-animation-state-token-matching`
- Commit: `fix: match animation state by identifier tokens`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Extract the declared state identifier

Add a small private helper that accepts declaration text and returns the first state
binding from a standard destructured `useState` assignment. Use a bounded regex or
Tree-sitter child traversal; do not inspect setter/body text because that reintroduces
noise. Return `None` for nonstandard/unparseable declarations.

**Verify**: helper tests cover `opacity`, `translateX`, `x`, `query`, and unrelated declarations.

### Step 2: Tokenize identifier semantics

Split snake_case, kebab-like separators, digits, and camel/Pascal case into lowercase
tokens. Match full tokens for `x`, `y`, `top`, `left`, `right`, `bottom`, `opacity`,
`scale`, `rotate`, `position`, `transform`; accept prefixes `animat*`, `transit*`, and
`translate*`. Never run raw one-character substring checks.

**Verify**: exact `x`/`y` and `translateX` remain positive; `query`, `story`, `text`,
`country`, `display`, and `ready` remain negative.

### Step 3: Integrate helper without changing other AST flow

Replace current signal loop inside `lexical_declaration`. Preserve parser fallback,
walk recursion, and emitted issue shape.

**Verify**: targeted then full tests pass.

## Test plan

- Positive: `opacity`, `scale`, `translateX`, exact `x`, exact `y`, `animationProgress`.
- Negative: `query`, `story`, `text`, `country`, `ready`, `userProfile`.
- Multiple declarations: only qualifying binding triggers one file-level issue.
- Existing ID-field test stays green.

## Done criteria

- [ ] No raw `sig in text_lower` check for one-character signals remains.
- [ ] Positive and negative fixtures pass.
- [ ] Issue shape unchanged.
- [ ] Full suite passes.
- [ ] Plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Installed Tree-sitter grammar does not expose declaration text consistently.
- Supporting required syntax needs a general JavaScript parser rewrite.
- Existing tests establish substring matching as intentional.
- Fix changes any non-animation analyzer finding.

## Maintenance notes

Keep signals centralized and tested pairwise for positive/negative identifiers. Execute
this plan before analyzer module extraction so plan 012 moves corrected behavior.
