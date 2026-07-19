# NexusFlow AI — Full-stack slop lab

Runnable beta fixture for UIdetox. It is deliberately bad.

The app combines a React/Vite frontend, FastAPI backend, REST API, OpenAPI document,
and SQLite database. Six product routes and reusable components create enough
structure for AST parsing, import/ownership mapping, runtime observation, intent
provenance, full-stack operation reconciliation, source-aware redesign planning,
proposal comparison, and disposable prototype briefs.

## Deliberate defects

This fixture is not an example to copy. `beta-expectations.json` is the contract.
It records intentional visual, interaction, accessibility, architecture, DTO, copy,
and API-parity defects. Important examples:

- purple/blue/pink gradients, glass cards, Inter everywhere, giant shadows and pills
- repeated cards, centred hero, emoji icons, gradient text, AI nav/footer
- `transition: all`, bounce loops, removed focus outlines, weak responsive behavior
- placeholder-only forms, celebratory toasts, low-value confirmation dialogs
- duplicated frontend/backend models and a process-global SQLite connection
- one frontend-only API operation, one backend-only operation, one method mismatch

The app must remain functional. UIdetox should report the defects, preserve route/API
contracts, and create redesign plans whose `source_targets` cover affected components.
The generic runtime API wrapper is deliberately opaque to static transport extraction;
`frontend/src/api/semantic-contract-probes.ts` supplies uncalled literal operation
evidence so parity reconciliation has a stable, explicit beta oracle.

## Install

```bash
cd examples/fullstack-slop-lab
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install
```

## Run

Terminal 1:

```bash
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

Terminal 2:

```bash
npm run dev
```

Open `http://127.0.0.1:4173`.

## Verify application behavior

```bash
npm run build
.venv/bin/python -m pytest -q tests
```

## Exercise UIdetox

Point `UIDETOX_BIN` at a source checkout when testing unreleased code:

```bash
export UIDETOX_BIN=/absolute/path/to/UIdetox/.venv/bin/uidetox
./scripts/prepare_uidetox.sh
```

UIdetox intentionally resolves a nested working directory to its containing Git
root. Because this fixture lives inside the UIdetox repository, materialize it as
an independent beta project before testing project-root tooling detection:

```bash
SANDBOX="$(./scripts/materialize_sandbox.sh)"
cd "$SANDBOX"
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install
./scripts/prepare_uidetox.sh
```

With both servers running:

```bash
"$UIDETOX_BIN" scan --path frontend
"$UIDETOX_BIN" map frontend \
  --runtime \
  --url http://127.0.0.1:4173 \
  --screenshots \
  --output .uidetox/frontend-map.json \
  --json
"$UIDETOX_BIN" redesign frontend \
  --map-file .uidetox/frontend-map.json \
  --variants 3 \
  --output .uidetox/redesigns.json \
  --json
"$UIDETOX_BIN" compare --file .uidetox/redesigns.json
python scripts/inspect_artifacts.py
```

Then select a proposal:

```bash
"$UIDETOX_BIN" prototype <proposal-id> \
  --file .uidetox/redesigns.json \
  --output .uidetox/prototype-brief.md
npm run verify:artifacts
```

Runtime state, screenshots, database files, dependencies, and build output are ignored.
Source, seed logic, expectations, and tests remain stable for repeatable baselines.
