# ADR: Application semantic adapters

Status: Accepted
Date: 2026-07-25

## Decision

UIdetox builds application semantics through one dependency direction:

`source_facts parser lifecycle → semantic adapters → application map → consumers`

`source_facts.py` owns Tree-sitter grammar loading, parsing, walking, and
parser-independent immutable facts. `semantic_adapters.py` selects one adapter
per source file, attaches capability metadata to that canonical `SourceFacts`
payload, and resolves cross-file component and network behavior.
`frontend_map.py` only projects that application graph into its public
artifact. Runtime and visual consumers use the same graph's source-signature
ownership evidence.

No command, map consumer, or framework integration may create another parser
cache, source discovery walk, global component-name index, or regex endpoint
fallback.

One immutable application index owns module paths, extension candidates,
network symbols, routes, and selector-to-source signatures. Module candidate
and runtime ownership lookups reuse it. Import/export traversal reads canonical
per-module facts through that index; consumers must not add parallel caches.

## Capability contract

Every module reports:

- `native`: qualified grammar supplies the declared semantics;
- `degraded`: bounded extraction supplies partial evidence and states why;
- `unsupported`: no qualified adapter exists.

JavaScript and TypeScript use qualified Tree-sitter grammars. Vue, Svelte, and
Astro remain `degraded`: embedded scripts use the shared JS/TS parser while
template evidence is conservative. This avoids claiming native framework
support without a maintained parser backend qualified across supported Python
and platform targets.

Core Tree-sitter is constrained to `>=0.25,<0.26`. With the shipped grammar
ABI, 0.24 rejects language version 15, while 0.26 corrupts node positions and
bus-errors on the full-stack qualification fixture. Core 0.25.2 passes that
reproducer, the bounded-source-anchor regression, and the complete suite.

Unknown network calls remain unresolved facts with provenance. Import and
re-export traversal is bounded by visited `(module, export)` identities, so
cycles terminate deterministically.
TypeScript generic-call evidence is bounded and classified by client-family
conventions. Callable type parameters substitute concrete call arguments
through imported and re-exported wrappers; this records source type references
without claiming the backend DTO lineage owned by the next phase.

Backend capabilities obey the same provenance rule. A generic FastAPI
`Depends(...)` is dependency evidence, not authentication. Authentication is
present only for qualified OpenAPI security or imported FastAPI `Security`
bound to an imported security provider. Persistence lineage requires an
explicit table declaration or qualified SQLAlchemy declarative-base
provenance; an arbitrary local class named `Base` is not an entity.

## Source ownership

Render topology resolves lexical import bindings and module exports. Duplicate
component names do not influence ownership. Package imports become external
nodes; unresolved local symbols remain explicitly unresolved.

Runtime ownership follows this precedence:

1. application-provided `data-uidetox-source` path;
2. unique exact static selector (`id`, `data-testid`, or `data-test`);
3. route-disambiguated exact selector candidates;
4. unique or route-disambiguated class/tag heuristic;
5. unique route context at low confidence;
6. ambiguous or unresolved provenance with no `source_targets`.

UIdetox never injects source annotations into target applications.

## Consequences

New frameworks and client families extend the adapter registry and calibration
corpus. Public map evidence exposes adapter status, reasons, counts, confidence,
and resolution issues. Compatibility projections may reshape adapter output,
but cannot parse or infer an independent semantic graph.
