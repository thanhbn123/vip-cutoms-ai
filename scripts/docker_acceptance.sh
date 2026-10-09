#!/usr/bin/env bash
# Owner acceptance against the running compose stack: seed demo tenant+case inside the api container → Playwright (reads the
# untouched BLOCKED demo case) → HTTP flow A–P (creates and drives its own cases). Writes artifacts/test-results/docker-acceptance.txt.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
A="$ROOT/artifacts/test-results"; mkdir -p "$A"
C=(docker compose -f infra/docker-compose.yml --env-file .env)
export SEED_DEMO_PASSWORD="${SEED_DEMO_PASSWORD:-$(python3 -c 'import secrets;print(secrets.token_urlsafe(16))')}"
API="${DOCKER_API_URL:-http://localhost:8000}"; WEB="${DOCKER_WEB_URL:-http://localhost:5173}"
{
  echo "# docker-acceptance · $(date -u +%FT%TZ) · $(git rev-parse --short HEAD) · api $API · web $WEB"
  echo "## 1. seed demo tenant + V12 case inside the api container"
  "${C[@]}" exec -T -e SEED_DEMO_PASSWORD="$SEED_DEMO_PASSWORD" api python scripts/seed_demo.py --with-case 2>&1 | tail -2
  echo "## 2. Playwright against the Docker web (seeded case must be BLOCKED)"
  ( cd apps/web && E2E_BASE_URL="$WEB" PW_CHROMIUM_PATH="${PW_CHROMIUM_PATH:-/opt/pw-browsers/chromium}" npx playwright test 2>&1 | grep -vE 'agent-proxy|google|gvt1|For details' | tail -4 ); echo "playwright_exit=${PIPESTATUS[0]}"
  echo "## 3. HTTP acceptance A–P (scripts/acceptance_http.py)"
  BASE_URL="$API" apps/api/.venv/bin/python scripts/acceptance_http.py 2>&1; echo "acceptance_exit=$?"
  echo "## containers after flow"; "${C[@]}" ps --format 'table {{.Name}}\t{{.Status}}'
  echo "restart counts: $(for c in $("${C[@]}" ps -q); do docker inspect --format '{{.Name}}={{.RestartCount}}' "$c"; done | tr '\n' ' ')"
  echo "uploaded documents in volume: $("${C[@]}" exec -T api sh -c 'find /data/uploads -type f | wc -l')"
} 2>&1 | tee "$A/docker-acceptance.txt"
