# Plan 016: Replace shallow extraction with adapter-driven application semantics

> **Executor instructions**: Build one semantic extraction path used by mapping,
> analysis, and runtime ownership. Move callers, then delete React-shaped regex
> fallbacks and global-name resolution. Do not leave a parallel adapter system.
> Run every gate and update `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- pyproject.toml uidetox/source_facts.py uidetox/frontend_semantics.py uidetox/frontend_map.py uidetox/fileset.py uidetox/visual_semantics.py tests/test_source_facts.py tests/test_frontend_mapping.py tests/test_visual_semantics.py tests/test_calibration_matrix.py`

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/014-calibration-and-qualification-matrix.md`
- **Category**: tech-debt
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

Imported HTTP clients, aliases, generated clients, query libraries, and
re-exports can disappear from endpoint evidence. Vue/Svelte/Astro files are
accepted by discovery but lack native semantic grammars. JSX render edges use
global component-name counts, so duplicate local names become synthetic
external components. Runtime findings then have selectors but no owning source.
These are one problem: source identity and behavior are not modeled end to end.

## Current state

- `uidetox/source_facts.py:51-56` registers JS/JSX, TS/TSX, and CSS-family AST
  grammars only.
- `uidetox/source_facts.py:499-589` recognizes exact `fetch`, exact
  `axios.<method>`, and direct same-file fetch wrappers.
- `uidetox/frontend_semantics.py:62-70` drops endpoint facts whose URL is
  unknown.
- `uidetox/frontend_map.py:36-68` discovers Vue/Svelte/Astro alongside
  JS/TS/JSX/TSX.
- `uidetox/frontend_map.py:542-584` resolves imports separately, then resolves
  rendered tags by global component-name cardinality.
- `uidetox/frontend_map.py:1041-1129` creates runtime nodes with `file=""` and
  no `source_targets`.
- `uidetox/visual_semantics.py:40-92` can use `source_targets` or adjacent
  file-bearing nodes, but excludes `runtime_text` and production runtime nodes
  provide neither source.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Source facts | `python -m pytest -q -W error tests/test_source_facts.py` | all pass |
| Maps/ownership | `python -m pytest -q -W error tests/test_frontend_mapping.py tests/test_visual_semantics.py` | all pass |
| Calibration | `python -m pytest -q -W error tests/test_calibration_matrix.py` | adapter cases meet expectations |
| Full | `python -m pytest -q -W error` | exit 0 |

## Scope

**In scope**:
- `uidetox/semantic_adapters.py` (create; protocol, registry, capability model)
- `uidetox/source_facts.py`
- `uidetox/frontend_semantics.py`
- `uidetox/frontend_map.py`
- `uidetox/fileset.py`
- `uidetox/visual_semantics.py`
- `pyproject.toml` only if a qualified parser dependency is required
- `tests/test_source_facts.py`
- `tests/test_frontend_mapping.py`
- `tests/test_visual_semantics.py`
- `tests/calibration/manifest.json`
- `tests/calibration/fixtures/**`
- `docs/decisions/semantic-adapters.md` (create)

**Out of scope**:
- Backend DTO/database lineage; plan 017 owns it.
- Browser interaction scenarios; plan 018 owns them.
- Mutating the target application to add source annotations.
- Claiming exact source ownership from heuristic-only evidence.

## Cleanup and replacement constraints

- One source-discovery and semantic-extraction path.
- Delete `_extract_*` regex fallbacks in `frontend_map.py` once adapters cover
  their contracts.
- Replace global component-name resolution with module/export identity; delete
  the ambiguous-name external-node fallback except for truly external symbols.
- Keep `source_facts.py` as shared parse lifecycle or fold it into the adapter
  module; do not duplicate parser caches/walkers.
- Add parser dependencies only after plan 014 proves Python/platform support.
- Report production line counts and deleted helper count.

## Git workflow

- Branch: `codex/016-application-semantics`
- Commit by contract: adapter API, JS/TS symbol graph, framework adapters,
  runtime ownership, cleanup.
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Characterize semantic identity and capability

Add corpus cases for:

- imported Axios instances and method aliases;
- imported/re-exported request wrappers;
- generated-client and RTK Query/TanStack/Apollo/`ky`-style calls;
- static and dynamic URLs;
- two modules exporting the same component name with one explicitly imported;
- aliased/default/named component imports;
- Vue/Svelte/Astro components, routes, actions, states, and embedded scripts;
- runtime selectors that have unique, ambiguous, and absent source matches.

**Verify**: current gaps fail exactly their intended cases.

### Step 2: Define a deep adapter contract

Create one adapter protocol returning immutable facts for:

- module/import/export/local binding identity;
- components and render relationships;
- routes, regions, actions, and UI states;
- network calls with client family, method, URL expression, request/response
  type references, and unresolved evidence;
- static selector/source signatures;
- capability status (`native`, `degraded`, `unsupported`) with reason and
  confidence.

Registry selection must be deterministic by extension/framework evidence.
Unknown calls remain unresolved facts; they are never silently dropped.

**Verify**: registry and capability serialization tests pass.

### Step 3: Consolidate JS/TS extraction around symbol identity

Extend the existing Tree-sitter parse lifecycle to retain import bindings,
exports, call targets, wrapper definitions, and re-export chains. Resolve
common client shapes through symbol flow rather than spelling alone. Bound
cross-file traversal and emit unresolved provenance on cycles or dynamic
construction.

Replace the current same-file HTTP wrapper scan and duplicate frontend-map
regex endpoint extraction.

**Verify**: JS/TS client calibration cases pass; cyclic imports terminate
deterministically.

### Step 4: Add framework adapters without false support claims

Implement Vue, Svelte, and Astro adapters using parser backends qualified by
plan 014. Extract embedded script through the shared JS/TS adapter and template
component/action/region facts through the framework grammar. If a maintained
backend cannot support every declared Python/platform target, keep that
framework explicitly degraded and stop before adding an unqualified core
dependency.

**Verify**: native cases pass where backend exists; missing backend reports
degraded/unsupported, never clean.

### Step 5: Resolve component topology through lexical bindings

Represent component identity as `(module, export, local binding)`. Resolve each
rendered tag through the importing module before any external-component
fallback. Preserve external nodes only for package imports or truly unresolved
symbols. Remove global name-count routing.

**Verify**: duplicate `Button` fixture maps to the imported module; no synthetic
external node exists.

### Step 6: Link runtime elements to source with provenance

Build a source-signature index from routes, component ownership, stable IDs,
test/data attributes, static classes, and adapter-emitted selector signatures.
Resolve runtime elements to source targets using explicit exact matches first,
then unique heuristic matches. Store `source_targets`, confidence, and
provenance on runtime region/action/text nodes. Include `runtime_text` in visual
semantic lookup. Ambiguous matches remain unresolved.

Support an optional application-provided runtime source hook as highest
confidence, but do not require or inject it into target code.

**Verify**: production `_merge_runtime_evidence` path—not manually constructed
test nodes—produces source-owned visual regions.

### Step 7: Delete superseded extraction and document capability truth

Remove old regex fallback, global-name lookup, and duplicate parser/discovery
helpers. Update map evidence to expose adapter/capability status and counts.
Record dependency direction in the ADR:
parser lifecycle → semantic adapters → application map → consumers.

**Verify**: grep shows no removed fallback symbols; focused, calibration, and
full suites pass.

## Test plan

- Import/export/alias/re-export identity.
- HTTP/query/generated client call propagation.
- Dynamic/unresolved calls retained with evidence.
- Framework-native and degraded capability cases.
- Duplicate component names and external packages.
- Runtime action/region/text source ownership and ambiguity.
- Cross-file cycles, ordering, and deterministic serialization.

## Done criteria

- [ ] One adapter path supplies all semantic consumers.
- [ ] Common imported client calls remain visible.
- [ ] Framework support is native or explicitly degraded/unsupported.
- [ ] Render topology uses module/export identity.
- [ ] Runtime findings carry source targets or explicit unresolved provenance.
- [ ] React-shaped fallback and global-name resolution are deleted.
- [ ] Production-code delta and deleted helpers are reported.
- [ ] Full suite passes; plan status updated.

## STOP conditions

- No parser backend supports required Python/platform versions.
- Source ownership would require unstable framework internals or target-app
  mutation.
- Public JSON consumers require undocumented legacy ambiguity.
- Migration creates two active parser caches or semantic graphs.

## Maintenance notes

New frameworks and client families extend this registry and plan 014 corpus.
Do not add recognition branches directly to map/workflow commands.
