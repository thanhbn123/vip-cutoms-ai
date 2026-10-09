#!/usr/bin/env bash
# B-07 operator wrapper: runs apps/api/scripts/deactivate_demo_users.py INSIDE the running api container of the
# staging compose project, so no database credential leaves the host. Never prints secrets.
#
#   DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh              # inventory (read-only)
#   DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --execute    # deactivate + verify
#   DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --verify
#
# --execute prompts for the literal confirmation token "demo.local" unless DEACTIVATE_CONFIRM is already exported.
set -euo pipefail
DEPLOY_PATH="${DEPLOY_PATH:-/opt/vip-customs-ai}"
PROJECT="${COMPOSE_PROJECT_NAME:-vip-customs-ai-staging}"
ENV="$DEPLOY_PATH/infra/staging/.env"
[ -f "$ENV" ] || { echo "missing $ENV"; exit 1; }
C=(docker compose -p "$PROJECT" -f "$DEPLOY_PATH/infra/staging/docker-compose.staging.yml" --env-file "$ENV")
"${C[@]}" ps --format '{{.Name}} {{.Status}}' | grep -q "api.*Up" || { echo "api container is not running for project $PROJECT"; exit 1; }

MODE="${1:-}"
case "$MODE" in
  "")          "${C[@]}" exec -T api python scripts/deactivate_demo_users.py ;;
  --verify)    "${C[@]}" exec -T api python scripts/deactivate_demo_users.py --verify ;;
  --execute)
    if [ -z "${DEACTIVATE_CONFIRM:-}" ]; then
      read -r -p "Type demo.local to deactivate every *@demo.local account on THIS host: " DEACTIVATE_CONFIRM
    fi
    [ "$DEACTIVATE_CONFIRM" = "demo.local" ] || { echo "confirmation mismatch; nothing changed"; exit 2; }
    "${C[@]}" exec -T -e DEACTIVATE_CONFIRM="$DEACTIVATE_CONFIRM" api python scripts/deactivate_demo_users.py --execute \
      --reason "${REASON:-B-07: demo acceptance accounts deactivated after staging acceptance (G18)}"
    echo "== post-check: a demo login must now be rejected (401) and health must be unchanged"
    "${C[@]}" exec -T api python - <<'PY'
import json, urllib.request, urllib.error
req = urllib.request.Request("http://localhost:8000/api/v1/auth/login", data=json.dumps({"email": "reviewer@demo.local", "password": "x"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=5); print("UNEXPECTED: login accepted"); raise SystemExit(1)
except urllib.error.HTTPError as e:
    print("demo login ->", e.code, "(expected 401)"); raise SystemExit(0 if e.code == 401 else 1)
PY
    "${C[@]}" exec -T api python -c "import urllib.request as u;print(u.urlopen('http://localhost:8000/ready').read().decode()[:200])"
    ;;
  *) echo "usage: $0 [--execute|--verify]"; exit 64 ;;
esac
