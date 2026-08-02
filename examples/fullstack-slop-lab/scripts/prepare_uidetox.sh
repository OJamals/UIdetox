#!/usr/bin/env bash
set -euo pipefail

UIDETOX_BIN="${UIDETOX_BIN:-uidetox}"

"${UIDETOX_BIN}" setup \
  --design-variance 8 \
  --motion-intensity 6 \
  --visual-density 8 \
  --dev-server http://127.0.0.1:4173 \
  --product-goal "Provide a runnable B2B operations stress fixture in its remediated state, retaining historical multi-layer slop evidence while preserving verified frontend, API, and database behavior." \
  --audience "UIdetox maintainers, beta testers, and agent-harness evaluators" \
  --primary-job "Verify that UIdetox can map and validate a remediated full-stack result against explicit historical slop provenance without regressing routes, interactions, or contracts." \
  --tone "Calm, precise operational confidence" \
  --genre "Dense editorial operations command center" \
  --page-kind application \
  --brand "NexusFlow" \
  --preserve "React route paths, navigation destinations, and historical contract-canary provenance" \
  --preserve "FastAPI endpoint paths, typed response contracts, and imported APIRouter topology" \
  --preserve "Recorded pre-remediation issue and parity evidence" \
  --preserve "Synthetic provenance and no-production-data guarantee in fixture-intent.json" \
  --constraint "Keep the fixture runnable while structural and visual remediation evolves" \
  --constraint "Keep historical route, method, DTO, lineage, layout, and accessibility canaries isolated in intentional-slop.json"
