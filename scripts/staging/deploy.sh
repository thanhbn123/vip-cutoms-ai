#!/usr/bin/env bash
# Runs ON the staging host (copy this file or `git clone` first). Idempotent. Deploys the exact DEPLOY_SHA.
#   DEPLOY_SHA=<sha> DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deploy.sh
# Requires infra/staging/.env (from .env.staging.example) already filled on the host. Never prints secrets.
set -euo pipefail
: "${DEPLOY_SHA:?DEPLOY_SHA required (see docs/G15_DEPLOY_RECORD.md)}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/vip-customs-ai}"
REPO_URL="${REPO_URL:-https://github.com/thanhbn123/vip-cutoms-ai.git}"
PROJECT="${COMPOSE_PROJECT_NAME:-vip-customs-ai-staging}"
log() { echo "[$(date -u +%FT%TZ)] $*"; }

log "== host identity"; hostname; whoami; uname -a; df -h / | tail -1; (free -h || true) | head -2
docker version --format 'docker server {{.Server.Version}}'; docker compose version --short
log "== pre-deploy inventory (nothing is stopped)"; docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'; (ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | head -40

log "== checkout exact SHA into dedicated directory $DEPLOY_PATH"
if [ ! -d "$DEPLOY_PATH/.git" ]; then mkdir -p "$DEPLOY_PATH"; git clone "$REPO_URL" "$DEPLOY_PATH"; fi
cd "$DEPLOY_PATH"
git fetch origin --prune
git checkout -q develop 2>/dev/null || git checkout -q -b develop origin/develop
git reset -q --hard "$DEPLOY_SHA"          # only this dedicated staging checkout
[ "$(git rev-parse HEAD)" = "$DEPLOY_SHA" ] || { echo "HEAD != DEPLOY_SHA"; exit 1; }
log "HEAD = $(git rev-parse HEAD)"

ENV="$DEPLOY_PATH/infra/staging/.env"
[ -f "$ENV" ] || { echo "missing $ENV — copy infra/staging/.env.staging.example and fill it (docs/STAGING_SECRETS.md)"; exit 1; }
chmod 600 "$ENV"
for k in POSTGRES_PASSWORD APP_SECRET_KEY PUBLIC_HOST PUBLIC_WEB_ORIGIN; do grep -qE "^$k=.+" "$ENV" || { echo "$k not set in .env"; exit 1; }; done
grep -qE "^AI_PROVIDER=mock" "$ENV" || echo "WARN: AI_PROVIDER is not mock"
grep -q "^IMAGE_TAG=" "$ENV" && sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${DEPLOY_SHA:0:12}/" "$ENV" || echo "IMAGE_TAG=${DEPLOY_SHA:0:12}" >> "$ENV"
C=(docker compose -p "$PROJECT" -f infra/staging/docker-compose.staging.yml --env-file "$ENV")

log "== backup / rollback baseline"
mkdir -p "$DEPLOY_PATH/backups"
if "${C[@]}" ps -q postgres 2>/dev/null | grep -q .; then
  echo "PREVIOUS_IMAGES:"; "${C[@]}" images 2>/dev/null | tail -n +2 | tee "$DEPLOY_PATH/backups/previous-images-$(date +%F-%H%M).txt"
  "${C[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$DEPLOY_PATH/backups/db-predeploy-$(date +%F-%H%M).dump"
  echo "FIRST_DEPLOY=NO"
else
  echo "FIRST_DEPLOY=YES (no running postgres for project $PROJECT)"
fi

log "== build images from $DEPLOY_SHA"; "${C[@]}" build --no-cache
docker images --digests --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Digest}}' | grep -E "vip-customs|REPOSITORY"

log "== start"; "${C[@]}" up -d
for i in $(seq 1 60); do "${C[@]}" ps --format '{{.Name}} {{.Status}}' | grep -q "api.*Up" && break; sleep 2; done
"${C[@]}" ps
log "== migration"; "${C[@]}" exec -T api alembic current; echo "heads=$("${C[@]}" exec -T api alembic heads | wc -l)"
log "== server-internal health"; "${C[@]}" exec -T api python -c "import urllib.request as u;print(u.urlopen('http://localhost:8000/health').read().decode());print(u.urlopen('http://localhost:8000/ready').read().decode())"
log "== deployed $DEPLOY_SHA as project $PROJECT. Next: scripts/staging/acceptance.sh from a client."
