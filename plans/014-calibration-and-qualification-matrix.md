# Plan 014: Make every capability claim executable and measurable

> **Executor instructions**: Build one consolidated pytest-based qualification
> system. Do not add a second test runner or duplicate fixtures already covered
> by the full-stack lab. Delete superseded qualification helpers in the same
> change. Run every gate and update `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- pyproject.toml README.md .github/workflows/python-publish.yml examples/fullstack-slop-lab tests/test_live_demo_findings.py tests/test_release_readiness.py tests/test_regressions.py uidetox/data`

## Status

- **Priority**: P0
- **Effort**: L
- **Risk**: MED
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

UIdetox has 218 static rules plus semantic, runtime, visual, parity, packaging,
and provider-asset behavior. The existing suite is green, but capability
quality is not measured as precision/recall across frameworks and the last
audit could not qualify every rule, live Playwright behavior, Windows, the
installed wheel, packaged provider/design assets, or dependency advisories.
One qualification matrix should replace one-off audit work.

## Current state

- `examples/fullstack-slop-lab/beta-expectations.json` stores aggregate routes,
  parity counts, slop families, and remediation targets; it is an end-to-end
  product fixture, not a per-detector oracle.
- `tests/test_regressions.py` contains isolated detector cases without a shared
  expectation schema or precision/recall budget.
- `tests/test_live_demo_findings.py` qualifies one React/Vite +
  FastAPI/SQLite application.
- `.github/workflows/python-publish.yml:17-42` tests Python 3.11-3.13 on Ubuntu
  only and runs only when a release is published.
- `.github/workflows/python-publish.yml:44-84` builds and smoke-tests a wheel on
  Ubuntu only.
- `pyproject.toml:33-51` has `dev`, `visual`, and `capture` extras; no dependency
  audit tool is declared.
- `uidetox/data/` mirrors root commands, references, docs, and skill assets
  shipped in the wheel.

Repo convention: pytest is the canonical gate:
`python -m pytest -q -W error`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Core | `python -m pytest -q -W error` | exit 0 |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | zero unclassified FP/FN results |
| Live runtime | `python -m pytest -q -W error -m browser` | Playwright cases pass or skip only with explicit missing-browser reason |
| Assets/wheel | `python -m pytest -q -W error tests/test_release_readiness.py tests/test_update_skill.py` | packaged assets and wheel contract pass |
| Dependencies | `python -m pip_audit --strict --desc` | exit 0, or only reviewed/temporarily allowlisted advisories |

## Scope

**In scope**:
- `tests/calibration/README.md` (create)
- `tests/calibration/manifest.json` (create)
- `tests/calibration/fixtures/**` (create)
- `tests/test_calibration_matrix.py` (create)
- `tests/test_live_demo_findings.py`
- `tests/test_runtime_observer.py`
- `tests/test_release_readiness.py`
- `tests/test_update_skill.py`
- `tests/conftest.py`
- `pyproject.toml`
- `.github/workflows/python-publish.yml`
- `README.md`
- `docs/qualification.md` (create)

**Out of scope**:
- Fixing detector behavior exposed by qualification; plans 015-019 own fixes.
- A second corpus runner outside pytest.
- Downloading external sample applications during tests.
- Treating perceptual image similarity as an aesthetic-quality oracle; preserve
  `docs/decisions/visual-evidence-capability.md`.

## Cleanup and replacement constraints

- Reuse `examples/fullstack-slop-lab`; do not clone it into a second fixture.
- Fold redundant release-readiness and asset-parity helpers into shared pytest
  fixtures, then delete the old copies.
- Extend the existing workflow rather than adding overlapping workflows.
- Track `git diff --numstat`; explain any production-code increase. Most new
  lines should be fixtures, expectations, and tests.

## Git workflow

- Branch: `codex/014-capability-qualification`
- Commits: corpus schema, platform/browser qualification, then release gate.
- Suggested message: `test: qualify uidetox capability matrix`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Define one versioned expectation manifest

Create a strict manifest whose cases name fixture path, framework/language,
capability, detector/rule ID, positive/negative/degraded/unsupported status,
expected anchors, severity, optional route/state/viewport, and rationale.
Reject duplicate IDs, missing fixtures, unknown detectors, and anchors escaping
the fixture root.

Seed paired cases for React/Next-style TSX, Vue, Svelte, Astro, common API-client
shapes, CSS/Tailwind/themes/modern colors, representative Python/TypeScript
backends, OpenAPI, and ORM schema shapes. Fixtures are local minimal source
trees, not installed applications.

**Verify**: calibration command passes schema validation and fails readable
temporary malformed cases.

### Step 2: Measure signal without hiding unsupported behavior

Report TP, FP, FN, degraded, and unsupported counts by capability and
framework. Fail on unclassified output or regression from established
expectations. Do not create one blended score that masks a failing category.
Record current gaps as degraded/unsupported and link their rationale to plans
015-019.

**Verify**: injecting one unexpected result creates one FP failure; removing one
expected result creates one FN failure.

### Step 3: Qualify all 218 rules systematically

Require every rule ID to have:

- at least one positive case;
- at least one negative/non-trigger case;
- an owner category and supported extensions;
- an occurrence policy;
- a confidence level or an explicit manual-review classification.

Generate coverage from the live catalog; do not maintain a duplicate list.
Rules that cannot be made deterministic must be explicitly manual and excluded
from objective scoring by plan 015.

**Verify**: a newly added rule without required cases fails collection.

### Step 4: Add live-browser qualification

Mark Playwright tests with `browser`. Use the existing full-stack lab and one
server lifecycle fixture. Exercise all supported viewports, screenshots,
runtime findings, readiness states, and failure cleanup. No test may depend on
the public network. Start/stop processes through a single fixture and prove no
orphan process remains.

**Verify**: browser command passes twice consecutively with identical structured
results.

### Step 5: Qualify Windows and installed-wheel behavior

Extend the existing workflow's quality matrix to include Windows for supported
Python versions without duplicating the Ubuntu job body. Use platform-neutral
Python in test commands. Build once per release candidate, install the wheel
into a clean environment, run CLI smoke tests outside the checkout, and verify
all bundled commands/references/docs match their canonical root sources.

**Verify**: workflow syntax is valid; local wheel smoke and asset-parity tests
pass; Windows matrix is visible in workflow configuration.

### Step 6: Add actionable dependency auditing

Add `pip-audit` to a dedicated `audit` development extra or the existing `dev`
extra only if contributor installation cost remains acceptable. Run it against
the built package environment. Allowlist only a reviewed advisory with package,
rationale, expiry date, and tracking reference; never blanket-ignore IDs.

**Verify**: dependency command exits 0 with no unexplained high/critical
advisory.

### Step 7: Document the one-command qualification contract

Document core, browser, dependency, and wheel commands in
`docs/qualification.md`; keep README concise. Remove stale instructions or
duplicate command tables elsewhere.

**Verify**: every documented command is copied from executable configuration
and succeeds in its supported environment.

## Test plan

- Manifest schema/path validation.
- Positive/negative detector pairs and per-capability metrics.
- Catalog-to-corpus completeness for all rule IDs.
- Full-stack lab browser lifecycle and deterministic results.
- Windows-safe path/process behavior.
- Installed-wheel CLI and asset parity outside checkout.
- Dependency audit policy and expiring allowlist validation.

## Done criteria

- [ ] Every rule has explicit positive/negative qualification or manual status.
- [ ] Framework/capability FP/FN is measurable.
- [ ] Live Playwright runs deterministically with no orphan processes.
- [ ] Windows and installed-wheel gates exist and pass.
- [ ] Bundled assets match canonical sources.
- [ ] Dependency advisories are checked with no unexplained high/critical item.
- [ ] No duplicate runner, fixture application, or workflow remains.
- [ ] Full suite passes and plan status is updated.

## STOP conditions

- Qualification requires public-network access or real credentials.
- Windows support requires dropping Python 3.11-3.13 compatibility.
- A detector is nondeterministic across identical consecutive runs.
- Closing an FP/FN would require changing production code in this plan.
- A dependency advisory affects reachable production code; stop and open a
  separate remediation plan before allowlisting it.

## Maintenance notes

This is the permanent capability-claim gate. New rules, adapters, runtime
states, packaged assets, or supported platforms must extend this matrix rather
than adding isolated test harnesses.
