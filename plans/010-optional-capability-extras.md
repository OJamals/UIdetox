# Plan 010: Split optional capability dependencies into extras

> **Executor instructions**: Preserve core scan behavior and all source/package-data
> mirrors. This plan is reconciled through completed plans 001-009; keep plan 001's
> `dev` extra and all later stacked behavior intact. Update plan index after completion.
>
> **Drift check (run first)**: `git diff --stat 54dc45c..HEAD -- pyproject.toml README.md uidetox/commands/capture.py docs uidetox/data/docs tests/test_optional_dependencies.py`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: migration
- **Planned at**: commit `54dc45c`, 2026-07-16

## Why this matters

Base installation currently pulls Playwright and Pillow although each is used by an
optional capability and imports defensively. Users running scan/check/queue
pay larger installs and broader dependency-conflict/security surface. Playwright's
Python package also does not install Chromium, so documented base installation still
leaves capture unusable without an extra browser step.

## Current state

- `pyproject.toml:27-35` makes Pillow and Playwright mandatory.
- `uidetox/commands/capture.py:28-38` handles missing Playwright import.
- `uidetox/commands/capture.py:89-132` handles missing Pillow.
- `README.md:33-60` documents only `pip install uidetox`.

Tree-sitter, PyYAML, and language grammars power core scanning and must remain base
dependencies. Plan 001's `dev` extra must remain intact.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Metadata | `python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['optional-dependencies'].keys())"` | includes `dev`, `visual`, `capture`, `all` |
| Base wheel | `python -m pip wheel . --no-deps --wheel-dir /tmp/uidetox-wheel` | exit 0, wheel created |
| Tests | `python -m pytest -q tests/test_optional_dependencies.py` | all pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `pyproject.toml`
- `README.md`
- `uidetox/commands/capture.py`
- root `docs/*.md` installation/capture sections only
- matching `uidetox/data/docs/*.md` mirrors
- `tests/test_optional_dependencies.py` (create)

**Out of scope**:
- Making Tree-sitter optional.
- Automatically downloading browsers during package install.
- Replacing Pillow.
- Changing capture image algorithms.

## Git workflow

- Branch: `codex/010-optional-capability-extras`
- Commit: `build: move optional capabilities into extras`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Define extras without losing plan 001 metadata

Move existing Pillow and Playwright requirements into `capture`; define `all` with
the complete optional set. Preserve version constraints already present. Keep or
merge `dev` from plan 001. Base dependencies retain PyYAML and all Tree-sitter
packages.

**Verify**: metadata command lists all four extras; base dependency list excludes both optional packages.

### Step 2: Improve unavailable-feature guidance

Capture missing-import and browser-launch failures must recommend:

```bash
pip install 'uidetox[capture]'
python -m playwright install chromium
```

Preserve original exception summary for non-browser launch failures.

**Verify**: tests monkeypatch imports/launch and assert actionable text.

### Step 3: Update installation documentation and mirrors

README Quick Start keeps minimal base install. Add an Optional Capabilities section
for `visual`, `capture`, `all`, and Chromium bootstrap. Update provider docs only where
they describe installation/capture. Keep every root doc byte-identical to its
`uidetox/data/docs` counterpart after edits.

**Verify**: hash comparison over root/docs mirrors reports zero differences.

### Step 4: Test base import and feature fallbacks

Add tests parsing project metadata, simulating missing optional imports, and verifying
core `import uidetox` plus analyzer import does not require optional packages. Do not
uninstall packages from executor environment; monkeypatch import boundaries.

**Verify**: optional dependency tests and full suite pass.

## Test plan

- Metadata extras contain expected distributions; base excludes them.
- Missing Playwright/Pillow does not crash unrelated commands.
- Missing Chromium message contains exact browser-install command.
- Root and bundled docs remain synchronized.

## Done criteria

- [ ] Minimal install excludes Playwright and Pillow.
- [ ] `visual`, `capture`, `all`, `dev` extras coexist.
- [ ] Capture remediation names both package extra and Chromium install.
- [ ] Docs/mirrors synchronized.
- [ ] Base wheel builds; full tests pass; plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Any optional package is imported unconditionally on core scan/CLI startup.
- Packaging backend rejects extras layout.
- Plan 001's dev setup would be overwritten.
- Browser installation would need to execute automatically during package install.

## Maintenance notes

New optional capabilities need an extra, guarded import, actionable remediation, and
base-import regression test. Review dependency additions for whether every user truly
needs them.
