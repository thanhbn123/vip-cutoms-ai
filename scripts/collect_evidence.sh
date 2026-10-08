#!/usr/bin/env bash
# Runs every local check and writes trimmed, real outputs to artifacts/test-results/ (summaries only; no large logs).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; A="$ROOT/artifacts/test-results"; mkdir -p "$A"
stamp() { echo "# $1 · $(date -u +%Y-%m-%dT%H:%M:%SZ) · develop $(git -C "$ROOT" rev-parse --short HEAD)"; }
run() { # name, cmd...  → file with header, exit code and last 40 lines
  local name=$1; shift; local f="$A/$name.txt"; { stamp "$name"; echo "\$ $*"; } >"$f"
  ( cd "$ROOT" && "$@" ) >"$A/.$name.full" 2>&1; local rc=$?
  { echo "exit_code=$rc"; echo "----- last lines -----"; tail -n 40 "$A/.$name.full"; } >>"$f"; rm -f "$A/.$name.full"
  printf '%-22s exit=%s\n' "$name" "$rc"; return $rc
}
cd "$ROOT"
run lint             bash -o pipefail -c "cd apps/api && .venv/bin/ruff check app tests scripts && echo RUFF_OK"
run typecheck        bash -o pipefail -c "cd apps/web && npx tsc -b && echo TSC_OK"
run backend-pytest   bash -o pipefail -c "cd apps/api && .venv/bin/pytest -q 2>&1 | tail -5"
run frontend-vitest  bash -o pipefail -c "cd apps/web && npx vitest run 2>&1 | tail -8"
run build            bash -o pipefail -c "cd apps/web && npx vite build 2>&1 | tail -6"
run migration-test   bash -o pipefail -c "cd apps/api && export DATABASE_URL=postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test && .venv/bin/python -c \"from sqlalchemy import create_engine,text;e=create_engine('postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test');c=e.connect();c.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'));c.commit()\" && .venv/bin/alembic upgrade head 2>&1 | tail -12 && echo HEADS=\$(.venv/bin/alembic heads | wc -l) && .venv/bin/alembic downgrade 0008_copilot_memory 2>&1 | tail -2 && .venv/bin/alembic upgrade head 2>&1 | tail -2 && .venv/bin/alembic current"
run integration-e2e  bash -o pipefail -c "PW_CHROMIUM_PATH=\${PW_CHROMIUM_PATH:-/opt/pw-browsers/chromium} bash scripts/e2e.sh 2>&1 | grep -vE 'agent-proxy|google|gvt1|For details' | tail -15"
run api-smoke        bash -o pipefail -c "cd apps/api && export APP_ENV=test DATABASE_URL=postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test APP_SECRET_KEY=smoke-only-secret-key-not-for-any-real-environment-000 LOCAL_STORAGE_DIR=\$PWD/../../local-data/smoke && (.venv/bin/uvicorn app.main:app --port 8791 >/dev/null 2>&1 & echo \$! > /tmp/claude-0/smoke.pid) && for i in \$(seq 1 20); do curl -sf localhost:8791/health >/dev/null && break; sleep 1; done && echo HEALTH: \$(curl -s localhost:8791/health) && echo READY: \$(curl -s localhost:8791/ready) && TOK=\$(curl -s -X POST localhost:8791/api/v1/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"reviewer@demo.local\",\"password\":\"demo-acceptance-2026\"}' | .venv/bin/python -c 'import sys,json;print(json.load(sys.stdin)[\"access_token\"])') && echo CASES: \$(curl -s localhost:8791/api/v1/cases -H \"Authorization: Bearer \$TOK\" | .venv/bin/python -c 'import sys,json;print([(c[\"case_no\"],c[\"status\"]) for c in json.load(sys.stdin)])') && echo UNAUTH: \$(curl -s -o /dev/null -w '%{http_code}' localhost:8791/api/v1/cases); kill \$(cat /tmp/claude-0/smoke.pid)"
run secret-scan      bash scripts/secret_scan.sh
if [ "${SKIP_DOCKER:-0}" != 1 ] && docker info >/dev/null 2>&1; then run docker-smoke bash scripts/docker_smoke.sh; else echo "docker-smoke            SKIPPED (no daemon or SKIP_DOCKER=1; see scripts/docker_smoke.sh)"; fi
echo "evidence written to $A"
