#!/usr/bin/env bash
set -euo pipefail
# Run from the Week 17 folder. The default assumes sibling folders Week16/ and "Week 17/".
SOURCE="${1:-../Week16}"
if [[ ! -d "$SOURCE/backend" || ! -d "$SOURCE/frontend" ]]; then
  echo "Cannot find Week 16 backend/frontend at: $SOURCE" >&2
  echo "Usage: ./scripts/carry_forward_week16.sh [path-to-Week16]" >&2
  exit 1
fi
for item in backend frontend docs tests; do
  if [[ -d "$SOURCE/$item" ]]; then
    mkdir -p "$item"
    cp -an "$SOURCE/$item/." "$item/"
  fi
done
if [[ -f "$SOURCE/docker-compose.yml" ]]; then cp -n "$SOURCE/docker-compose.yml" ./docker-compose.yml || true; fi
if [[ -f "$SOURCE/backend/.env.example" && ! -f backend/.env.example ]]; then cp "$SOURCE/backend/.env.example" backend/.env.example; fi
echo "Week 16 source carried forward. Review path/config differences, then run: uv lock && uv sync"
