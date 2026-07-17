---
id: lf-0014
title: Parse source once into shared normalized facts
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_ast_capabilities.py tests/test_frontend_mapping.py tests/test_regressions.py -k "ast or semantic or analyzer or rule"
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator.
- Problem: analyzer and frontend mapper parse and walk the same JS/TS/TSX source independently through two cognitive-127+ functions.
- Out of scope: adding new parser packages, changing the 218-rule catalog, or changing issue IDs/order/messages.
- Review failure: analyzer issue parity changes, frontend semantic extraction regresses, a file is parsed twice in a combined analysis/map session, or compatibility imports break.
- Riskiest assumption: one normalized source-fact model can serve deterministic rules and semantic mapping without exposing tree-sitter nodes as its interface.
- Smallest acceptable: introduce a source-fact module with provenance/confidence, make analyzer and mapper consume it, retain compatibility wrappers, and lock behavior with parity tests.
- Recommended choice accepted: support existing JavaScript, TypeScript, TSX, and CSS capabilities first; language adapters remain internal.

# Context

`analyzer_ast._analyze_ast` and `frontend_semantics.extract_script_semantics` both call `_get_parser`, parse the same content, walk independent trees, and encode overlapping React/JSX knowledge. Analyzer orchestration also rereads the source separately.

# Acceptance Criteria

- A new deep source-fact module owns parser selection, parse lifecycle, normalized facts, provenance, confidence, and parse errors.
- Facts cover every semantic currently consumed by `frontend_semantics`: imports, React aliases, rendered modules, declared UI modules, regions, actions, state, endpoints including HTTP method when statically known, and routes.
- Facts expose analyzer-required AST-derived observations without leaking raw tree-sitter nodes across the external seam.
- Analyzer and frontend mapping consume the shared fact module rather than independently parsing/walking source.
- Existing `frontend_semantics.extract_script_semantics`, analyzer public imports, and monkeypatch compatibility remain callable.
- Combined consumers can reuse one fact extraction result for a file.
- Analyzer catalog remains 218 unique rules with unchanged order/fingerprint.
- Existing issue output remains byte-for-byte equivalent on representative TSX, CSS, Markdown, and unsupported fixtures.
- Tests cover alias imports, Axios/fetch methods, dynamic endpoint unknowns, parse errors, and reuse.

# Constraints

- No new runtime dependency.
- Do not remove the `uidetox.analyzer` compatibility facade.
- Preserve issue ID, tier, file, line, column, message, and ordering contracts.
- Reindex codebase-memory after file-shape changes before further symbol edits.

# Review Notes

- Compare outputs structurally, not only counts.
- Reject a wrapper that still performs two parses.
- Keep language-specific adapters private until two implementations genuinely vary.
