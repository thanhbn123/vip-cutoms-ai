#!/usr/bin/env bash
# Clean Docker Compose boot from zero + host-side checks. Writes artifacts/test-results/docker-smoke.txt. Requires .env (see .env.example).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
A="$ROOT/artifacts/test-results"; mkdir -p "$A"; OUT="$A/docker-smoke.txt"
C=(docker compose -f infra/docker-compose.yml --env-file .env)
PGPW=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-); SK=$(grep '^APP_SECRET_KEY=' .env | cut -d= -f2-)
{
  echo "# docker-smoke · $(date -u +%FT%TZ) · $(git rev-parse --short HEAD)"
  echo "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null) · compose: $(docker compose version --short)"
  echo "## down -v --remove-orphans"; "${C[@]}" down -v --remove-orphans 2>&1 | tail -3
  echo "## build --no-cache"; ( time "${C[@]}" build --no-cache ) > "$A/.docker-build.full" 2>&1; rc=$?; echo "build_exit=$rc"; grep -E "naming to|ERROR|^real" "$A/.docker-build.full" | tail -6
  [ $rc -eq 0 ] || { echo "BUILD FAILED"; exit 1; }
  echo "## up -d"; "${C[@]}" up -d 2>&1 | tail -4
  for i in $(seq 1 60); do curl -fsS localhost:8000/ready >/dev/null 2>&1 && break; sleep 2; done
  echo "## ps"; "${C[@]}" ps --format 'table {{.Name}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  echo "## health (host)";  curl -fsS -w ' [%{http_code}]\n' http://localhost:8000/health || echo "HEALTH FAILED"
  echo "## ready (host)";   curl -fsS -w ' [%{http_code}]\n' http://localhost:8000/ready  || echo "READY FAILED"
  echo "## frontend (host)"; curl -sI http://localhost:5173/ | head -2
  echo "## alembic in api container"; "${C[@]}" exec -T api alembic current 2>/dev/null | tail -1; echo "heads=$("${C[@]}" exec -T api alembic heads 2>/dev/null | wc -l)"
  echo "## schema tables (fresh volume)"; "${C[@]}" exec -T postgres psql -U vip_customs -d vip_customs -tc "select count(*) from information_schema.tables where table_schema='public'" | tr -d ' '
  echo "## logs scan (last 200 lines/service)"; "${C[@]}" logs --no-color --tail=200 > "$A/.docker-logs.full" 2>&1
  echo "error/traceback/restart lines: $(grep -ciE 'traceback|exception|restarting|exited with|connection refused|fatal' "$A/.docker-logs.full")"
  grep -iE 'traceback|exception|restarting|exited with|connection refused|fatal' "$A/.docker-logs.full" | head -5
  echo "secret leak check (POSTGRES_PASSWORD / APP_SECRET_KEY in logs): $(grep -c -e "$PGPW" -e "$SK" "$A/.docker-logs.full")"
  echo "restart counts: $(for c in $("${C[@]}" ps -q); do docker inspect --format '{{.Name}}={{.RestartCount}}' "$c"; done | tr '\n' ' ')"
} 2>&1 | tee "$OUT"
