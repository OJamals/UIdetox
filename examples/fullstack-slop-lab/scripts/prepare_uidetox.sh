#!/usr/bin/env bash
set -euo pipefail

UIDETOX_BIN="${UIDETOX_BIN:-uidetox}"

"${UIDETOX_BIN}" setup \
  --design-variance 6 \
  --motion-intensity 3 \
  --visual-density 7 \
  --dev-server http://127.0.0.1:4173 \
  --product-goal "Provide a runnable B2B operations fixture that demonstrates UIdetox baseline-to-remediation work while preserving verified frontend, API, and database behavior." \
  --audience "UIdetox maintainers, beta testers, and agent-harness evaluators" \
  --primary-job "Verify that UIdetox can map intent, correct structural and visual defects, preserve routes, and keep frontend operations aligned with API and database contracts." \
  --tone "Calm, precise operational confidence" \
  --genre "Dense editorial operations ledger" \
  --page-kind application \
  --brand "NexusFlow" \
  --preserve "React route paths and navigation destinations" \
  --preserve "FastAPI endpoint paths and SQLite-backed data behavior" \
  --preserve "Recorded pre-remediation issue and parity evidence" \
  --preserve "Synthetic provenance and no-production-data guarantee in fixture-intent.json" \
  --constraint "Keep the fixture runnable while structural and visual remediation evolves" \
  --constraint "Keep frontend operations aligned with backend methods and DTOs"
