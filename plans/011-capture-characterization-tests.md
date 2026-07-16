# Plan 011: Characterize the capture and visual-diff pipeline

> **Executor instructions**: Build deterministic tests first. Do not require network,
> localhost, or a real browser in the default suite. This plan is reconciled through
> completed plans 001-010; preserve Plan 010 guidance and extras. Update plan index when complete.
>
> **Drift check (run first)**: `git diff --stat af366bc..HEAD -- uidetox/commands/capture.py tests/test_capture.py pyproject.toml`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: `plans/010-optional-capability-extras.md`
- **Category**: tests
- **Planned at**: commit `af366bc`, 2026-07-16

## Why this matters

Capture and visual diff are advertised core workflow surfaces, yet no tests reference
`uidetox.commands.capture`, `_capture_screenshot`, or `_generate_visual_diff`. Regressions
in naming, severity thresholds, metadata, responsive branches, missing baseline, or
failure exits can ship unnoticed. Deterministic characterization enables safe future
optimization without browser flakiness.

## Current state

- `uidetox/commands/capture.py:28-54`: Playwright launch/navigation/screenshot.
- `:57-76`: responsive viewport capture.
- `:79-136`: resize, pixel difference, 8x visualization, severity thresholds.
- `:139-233`: before/after/responsive orchestration and metadata.
- Repo-wide test search at `55fc6f3`: zero capture references.

Use existing pytest `tmp_path`, `monkeypatch`, and `capsys` style from
`tests/test_regressions.py`; avoid global filesystem writes.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup | `python -m pip install -e '.[dev,capture]'` | exit 0 |
| Targeted | `python -m pytest -q tests/test_capture.py` | all pass without browser launch |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `tests/test_capture.py` (create)
- `uidetox/commands/capture.py` only for minimal dependency injection/test seam
- `pyproject.toml` only if a pytest marker must be registered

**Out of scope**:
- Changing visual-diff thresholds or algorithms.
- Installing/launching Chromium in default tests.
- Snapshotting binary images in git.
- Optimizing Pillow pixel iteration.

## Git workflow

- Branch: `codex/011-capture-characterization-tests`
- Commit: `test: characterize capture and visual diff`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Characterize pure visual diff

Generate tiny RGB images under `tmp_path` using Pillow. Test identical images,
controlled changed-pixel percentages around every existing threshold, mismatched
dimensions, diff file creation, metadata keys, rounded percentage, and amplified diff
visibility. Assertions must encode current behavior, not new desired thresholds.

**Verify**: visual-diff tests pass deterministically.

### Step 2: Characterize capture wrapper failures

Monkeypatch Playwright import/objects or extract one minimal injectable launcher seam.
Cover missing package, missing browser executable, navigation exception, screenshot
success, browser close, viewport/full-page parameters. Never open network/localhost.

**Verify**: tests assert return values and actionable stderr from plan 010.

### Step 3: Characterize command orchestration

Monkeypatch `_server_is_reachable`, `_capture_screenshot`, `_capture_multi_viewport`,
and `_snapshots_dir`. Cover `before`, `after` with/without baseline, responsive success,
partial viewport failure, metadata JSON, `latest.png`, and exit codes.

**Verify**: targeted tests pass with no browser process.

### Step 4: Add opt-in smoke marker only if stable

Optionally add one `integration`-marked real-browser test that is skipped unless an
explicit environment flag is set. Register marker in pytest config. It must use a
local fixture server, bounded timeout, and cleanup. Omit this step if it adds platform
fragility; deterministic tests are required outcome.

**Verify**: default targeted command reports no unregistered marker and does not launch Chromium.

## Test plan

- Pure image math and severity boundaries.
- Missing optional dependency/browser errors.
- Screenshot wrapper argument forwarding and cleanup.
- Before/after/responsive state machine.
- Metadata and output paths isolated under `tmp_path`.

## Done criteria

- [ ] Capture module has direct deterministic coverage.
- [ ] Every visual severity boundary is asserted.
- [ ] Before/after/responsive branches covered.
- [ ] Default suite needs no browser/network.
- [ ] Full suite passes and plan status updated.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Tests require production threshold changes to pass.
- Capture code cannot be isolated without a public API redesign.
- Default tests require browser download, network, or fixed ports.
- Plan 010 capture extra is absent or incompatible.

## Maintenance notes

Treat these as characterization tests: algorithm changes require intentional expected
value updates and reviewer scrutiny. Keep real-browser coverage opt-in until CI has an
explicit browser contract.
