# ADR: Evidence-bound finding lifecycle

Status: Accepted
Date: 2026-07-25

## Decision

UIdetox uses one immutable, versioned `Finding` at every static, runtime, and
contract boundary. Its fingerprint derives from detector identity, normalized
evidence, and source/runtime/contract anchors. Producers emit every occurrence;
state, map, scan output, queue packets, scoring, and resolution consume the
same model.

Resolution dispatches the finding's verifier and records history only when the
originating detector reports the anchored defect absent. Mechanical checks do
not substitute for detector verification. Explicit overrides require an actor,
reason, and timestamp; overridden findings stay current, scored, and blocking.

Scores use only current findings and qualified coverage. Historical resolutions
cannot improve a new score. Subjective review requires A/B/C/D dimensions,
rationale, reviewer, linked routes/states/viewports/findings, and hashes for
source, map, and runtime evidence. Hash drift invalidates that review.

One eligibility evaluator owns pending-finding, score, qualification, freshness,
review, worktree, and session-branch gates. Status, workflow, and finish consume
its typed blockers.

## Compatibility and consequences

Schema version 2 loads legacy state through one read adapter without rewriting
files during load. The next save writes canonical findings. Unknown fields
survive round trips for forward compatibility; no legacy mutable pipeline or
lifetime-score path remains active.

New detector families must emit canonical findings with enough provenance for a
deterministic verifier. Ambiguous evidence remains informational or
investigative and cannot be presented as a verified defect.
