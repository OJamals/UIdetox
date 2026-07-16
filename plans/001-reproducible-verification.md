# Plan 001: Establish reproducible contributor verification

> **Executor instructions**: Follow this plan step by step. Run every verification
> command and confirm the expected result before moving on. Stop on any condition
> listed below; do not improvise. When done, update this plan's row in
> `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- pyproject.toml README.md tests/conftest.py`
> If live code no longer matches the excerpts below, stop and report drift.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

Current checkout has no documented contributor install or canonical verification
gate. In the audit environment, `python -m pytest -q` ran 788 tests but failed two
AST assertions because the ambient interpreter lacked declared Tree-sitter
dependencies. Contributors and agents need one explicit setup path that installs
runtime plus test dependencies and fails early when core AST support is absent.

## Current state

- `pyproject.toml:27-36` declares runtime dependencies but no `dev` extra or pytest configuration.
- `README.md:33-60` documents end-user `pip install uidetox`, not contributor setup.
- `uidetox/analyzer.py:18-29` converts missing Tree-sitter imports into `HAS_AST = False`.
- `tests/test_regressions.py:5318-5339` and `:5373-5389` require AST detections.

```python
# uidetox/analyzer.py:18-29
try:
    from tree_sitter import Language, Parser
    ...
    HAS_AST = True
except ImportError:
    HAS_AST = False
```

Repo conventions: Python 3.11+, setuptools, pytest-style functions in `tests/`,
and conventional commits (`fix: ...`, `refactor: ...`, `ci: ...`). No ADR,
CONTEXT, PRODUCT, or DESIGN document exists.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Install | `python -m pip install -e '.[dev]'` | exit 0; editable package and test deps installed |
| Tests | `python -m pytest -q` | exit 0; all tests pass |
| Metadata | `python -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('ok')"` | prints `ok` |

## Scope

**In scope**:
- `pyproject.toml`
- `README.md`
- `tests/conftest.py` (create)

**Out of scope**:
- Production analyzer behavior when optional imports fail at runtime.
- GitHub Actions; plan 003 owns release gating.
- Adding unrelated linters, formatters, pre-commit hooks, or lockfiles.

## Git workflow

- Branch: `codex/001-reproducible-verification`
- Commit: `build: add reproducible contributor test setup`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Define the contributor dependency set

Add `[project.optional-dependencies]` with a `dev` extra containing pytest. Keep
all existing runtime requirements unchanged. Use a compatibility range supporting
Python 3.11-3.13; do not pin platform-specific wheels. Add
`[tool.pytest.ini_options]` with `testpaths = ["tests"]` and concise failure output.

**Verify**: metadata command above → `ok`.

### Step 2: Fail fast when core AST support is missing

Create `tests/conftest.py`. At session start import `HAS_AST`; if false, raise a
pytest usage error saying to run `python -m pip install -e '.[dev]'`. Do not skip
AST tests: Tree-sitter is a declared core capability, so a contributor environment
without it is invalid.

**Verify**: `python -m pytest --collect-only -q` → exit 0 after editable install; 788 or more tests collected.

### Step 3: Document exact contributor workflow

Add a concise `Contributing` section to README with Python requirement, editable
install, canonical `python -m pytest -q` command, and expected all-green result.
Keep end-user Quick Start unchanged.

**Verify**: `rtk rg -n "pip install -e|python -m pytest" README.md` → both commands found in contributor section.

### Step 4: Prove clean-checkout behavior

Run editable install and full tests. Record actual passing count in commit/PR notes,
not in README where it will become stale.

**Verify**: `python -m pytest -q` → exit 0, zero failures/errors.

## Test plan

- Existing full suite is the acceptance test.
- Explicitly confirm `test_analyze_ast_dashboard_issue_has_correct_id` and
  `test_analyze_ast_animate_state_has_id` pass.
- Verify missing Tree-sitter in a throwaway environment produces one actionable
  usage error rather than two misleading assertion failures.

## Done criteria

- [ ] `python -m pip install -e '.[dev]'` exits 0.
- [ ] `python -m pytest -q` exits 0.
- [ ] Contributor commands appear in README.
- [ ] Missing AST support fails at session start with remediation text.
- [ ] Only in-scope files plus `plans/README.md` changed.
- [ ] Plan status updated.

## STOP conditions

- Runtime dependencies cannot install on any supported Python 3.11-3.13 interpreter.
- AST tests still fail after installing the declared runtime dependencies.
- Fix requires changing analyzer detection semantics instead of environment setup.
- Existing project metadata has gained a different test-tool convention since `55fc6f3`.

## Maintenance notes

Keep contributor and CI commands identical. Any future mandatory analyzer backend
must join core dependencies and the session preflight. Optional capabilities belong
in extras handled by plan 010.
