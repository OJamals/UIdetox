#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION="${1:-$(mktemp -d /tmp/uidetox-fullstack-slop-lab.XXXXXX)}"

if [[ -d "${DESTINATION}" ]] && [[ -n "$(find "${DESTINATION}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Destination must be empty: ${DESTINATION}" >&2
  exit 1
fi

mkdir -p "${DESTINATION}"
rsync -a \
  --exclude .hallmark \
  --exclude .ruff_cache \
  --exclude .uidetox \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude data \
  --exclude dist \
  --exclude node_modules \
  "${SOURCE_ROOT}/" "${DESTINATION}/"

printf '%s\n' "${DESTINATION}"
