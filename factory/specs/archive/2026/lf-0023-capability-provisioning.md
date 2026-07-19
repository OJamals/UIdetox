---
id: lf-0023
title: Add consent-aware optional capability provisioning
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_capabilities.py tests/test_optional_dependencies.py
  - .venv/bin/python -m pytest -q
  - .venv/bin/python -m compileall -q uidetox
---

# Grill Gate

- Owner: UIdetox maintainers and users opting into richer codebase/runtime/visual evidence.
- Problem: Pillow, Playwright, Chromium, and codebase-memory setup knowledge is duplicated or absent, and `uvx` execution must not be treated as a durable environment.
- Out of scope: silently installing anything, changing core dependencies, adding Chroma, or redesigning agent-file installation.
- Review failure: any install runs without explicit consent, shell injection is possible, uvx cache is mutated directly, codebase-memory is represented as a Python extra, capability status is guessed, or existing optional-dependency behavior regresses.
- Riskiest assumption: one capability plan can provide Locality while respecting three real Seams: Python package installation, Playwright browser installation, and external codebase-memory setup.
- Smallest acceptable: a deep capability Module detects status, builds a deterministic recommended plan, selects pip/uv Adapters, executes only consented allowlisted argv, verifies outcomes, and integrates with the onboarding `capabilities` step.

# Context

`pyproject.toml` keeps Pillow and Playwright optional. Existing error paths repeat pip and Chromium commands. Official uv semantics make `uvx` disposable and discourage mutating tool environments, so persistent installation must use `uv tool install` or a user-selected pip environment. codebase-memory is an external MCP/plugin capability and needs a separate Adapter and honest verification.

# Acceptance Criteria

- A capability Module defines typed capability status and setup results for `codebase-memory`, `pillow`, `playwright`, and `chromium`.
- Detection distinguishes Python distribution presence, import presence, Playwright browser readiness, command/MCP availability, and unknown/unverifiable state.
- The recommended plan explains that all capabilities are optional, selects all by default only in an interactive confirmation prompt, and supports declining any or all without failure.
- pip and uv execution use fixed argv lists with no shell interpolation; subprocess output is bounded and errors are converted to structured results.
- A uvx invocation is never modified in place. Durable uv setup uses the supported uv tool installation path; pip setup targets the active/interpreter environment only when the user selects it.
- Playwright package setup and Chromium setup remain separate verifiable operations.
- codebase-memory remains an external-tool Adapter; its setup guidance and verification are source-backed and never represented in `pyproject.toml` extras.
- Existing capture/visual missing-dependency messages derive commands from the capability Module rather than maintaining divergent literals.
- The onboarding workflow invokes capability provisioning after agent setup and records the step complete when the user either verifies selected capabilities or explicitly skips them.
- Tests cover uv, pip, uvx, declined installs, missing executables, failed subprocesses, Pillow/PIL naming, package-present/browser-missing, codebase-memory unavailable, output bounds, and shell metacharacters as inert data.

# Constraints

- No network operation in tests.
- No installation without a visible confirmation prompt.
- No `shell=True`, command-string construction, `eval`, or environment mutation hidden from the user.
- Do not move Pillow or Playwright into core dependencies.
- Preserve the existing Chroma-removal changes to `pyproject.toml` and `tests/test_optional_dependencies.py`; edit overlapping files minimally.

# Review Notes

- Verify two or more real Adapters justify each Seam; avoid a shallow standalone pip/uv selector.
- Inspect offline behavior and error text for actionable recovery.
- Check official uv and codebase-memory source guidance against generated commands.
- Verify capability detection has no import-time optional-dependency requirement.
