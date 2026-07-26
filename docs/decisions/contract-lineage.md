# ADR: Versioned full-stack contract lineage

Status: Accepted
Date: 2026-07-25

## Decision

UIdetox stores one schema-version-2 contract graph inside the frontend-map
artifact. Typed nodes represent UI actions and states, client calls, request,
response, and error schemas and fields, routes, handlers, services,
authorization requirements, entities, and database fields. Directed edges
carry provenance, confidence, a source anchor, and capability status.

`project_map.py` is the stable orchestration facade. `contract_graph.py` owns
the one canonical model, graph construction, version migration, and
reconciliation; `contract_adapters.py` owns qualified backend extraction.
`frontend_map.py` projects plan-016 application semantics into frontend graph
facts. Commands, workflow artifacts, redesigns, prototype briefs, and fixture
verification consume the graph and canonical plan-015 `Finding` objects. They
do not rebuild a route-only operation view.

Schema version 1 has one read-only migration adapter. Loads convert legacy
operations directly into graph nodes and edges; every write emits only version
2. The old operation model, reconciler, schema-reference cache, and derived
compatibility properties are deleted.

## Evidence states and reconciliation

`present`, `absent`, `unknown`, and `contradictory` are distinct capability
states. Present-versus-absent is a mismatch. Unsupported, dynamic, incomplete,
or contradictory extraction produces an investigative coverage gap. Unknown
evidence never proves compatibility.

Every source observation retains its own identity and anchor. Exact duplicate
observations may be removed, but same-route observations and distinct DTO
shapes are never unioned or resolved by first-wins selection. Semantically
identical DTO shapes collapse to one schema node while retaining every type
identity. Every OpenAPI success response shape remains a separate,
status-anchored node; statusless evidence is compatible with multiple variants
only when those variants have the same shape. Reconciliation deduplicates only
equivalent causal findings. Lineage uses explicit parent references, so sibling
services and entities cannot become an accidental chain.

Reconciliation traverses graph edges and compares the smallest compatible
frontend/backend slice in this order:

1. normalized route and method;
2. request and response fields, types, requiredness, nullability, enums, and
   validation attributes;
3. UI-owner-specific loading/error/empty/success lifecycle evidence;
4. authentication, authorization, and tenant evidence;
5. operation-specific success statuses and error-envelope shapes;
6. mutation-specific cache invalidation evidence.

Each difference emits one source-anchored canonical finding. No runtime
database access, code generation, DTO generation, or business-equivalence
claim is made.

## Adapter qualification

OpenAPI supplies referenced request, response, error, status, and security
evidence. Qualified FastAPI/Pydantic/SQLAlchemy source supplies
route-to-handler-to-service-to-entity fields. Qualified JavaScript framework
routes supply static handler evidence. TypeScript object contracts are bounded
to simple interface and object-alias declarations selected by the semantic
adapter; unsupported or nested dynamic shapes remain unknown.

UI lifecycle facts attach through the network call's callable owner or one
unambiguous JSX action-to-callable owner. Calls from low-level modules do not
inherit unrelated module UI state, and multiple calls under one UI owner remain
unknown instead of receiving shared lifecycle evidence. Python field and
security inference likewise requires import provenance: SQLAlchemy `Mapped[T]`
and FastAPI `Depends` aliases are recognized only when their bindings resolve
to the qualified framework imports.

The calibration corpus includes typed-shape parity with an explicit evidence
gap, field-type, enum, requiredness, and authentication mismatches, plus an
incomplete frontend contract. Prisma and route-less backend fixtures remain
explicitly degraded until their adapters are qualified.

## Consequences

Graph artifacts are larger than route summaries but have one canonical model.
Adding a framework requires adapter evidence and positive, negative, and
unknown calibration cases. Consumers use `contract_mismatch` and
`coverage_gap` summaries while retaining typed findings for remediation.
