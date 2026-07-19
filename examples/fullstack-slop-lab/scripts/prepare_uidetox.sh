#!/usr/bin/env bash
set -euo pipefail

UIDETOX_BIN="${UIDETOX_BIN:-uidetox}"

"${UIDETOX_BIN}" setup \
  --design-variance 2 \
  --motion-intensity 9 \
  --visual-density 8 \
  --dev-server http://127.0.0.1:4173 \
  --audience "UIdetox maintainers and beta testers" \
  --primary-job "Inspect semantic mapping, provenance, redesign planning, and verification" \
  --tone "maximal stereotypical AI SaaS slop" \
  --genre "operational workspace" \
  --page-kind page \
  --brand "NexusFlow AI" \
  --preserve "React route paths and navigation destinations" \
  --preserve "FastAPI endpoint paths and SQLite-backed data behavior" \
  --preserve "Deliberate operation mismatches listed in beta-expectations.json" \
  --constraint "Keep the fixture runnable while redesign proposals replace visual structure" \
  --constraint "Do not silently repair deliberate beta findings before recording a baseline"
