# Plan 003: Gate PyPI publication on verification

> **Executor instructions**: Follow the plan exactly. Do not publish, push, or
> manually trigger the workflow. Update the plan index after local/static validation.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- .github/workflows/python-publish.yml pyproject.toml`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: tests
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

Every push touching `uidetox/**` or `pyproject.toml` on `main`/`master` can build
and publish to PyPI. Package construction is the only current gate. The release
workflow must consume the same contributor test command established by plan 001
and require it before distribution build or trusted publishing.

## Current state

```yaml
# .github/workflows/python-publish.yml:23-40
jobs:
  release-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - name: Build release distributions
        run: |
          python -m pip install build
          python -m build
```

`pypi-publish` depends only on `release-build` (`:46-49`). Workflow commit style is
`ci: ...`. Preserve trusted-publishing permissions and environment configuration.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Local tests | `python -m pytest -q` | all pass |
| YAML parse | `ruby -e "require 'yaml'; YAML.load_file('.github/workflows/python-publish.yml'); puts 'ok'"` | prints `ok` |
| Diff review | `git diff --check -- .github/workflows/python-publish.yml` | exit 0, no output |

## Scope

**In scope**:
- `.github/workflows/python-publish.yml`

**Out of scope**:
- Changing PyPI token/trusted-publishing configuration.
- Triggering a release or publishing a package.
- Changing branch names or release/version policy.
- Adding unrelated GitHub workflows.

## Git workflow

- Branch: `codex/003-release-verification-gate`
- Commit: `ci: gate package publication on tests`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add supported-version verification matrix

Add a `quality` job on Ubuntu with Python 3.11, 3.12, and 3.13. Checkout source,
set up matrix Python, install `.[dev]`, then run exactly `python -m pytest -q`.
Use dependency caching only if setup-python can key it from `pyproject.toml` without
adding a lockfile.

**Verify**: YAML parse command → `ok`.

### Step 2: Make build depend on quality

Add `needs: quality` to `release-build`. Keep `pypi-publish` depending on
`release-build`, forming `quality → release-build → pypi-publish`.

**Verify**: `rtk rg -n -C 2 'quality|needs:' .github/workflows/python-publish.yml` → dependency chain visible.

### Step 3: Ensure test-only changes can validate safely

Add `tests/**` to path triggers only if project policy intends test changes to run
this workflow. Because this workflow publishes, do not make a test-only change
publish a new package. Preferred resolution: split verification into a reusable or
separate non-publishing workflow only if necessary; otherwise keep publish paths
unchanged and document that release-gate tests run on source/package changes.

**Verify**: workflow still publishes only after source/package metadata changes and green quality job.

## Test plan

- Local canonical test command passes.
- YAML parses.
- Inspect job dependencies mechanically.
- PR review must confirm no permissions broadened and secret references unchanged.

## Done criteria

- [ ] Python 3.11-3.13 matrix runs canonical tests.
- [ ] Build cannot start until matrix succeeds.
- [ ] Publish cannot start until build succeeds.
- [ ] Trusted-publishing permissions unchanged.
- [ ] No workflow was triggered by executor.
- [ ] `plans/README.md` status row updated.
- [ ] Plan status updated.

## STOP conditions

- Plan 001 did not establish a green canonical command.
- Any supported Python version cannot install declared dependencies.
- Required gating needs repository-environment changes unavailable in code.
- Change would expose, replace, or print a secret.

## Maintenance notes

Future supported Python classifiers must match this matrix. Review workflow changes
for accidental publication on pull requests or test-only commits.
