# Plan 017: Replace route parity with typed full-stack contract lineage

> **Executor instructions**: Migrate the existing project map; do not bolt a
> second contract graph beside it. Unknown evidence must remain unknown. Delete
> route-only reconciliation after all consumers move. Update the plan index.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- uidetox/project_map.py uidetox/frontend_map.py uidetox/tooling.py uidetox/commands/scan.py uidetox/commands/map.py uidetox/workflow.py tests/test_project_mapping.py tests/test_frontend_mapping.py tests/test_calibration_matrix.py`

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/015-unified-findings-and-verified-closure.md`, `plans/016-application-semantics-and-source-ownership.md`
- **Category**: direction
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

Current “full-stack parity” proves only that comparable paths and HTTP methods
exist. It can report compatibility while request/response fields, enums,
nullability, validation, error envelopes, authorization, mutation semantics, or
database entities disagree. UIdetox needs lineage from user-visible UI state to
stored data, with gaps converted into evidence-backed findings.

## Current state

- `uidetox/project_map.py:101-135` models operation method/path plus parameter
  names and schema references.
- `uidetox/project_map.py:289-387` groups by normalized path and compares only
  method sets.
- `uidetox/project_map.py:392-424` frontend extraction does not populate schema
  shapes.
- `uidetox/project_map.py:505-549` OpenAPI extraction retains referenced schema
  names, not field-level contracts.
- `uidetox/commands/scan.py:571-573` correctly warns that auth, UI error states,
  and business equivalence remain unverified.
- `tests/test_project_mapping.py:85-141` currently accepts a backend schema with
  no corresponding frontend schema as zero findings.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Contract tests | `python -m pytest -q -W error tests/test_project_mapping.py` | all pass |
| Integration | `python -m pytest -q -W error tests/test_frontend_mapping.py tests/test_live_demo_findings.py` | all pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | contract TP/FP/FN stable |
| Full | `python -m pytest -q -W error` | exit 0 |

## Scope

**In scope**:
- `uidetox/project_map.py`
- `uidetox/frontend_map.py`
- `uidetox/semantic_adapters.py`
- `uidetox/tooling.py`
- `uidetox/commands/scan.py`
- `uidetox/commands/map.py`
- `uidetox/workflow.py`
- `tests/test_project_mapping.py`
- `tests/test_frontend_mapping.py`
- `tests/test_live_demo_findings.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/contract-lineage.md` (create)

**Out of scope**:
- Generating DTOs, migrations, backend code, or UI components.
- Executing database queries against user systems.
- Declaring business equivalence from matching names alone.
- Supporting frameworks absent from plan 014's capability matrix.

## Cleanup and replacement constraints

- Evolve `ProjectMap` into one versioned application contract graph or replace
  it after confirming no documented external API requires the class name.
- Remove route-only `reconcile_operations` once graph reconciliation is live.
- Reuse plan 016 adapters; no project-map-specific parser copies.
- Emit plan 015 `Finding` objects directly; no second parity-finding lifecycle.
- Keep compatibility loading narrow and read-only, then write only the new
  version.

## Git workflow

- Branch: `codex/017-fullstack-contract-lineage`
- Commit by vertical slice: graph model, frontend/backend adapters,
  database/auth/state lineage, reconciliation/cleanup.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Add mismatched and matched contract oracles

Create paired fixtures covering:

- request/response field additions/removals and renamed fields;
- scalar, array/object, enum, nullable/required differences;
- validation constraints;
- success status and error-envelope variants;
- authentication/authorization/tenant evidence;
- frontend loading/error/empty/success states;
- mutation/cache invalidation evidence;
- handler/service/ORM/entity/column lineage;
- unknown and dynamically constructed contracts.

**Verify**: current route-only logic fails the intended mismatch cases.

### Step 2: Define one versioned contract graph

Model typed nodes for UI action/state, client operation, request/response/error
schema and field, route/handler, service operation, authorization requirement,
entity/model, and database field. Model directed edges with provenance,
confidence, source anchor, and capability status.

Unknown, absent, and contradictory are distinct. Missing extraction evidence is
never treated as parity.

**Verify**: exact graph serialization/round-trip and unknown-state tests pass.

### Step 3: Populate frontend contract evidence

Consume plan 016 call/type facts to link UI actions and states to client calls,
request payload construction, referenced TypeScript/schema types, response
consumption, and error/loading/empty UI branches. Preserve dynamic expressions
as unresolved nodes.

**Verify**: fixture UI actions reach expected client/schema/state nodes.

### Step 4: Populate backend and database evidence

Refactor existing OpenAPI/Python/JS/TS route extraction into adapters that add
DTO fields, validation, status/error variants, auth markers, handler/service
calls, and detected ORM/schema fields for qualified framework families. Use
static evidence only; do not infer tenant/auth guarantees from naming.

**Verify**: backend fixtures reach handler/service/entity fields with source
anchors; unsupported stacks report capability gaps.

### Step 5: Reconcile graph slices, not names

Compare compatible UI-action-to-storage paths:

- route/method;
- request and response field shape;
- nullability/required/enum/validation;
- error/status variants;
- auth/tenant evidence;
- mutation and user-visible state coverage.

Emit typed findings with confidence and the smallest causal mismatch slice.
Classify unresolved/unsupported evidence as investigate/coverage gaps.

**Verify**: matched fixtures are clean; each deliberate mismatch produces one
deduplicated causal finding.

### Step 6: Migrate commands and remove route-only parity

Update scan/map/workflow counts and artifacts to consume the contract graph and
plan 015 lifecycle. Preserve a concise compatibility summary for users. Delete
old route-only grouping/reconciliation, duplicate schema-reference storage, and
superseded tests.

**Verify**: no active caller uses old reconciliation; full-stack lab remains
qualified under the new expected graph.

## Test plan

- Graph serialization and legacy map migration.
- Field/type/nullability/enum/validation parity.
- Error/status/auth/tenant evidence.
- UI loading/error/empty/success state coverage.
- Handler/service/entity lineage.
- Dynamic/unknown/unsupported classification.
- Finding deduplication and detector-specific verification.

## Done criteria

- [ ] Full-stack evidence spans UI state through database field where supported.
- [ ] Contract mismatches become source-anchored findings.
- [ ] Unknown evidence never reports parity.
- [ ] Route-only reconciliation and duplicate parsers are deleted.
- [ ] No code generation or live database access is introduced.
- [ ] Production-code delta and removed paths are reported.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- Plan 015 or 016 is incomplete.
- Framework evidence cannot distinguish unknown from absent.
- Static analysis would need to assert business/auth equivalence without proof.
- A documented public API prevents replacing `ProjectMap`; stop and specify a
  versioned deprecation before proceeding.

## Maintenance notes

Framework support is an adapter/corpus concern. The core graph and
reconciliation must remain framework-neutral and conservative.
