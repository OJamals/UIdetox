---
id: lf-0016
title: Deepen redesign into source-aware feasibility planning
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_frontend_mapping.py tests/test_project_mapping.py tests/test_redesign_planning.py
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator.
- Problem: redesign ranks five static strategies from counts, keywords, and fingerprints; prototype formatting does not reason over dependency ownership, edit ordering, parity blockers, or evidence freshness.
- Out of scope: directly editing production frontend code, selecting a proposal without user choice, or inventing backend feasibility.
- Review failure: proposals remain canned strings, source targets ignore graph ownership, stale runtime evidence is silently treated as current or dropped, preserved contracts regress, or structural-distance behavior breaks.
- Riskiest assumption: the existing semantic graph and parity report contain enough evidence for deterministic feasibility and migration ordering.
- Smallest acceptable: enrich proposals with evidence-backed affected modules, dependency order, feasibility blockers, freshness, and observable acceptance checks; make prototype briefs expose them.
- Recommended choice accepted: retain strategy catalog as direction input, but it cannot be the planner’s sole source of truth.

# Context

`_STRATEGIES` is a 177-line static catalog. `_strategy_relevance` scores topology signals and intent keywords. `_build_proposal` formats catalog fields and a short file list. `frontend_map_is_fresh` checks source hashes only; automatic redesign refresh remaps without runtime evidence.

# Acceptance Criteria

- Redesign planning consumes semantic graph edges, cross-stack parity, experience contracts, resolved intent, and evidence freshness.
- Every proposal serializes:
  - affected source modules with evidence,
  - dependency-aware migration order,
  - preserved contracts tied to source/runtime evidence,
  - feasibility blockers and unknowns,
  - evidence freshness status,
  - acceptance checks observable from source or runtime.
- Source targets derive from ownership/dependency evidence, not an arbitrary filename slice.
- Cross-stack unmatched operations and method mismatches become explicit blockers or migration work, never silent assumptions.
- Runtime evidence has recorded provenance. When source changes, automatic refresh must not silently discard old runtime evidence or label it current; stale evidence is retained as stale or converted to an explicit unknown.
- Pairwise structural-distance and 1–5 variant contracts remain intact.
- Prototype briefs render the new source-aware planning fields and keep untrusted source evidence isolated.
- Tests cover dependency ordering, cyclic dependencies, parity blockers, runtime staleness, deterministic serialization, and legacy artifact loading.

# Constraints

- No production source edits.
- No automatic proposal selection.
- Preserve existing public proposal IDs and structural fingerprints where inputs are unchanged.
- Keep outputs deterministic.

# Review Notes

- Reject migration order based only on alphabetical filenames.
- Check cycles produce a clear grouped step or blocker.
- Check stale runtime evidence cannot satisfy an acceptance check.
