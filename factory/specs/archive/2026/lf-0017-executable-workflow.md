---
id: lf-0017
title: Add an opt-in executable and resumable workflow engine
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_workflow.py tests/test_frontend_mapping.py tests/test_project_mapping.py tests/test_regressions.py -k "loop or workflow or scan or map or redesign or finish"
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator.
- Problem: `uidetox loop` prints commands but does not execute analysis, mapping, planning, review, status, or finish transitions; the map→redesign→prototype path is separate.
- Out of scope: invoking an external coding agent automatically, selecting a redesign proposal automatically, bypassing review, or making default `uidetox loop` mutate source.
- Review failure: preview mode changes behavior, `--execute` shells through fragile command strings, state cannot resume, phases skip required evidence, user decisions are invented, or injected-adapter tests cannot drive the full state machine.
- Riskiest assumption: deterministic tool phases can execute automatically while agent fixes and proposal selection remain explicit waiting states.
- Smallest acceptable: a workflow module owns phase state/artifacts/retries, `uidetox loop --execute` runs deterministic phases and stops at human/agent decision gates, and default loop remains preview-only.
- Recommended choice accepted: execution requires explicit `--execute`; no surprise mutation.

# Context

`commands/loop.py::run` has cognitive complexity 38 and only prints the stage commands. Its call graph has no calls to scan, next, review, status, finish, map, redesign, or prototype. Existing tests assert banners/detection rather than executable transitions.

# Acceptance Criteria

- A deep workflow module owns phase definitions, transition rules, artifact references, retry/error state, and durable resumability.
- Default `uidetox loop` preserves current preview/instruction behavior.
- `uidetox loop --execute` runs deterministic phases through injected in-process adapters rather than shell command strings.
- Workflow includes mechanical checks, static analysis, semantic project mapping, issue planning, redesign planning, prototype generation after explicit proposal selection, subjective review gate, status/score evaluation, and finish eligibility.
- Workflow stops with explicit waiting states when:
  - source fixes require an agent,
  - subjective score requires human/LLM input,
  - redesign proposal selection is missing,
  - verification evidence is stale or blocked.
- State persists atomically under `.uidetox/` and resumes without rerunning completed fresh phases.
- Input/source changes invalidate only dependent downstream phases.
- Failed phases record concise evidence and remain retryable; no infinite automatic retry.
- Tests use fake adapters to cover happy path, each waiting state, failure/retry, resume, selective invalidation, and preview compatibility.
- CLI help and README document `--execute`, waiting states, and safety behavior.

# Constraints

- No external agent CLI invocation.
- No automatic proposal choice.
- No archive/finish transition without verified score and fresh evidence.
- Preserve current branch safety and existing command entry points.

# Review Notes

- Verify the workflow module—not `commands/loop.py`—contains transition knowledge.
- Verify repeated execution is idempotent for fresh completed phases.
- Verify errors never mark later phases complete.
