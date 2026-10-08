#!/usr/bin/env bash
# Full staging acceptance from a CLIENT machine (or the host) against a running stack.
#   BASE_URL=https://staging.host WEB_URL=https://staging.host SEED_DEMO_PASSWORD=... [COMPOSE="docker compose -p vip-customs-ai-staging -f infra/staging/docker-compose.staging.yml --env-file infra/staging/.env"] bash scripts/staging/acceptance.sh
# COMPOSE is needed for the host-side parts (seed, restart/persistence, backup/restore, logs). Writes artifacts/test-results/staging-acceptance.txt.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"
: "${BASE_URL:?}"; WEB_URL="${WEB_URL:-$BASE_URL}"
export SEED_DEMO_PASSWORD="${SEED_DEMO_PASSWORD:?}"
PY="${PY:-$ROOT/apps/api/.venv/bin/python}"; A="$ROOT/artifacts/test-results"; mkdir -p "$A"; OUT="${OUT:-$A/staging-acceptance.txt}"
CURL=(curl -sS --max-time 15); [ "${E2E_INSECURE_TLS:-0}" = 1 ] && CURL+=(-k)
read -r -a COMPOSE_ARR <<< "${COMPOSE:-}"   # word-split once; never eval (container-side quoting must survive)
compose() { [ -n "${COMPOSE:-}" ] && "${COMPOSE_ARR[@]}" "$@"; }
ms() { "${CURL[@]}" -o /dev/null -w '%{time_total}' "$1" | awk '{printf "%.0f", $1*1000}'; }
{
  echo "# staging-acceptance · $(date -u +%FT%TZ) · target $BASE_URL (web $WEB_URL) · repo $(git rev-parse --short HEAD)"
  echo "## 1. external health"; "${CURL[@]}" -w ' [%{http_code}]\n' "$BASE_URL/health"; "${CURL[@]}" -w ' [%{http_code}]\n' "$BASE_URL/ready"; "${CURL[@]}" -o /dev/null -w "frontend [%{http_code}]\n" "$WEB_URL/"
  case "$BASE_URL" in https://*) echo "TLS: $(curl -sS -o /dev/null -w '%{ssl_verify_result}' --max-time 15 "$BASE_URL/health" 2>&1 | sed 's/^0$/certificate VALID (verify_result=0)/')"; echo "http→https redirect: $(curl -sS -o /dev/null -w '%{http_code} → %{redirect_url}' --max-time 15 "${BASE_URL/https:/http:}/health" 2>&1)";; *) echo "TLS: TLS_PENDING / IP_ACCEPTANCE (plain http target)";; esac
  echo "## 2. seed demo data (host side)"; compose exec -T -e APP_ENV=development -e SEED_DEMO_PASSWORD="$SEED_DEMO_PASSWORD" api python scripts/seed_demo.py --with-case 2>&1 | tail -2 || echo "seed skipped (no COMPOSE) — demo tenant must already exist"
  echo "## 3. Playwright (browser) against $WEB_URL"; ( cd apps/web && E2E_BASE_URL="$WEB_URL" PW_CHROMIUM_PATH="${PW_CHROMIUM_PATH:-}" npx playwright test 2>&1 | grep -vE 'agent-proxy|google|gvt1|For details' | tail -4 ); echo "playwright_exit=${PIPESTATUS[0]}"
  echo "## 4. acceptance flow A–P over HTTP"; BASE_URL="$BASE_URL" "$PY" scripts/acceptance_http.py 2>&1; echo "acceptance_exit=$?"
  echo "## 5. negative / security tests"; BASE_URL="$BASE_URL" "$PY" scripts/staging/negative_tests.py 2>&1; echo "negative_exit=$?"
  echo "## 6. demo labels"; TOK=$("${CURL[@]}" -X POST "$BASE_URL/api/v1/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"operator@demo.local\",\"password\":\"$SEED_DEMO_PASSWORD\"}" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'); "${CURL[@]}" "$BASE_URL/api/v1/knowledge/notice" -H "Authorization: Bearer $TOK"; echo
  echo "## 7. performance smoke (sequential, light)"; for p in /health /ready /api/v1/cases /api/v1/dashboard/summary /api/v1/knowledge/datasets; do t=0; for i in 1 2 3 4 5; do t=$((t + $(ms "$BASE_URL$p"))); done; echo "$p avg $((t/5)) ms (5 req, auth: none for health/ready)"; done 2>/dev/null | sed 's#/api/v1/[a-z/]*#&#'
  if [ -n "${COMPOSE:-}" ]; then
    echo "## 8. restart / persistence"; N0=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from cases"'); compose restart >/dev/null 2>&1; sleep 8; for i in $(seq 1 30); do "${CURL[@]}" -f "$BASE_URL/ready" >/dev/null 2>&1 && break; sleep 2; done
    echo "after restart: ready $("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE_URL/ready"), cases before=$N0 after=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from cases"')"
    compose down >/dev/null 2>&1; compose up -d >/dev/null 2>&1; for i in $(seq 1 45); do "${CURL[@]}" -f "$BASE_URL/ready" >/dev/null 2>&1 && break; sleep 2; done
    echo "after down/up (volumes kept): ready $("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE_URL/ready"), cases=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from cases"'), uploads=$(compose exec -T api sh -c 'find /data/uploads -type f | wc -l')"
    echo "restart counts: $(for c in $(compose ps -q); do docker inspect --format '{{.Name}}={{.RestartCount}}' "$c"; done | tr '\n' ' ')"
    echo "## 9. backup + restore test (temporary database, live DB untouched)"; mkdir -p backups; F="backups/staging-$(date +%F-%H%M).dump"; compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$F"; echo "backup $F size=$(wc -c < "$F") bytes"
    compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE IF EXISTS restore_test" -c "CREATE DATABASE restore_test"' && compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_test' < "$F" && echo "RESTORE_TEST cases=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d restore_test -tAc "select count(*) from cases"') audit=$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d restore_test -tAc "select count(*) from audit_events"')"; compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE restore_test"'
    echo "## 10. log / secret review"; compose logs --no-color --tail=300 > "$A/.staging-logs.full" 2>&1; echo "lines=$(wc -l < "$A/.staging-logs.full") errors=$(grep -ciE 'traceback|exception|fatal|restarting' "$A/.staging-logs.full")"; echo "secret-pattern hits: $(grep -ciE 'password=|secret_key|authorization: bearer|BEGIN (RSA|EC|OPENSSH) PRIVATE' "$A/.staging-logs.full")"; echo "$SEED_DEMO_PASSWORD" | grep -qF -f - "$A/.staging-logs.full" && echo "SEED PASSWORD LEAKED" || echo "seed password not in logs"
  else echo "## 8–10 skipped (set COMPOSE to run restart/persistence, backup/restore and log review on the host)"; fi
} 2>&1 | tee "$OUT"
