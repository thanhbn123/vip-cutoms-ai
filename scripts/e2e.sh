#!/usr/bin/env bash
# Browser E2E against the real stack on the TEST database (reset from zero): migrate → seed demo case → API → Vite → Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export APP_ENV=test AI_PROVIDER=mock
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test}"
export APP_SECRET_KEY="${APP_SECRET_KEY:-e2e-only-secret-key-not-for-any-real-environment-000}"
export SEED_DEMO_PASSWORD="${SEED_DEMO_PASSWORD:-demo-acceptance-2026}"
export LOCAL_STORAGE_DIR="${LOCAL_STORAGE_DIR:-$ROOT/local-data/e2e-uploads}"
API_PORT="${API_PORT:-8000}"; WEB_PORT="${WEB_PORT:-5173}"
PY="${E2E_PYTHON:-$ROOT/apps/api/.venv/bin/python}"   # CI sets E2E_PYTHON=python (no venv)
mkdir -p "$ROOT/local-data"   # gitignored; absent in a fresh clone, and the log redirections below would abort under set -e
cd "$ROOT/apps/api"
$PY -c "from sqlalchemy import create_engine,text;e=create_engine('$DATABASE_URL');c=e.connect();c.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'));c.commit()"
$PY -m alembic upgrade head
$PY scripts/seed_demo.py --with-case
$PY -m uvicorn app.main:app --port "$API_PORT" >"$ROOT/local-data/e2e-api.log" 2>&1 & API_PID=$!
cd "$ROOT/apps/web"
VITE_API_PROXY="http://localhost:$API_PORT" npx vite --port "$WEB_PORT" --strictPort >"$ROOT/local-data/e2e-web.log" 2>&1 & WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT
for i in $(seq 1 30); do curl -sf "http://localhost:$API_PORT/ready" >/dev/null && curl -sf "http://localhost:$WEB_PORT/" >/dev/null && break; sleep 1; done
curl -sf "http://localhost:$API_PORT/ready"; echo
E2E_BASE_URL="http://localhost:$WEB_PORT" npx playwright test "$@"
