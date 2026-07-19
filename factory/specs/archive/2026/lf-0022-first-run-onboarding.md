---
id: lf-0022
title: Add a resumable first-run onboarding module
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_onboarding.py
  - .venv/bin/python -m pytest -q
  - .venv/bin/python -m compileall -q uidetox
---

# Grill Gate

- Owner: UIdetox maintainers and first-run CLI users.
- Problem: `uvx uidetox` with no command only prints help, leaving users to discover and order installation, agent setup, optional capabilities, intent capture, prompt handoff, and verification themselves.
- Out of scope: implementing capability installation, deepening agent installation, or creating the intent journal/handoff; those are follow-on specs lf-0023 through lf-0025.
- Review failure: explicit commands change behavior, `--help` starts onboarding, noninteractive use mutates state, returning users cannot resume, state is non-atomic, or existing tests fail.
- Riskiest assumption: no-argument invocation can distinguish a safe interactive first run from automation without uv-specific environment heuristics.
- Smallest acceptable: a deep onboarding Module owns ordered step state and resumption; an interactive no-command invocation starts or resumes it, prints basic instructions and pending steps, while noninteractive/no-command and `--help` retain help behavior.

# Context

The current entry point in `uidetox/cli.py` routes no-command invocation directly to help. `commands/setup.py::run` already mixes configuration and interactive behavior, so adding first-run sequencing there would reduce Locality. The onboarding Module needs one small Interface that hides state versioning, atomic persistence, idempotency, step ordering, and resume behavior. Later specs will supply real Adapters for agent setup, capability provisioning, intent journaling, and handoff generation.

# Acceptance Criteria

- A new onboarding Module owns a versioned ordered workflow with the steps `intro`, `agent`, `capabilities`, `intent`, and `handoff`.
- Onboarding state persists atomically under `.uidetox/` and records status, completed steps, timestamps, and the next pending step without overwriting unrelated project state.
- A virgin interactive `uidetox` no-command invocation starts onboarding, completes the `intro` step, and shows the ordered remaining steps.
- A later interactive no-command invocation resumes from persisted state without replaying completed steps.
- Noninteractive no-command invocation prints normal CLI help and performs no filesystem writes.
- `uidetox --help`, all explicit commands, and dynamic design skills retain existing dispatch behavior.
- Onboarding I/O and filesystem location are injectable through internal seams so tests use real state persistence without touching the operator's project.
- Tests cover virgin start, resume, completed state, malformed state recovery, TTY/non-TTY behavior, EOF, and explicit-command compatibility.

# Constraints

- Do not install packages or agent files in this spec.
- Do not call command runners as internal library Interfaces.
- Do not add a generalized plugin framework or expose step callbacks as a public Interface.
- Do not infer that `uvx` is durable; no-command interactive behavior must be safe for pip, uv tool, and uvx execution.
- Preserve the existing dirty Chroma-removal diff and stage only spec-owned paths.

# Review Notes

- Inspect the onboarding Module with the deletion test: removing it should redistribute ordering, state, resume, and idempotency logic across callers.
- Confirm state writes use the repository's atomic JSON conventions or an equally safe implementation.
- Confirm terminal detection does not consume stdin before the workflow starts.
- Confirm no-command help remains deterministic in captured/noninteractive execution.
