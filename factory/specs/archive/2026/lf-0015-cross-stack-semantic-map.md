---
id: lf-0015
title: Add cross-stack semantic mapping and deterministic parity
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_project_mapping.py tests/test_frontend_mapping.py tests/test_regressions.py -k "backend or api or map or fullstack or contract"
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator.
- Problem: backend/database/API detection returns tool names and commands only; UIdetox cannot answer which frontend operations lack backend support or which backend operations lack frontend use.
- Out of scope: proving arbitrary business-feature equivalence, executing servers, database introspection, or requiring network access.
- Review failure: parity remains prose-only, method/path mismatches are conflated with missing routes, dynamic paths create false certainty, old frontend-map consumers break, or supported adapters lack fixture tests.
- Riskiest assumption: HTTP operation and schema evidence is the smallest deterministic feature unit shared across frontend and backend.
- Smallest acceptable: build a semantic project-map module that combines frontend requests, backend routes, OpenAPI schemas, and runtime evidence; emit explicit unmatched/mismatch/unknown results.
- Recommended choice accepted: support OpenAPI/Swagger JSON/YAML, Python FastAPI/Flask decorators, and JS/TS Express/Fastify/Nest route declarations; other frameworks report unknown rather than guessed parity.

# Context

`FrontendMap` contains frontend nodes, edges, experience contracts, fingerprint, and evidence. `detect_backend`/`detect_api` only identify tooling. `scan` prints “check DTO alignment” but performs no reconciliation.

# Acceptance Criteria

- A semantic project-map module owns cross-stack evidence and reconciliation behind one interface.
- Frontend request facts include normalized HTTP method when known, normalized route path, source location, and confidence.
- Backend adapters extract normalized operations from:
  - OpenAPI/Swagger JSON and YAML path/method entries plus referenced schema names.
  - FastAPI and Flask route decorators.
  - Express, Fastify, and Nest route declarations in JS/TS.
- Route normalization treats `:id`, `{id}`, and framework-equivalent dynamic segments as the same shape while preserving parameter identity as evidence.
- Reconciliation separately reports:
  - frontend operation without matching backend operation,
  - backend operation without matching frontend operation,
  - path match with HTTP-method mismatch,
  - unresolved/dynamic evidence that cannot be compared safely.
- `uidetox map` produces cross-stack evidence automatically when supported backend evidence exists.
- Existing frontend-map top-level keys and loading behavior remain compatible; legacy frontend-only artifacts remain consumable.
- `scan`, redesign, and prototype consumers can read the deterministic parity report instead of printing an unsupported claim.
- Fixture tests cover each supported adapter, both unmatched directions, method mismatch, dynamic normalization, schema references, and unknown frameworks.

# Constraints

- No server startup, network calls, or database connections.
- Unsupported syntax must become unknown evidence, not a false match.
- Keep deterministic ordering and JSON serialization.
- Do not claim arbitrary UI/business features are equivalent beyond available operation/schema evidence.

# Review Notes

- Verify auth/error-state claims are not invented from route presence.
- Verify duplicate route declarations deduplicate without losing provenance.
- Verify backend-only health/internal routes can be classified or suppressed without corrupting raw evidence.
