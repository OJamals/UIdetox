# NexusFlow — Full-stack remediation lab

Runnable synthetic qualification fixture for UIdetox. It retains a reproducible
record of its deliberately poor baseline and contains no production customer data.

The app combines a React/Vite frontend, FastAPI backend, REST API, OpenAPI document,
and SQLite database. Fifteen product route patterns and reusable components create enough
structure for AST parsing, import/ownership mapping, runtime observation, intent
provenance, full-stack operation reconciliation, source-aware redesign planning,
proposal comparison, and disposable prototype briefs.

## Baseline and remediation evidence

This fixture is not a production product recommendation. `beta-expectations.json`
is the current qualification contract and `fixture-intent.json` retains the original
baseline counts. The baseline included:

- purple/blue/pink gradients, glass cards, Inter everywhere, giant shadows and pills
- repeated cards, centred hero, emoji icons, gradient text, AI nav/footer
- `transition: all`, bounce loops, removed focus outlines, weak responsive behavior
- placeholder-only forms, celebratory toasts, low-value confirmation dialogs
- duplicated frontend/backend models and a process-global SQLite connection
- ten frontend-only operations, eight backend-only operations, one method mismatch,
  and 212 deterministic analyzer findings
- storage-shaped account/connector payloads cast into incompatible frontend DTOs
- fixed-height customer records, connector cards, route walls, and provenance panels
- approval and journey contracts split across incompatible route vocabularies and DTOs
- fixed-width governance queues and journey canvases that clip on narrow screens

The remediated target is zero operation-parity findings and zero deterministic analyzer
findings while every route and backed action remains functional. The generic runtime API
wrapper is the canonical transport boundary. UIdetox resolves its literal call sites
through the local wrapper into concrete method/path operations, so parity evidence comes
from executable application code rather than a duplicate probe manifest.

## Intent and provenance

`fixture-intent.json` is the canonical product-intent and provenance manifest. It
records the fixture's product goal, audience, primary job, tone, genre, design dials,
preservation contract, constraints, anti-goals, route surface, lineage, source policy,
and explicit no-production-data guarantee. `scripts/prepare_uidetox.sh` installs that
same intent into UIdetox, while `/fixture-provenance` makes it visible inside the app.

The fixture is synthetic. Its original copy and layouts reproduced recurring
AI-generated SaaS habits; the current interface records the result of a UIdetox-guided
editorial operations redesign. Organizations, people, metrics, URLs, invoices,
notifications, and events are fictional seed data.

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
.venv/bin/playwright install chromium
npm run test:e2e
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
