#!/usr/bin/env bash
# Database + uploads backup for a compose-deployed stack. Prepared for production, usable for
# staging. Idempotent, safe to run while the stack serves traffic, and NEVER prints a secret.
#
#   DEPLOY_PATH=/opt/vip-customs-ai ENV_FILE=infra/production/.env bash scripts/production/backup.sh
#
# Writes to $BACKUP_DIR (from ENV_FILE):
#   db-<stamp>.dump        custom-format pg_dump (pg_restore-able, compressed)
#   uploads-<stamp>.tgz    the uploads volume — the database alone is NOT a complete backup,
#                          because documents live in object storage and the DB holds only keys
#   <file>.sha256          checksum of each artifact, so a silent truncation is detectable
#   MANIFEST.txt           appended one line per run: stamp, sizes, SHAs, deployed git SHA
#
# Exit non-zero on any failure, so a systemd timer / cron job reports it instead of failing
# silently — a backup job that fails quietly is worse than no backup job.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/vip-customs-ai}"
ENV_FILE="${ENV_FILE:-infra/production/.env}"
PROJECT="${COMPOSE_PROJECT_NAME:-vip-customs-ai-production}"
COMPOSE_FILES="${COMPOSE_FILES:--f infra/staging/docker-compose.staging.yml -f infra/production/docker-compose.production.yml}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }
die() { echo "[$(date -u +%FT%TZ)] FATAL: $*" >&2; exit 1; }

cd "$DEPLOY_PATH" || die "DEPLOY_PATH $DEPLOY_PATH not found"
[ -f "$ENV_FILE" ] || die "env file $ENV_FILE not found (copy infra/production/.env.production.example)"

# Read only the two keys this script needs; never echo the file.
BACKUP_DIR=$(sed -n 's/^BACKUP_DIR=//p' "$ENV_FILE" | tail -1)
RETENTION=$(sed -n 's/^BACKUP_RETENTION_DAYS=//p' "$ENV_FILE" | tail -1)
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vip-customs}"
RETENTION="${RETENTION:-14}"
case "$RETENTION" in ''|*[!0-9]*) die "BACKUP_RETENTION_DAYS must be an integer, got '$RETENTION'";; esac

# shellcheck disable=SC2086
C=(docker compose -p "$PROJECT" $COMPOSE_FILES --env-file "$ENV_FILE")

"${C[@]}" ps -q postgres 2>/dev/null | grep -q . || die "no running postgres for project $PROJECT — nothing to back up"

mkdir -p "$BACKUP_DIR" || die "cannot create $BACKUP_DIR"
STAMP=$(date -u +%F-%H%M%S)
DB_FILE="$BACKUP_DIR/db-$STAMP.dump"
UP_FILE="$BACKUP_DIR/uploads-$STAMP.tgz"

log "== database dump → $DB_FILE"
# -Fc = custom format. Password comes from the container's own environment, never the CLI.
"${C[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$DB_FILE"
[ -s "$DB_FILE" ] || die "database dump is empty — refusing to report success"

log "== uploads archive → $UP_FILE"
# Streamed out of the api container, which already has the volume mounted, so this needs no
# knowledge of the volume's name or host path.
"${C[@]}" exec -T api sh -c 'tar czf - -C /data/uploads .' > "$UP_FILE"
[ -s "$UP_FILE" ] || die "uploads archive is empty — refusing to report success"

log "== checksums"
for f in "$DB_FILE" "$UP_FILE"; do
  (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256")
done

DEPLOYED_SHA=$(git -c safe.directory="$DEPLOY_PATH" rev-parse HEAD 2>/dev/null || echo unknown)
printf '%s db=%s(%s bytes, %s) uploads=%s(%s bytes, %s) deployed_sha=%s\n' \
  "$STAMP" \
  "$(basename "$DB_FILE")" "$(wc -c < "$DB_FILE")" "$(cut -d' ' -f1 < "$DB_FILE.sha256")" \
  "$(basename "$UP_FILE")" "$(wc -c < "$UP_FILE")" "$(cut -d' ' -f1 < "$UP_FILE.sha256")" \
  "$DEPLOYED_SHA" >> "$BACKUP_DIR/MANIFEST.txt"

log "== retention: delete local artifacts older than $RETENTION days"
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.dump*' -o -name 'uploads-*.tgz*' \) \
  -mtime "+$RETENTION" -print -delete

log "== OK. db=$(wc -c < "$DB_FILE") bytes uploads=$(wc -c < "$UP_FILE") bytes"
echo
echo "REMINDER: this script keeps copies on the SAME HOST only. A host loss still loses the"
echo "data. Replicate $BACKUP_DIR off-host, and verify a restore on a schedule — an untested"
echo "backup is not a backup. Restore procedure: docs/PRODUCTION_RUNBOOK.md"
