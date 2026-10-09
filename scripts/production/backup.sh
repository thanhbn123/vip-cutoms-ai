#!/usr/bin/env bash
# Database + uploads backup for a compose-deployed stack. Prepared for production, usable for
# staging. Idempotent, safe to run while the stack serves traffic, and NEVER prints a secret.
#
#   DEPLOY_PATH=/opt/vip-customs-ai ENV_FILE=infra/production/.env bash scripts/production/backup.sh
#
# Writes to $BACKUP_DIR (from ENV_FILE), mode 0700, every artifact mode 0600:
#   db-<stamp>.dump        custom-format pg_dump (pg_restore-able, compressed)
#   uploads-<stamp>.tgz    the uploads volume — the database alone is NOT a complete backup,
#                          because documents live in object storage and the DB holds only keys
#   <file>.sha256          checksum of each artifact, so a silent truncation is detectable
#   MANIFEST.txt           appended one line per run: stamp, sizes, SHAs, deployed git SHA
#
# A dump contains every customer document and every audit record in plaintext, so it is as
# sensitive as the database itself. `umask 077` is set before anything is created, and the
# directory and each artifact are explicitly chmod-ed, rather than trusting the caller's
# umask: under a normal 022 the dumps would otherwise be world-readable.
#
# ── CONSISTENCY: THIS IS NOT AN ATOMIC SNAPSHOT ──────────────────────────────────────────────
# The database dump and the uploads archive are taken SEQUENTIALLY from a LIVE stack, so they
# are two snapshots at two different instants, and neither is coordinated with the other:
#
#   * `pg_dump` itself is internally consistent — it runs in a single repeatable-read
#     transaction, so the dump reflects one database instant, excluding writes committed after
#     it started.
#   * The uploads archive is NOT: `tar` walks a live directory with no snapshot, so a file
#     written while it walks may be captured whole, partially, or not at all.
#   * The two are seconds apart. A document uploaded between them lands in the uploads archive
#     but not the dump (an orphan file), and a case row committed between them can reference a
#     document whose bytes were archived — or, if the upload landed just after the tar, were
#     not. Restoring both therefore does not reproduce any single instant of the live system.
#
# What that means in practice: expect a small number of dangling references near the backup
# window, not silent data corruption. Restore guidance is in docs/PRODUCTION_RUNBOOK.md §4 —
# for a restore that must be exact, quiesce writers first (stop `api` and `web`, leave
# `postgres` up) and take the pair with no traffic in flight. That works because the uploads
# archive is read by a one-off container rather than by `exec` into the running `api`; see the
# uploads step below. Do not describe the output of a live run as a consistent point-in-time
# backup, because it is not one.
#
# Exit non-zero on any failure, so a systemd timer / cron job reports it instead of failing
# silently — a backup job that fails quietly is worse than no backup job.
set -euo pipefail

# Before ANY file or directory is created: 077 => files 600, directories 700.
umask 077

DEPLOY_PATH="${DEPLOY_PATH:-/opt/vip-customs-ai}"
ENV_FILE="${ENV_FILE:-infra/production/.env}"
PROJECT="${COMPOSE_PROJECT_NAME:-vip-customs-ai-production}"
COMPOSE_FILES="${COMPOSE_FILES:--f infra/staging/docker-compose.staging.yml -f infra/production/docker-compose.production.yml}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }
die() { echo "[$(date -u +%FT%TZ)] FATAL: $*" >&2; exit 1; }

# GNU coreutils vs BSD/macOS: used only for the local checks below, never for the dump itself.
_owner_uid() { stat -c %u "$1" 2>/dev/null || stat -f %u "$1"; }
_mode() { stat -c %a "$1" 2>/dev/null || stat -f %Lp "$1"; }
_sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }

# Create (or re-create) a file that is private from the instant it exists. A plain `>`
# redirection into a pre-existing file keeps that file's old, possibly loose, mode.
_new_private_file() { rm -f "$1"; (umask 077; : > "$1"); chmod 600 "$1"; }

cd "$DEPLOY_PATH" || die "DEPLOY_PATH $DEPLOY_PATH not found"
[ -f "$ENV_FILE" ] || die "env file $ENV_FILE not found (copy infra/production/.env.production.example)"

# Read only the two keys this script needs; never echo the file.
BACKUP_DIR=$(sed -n 's/^BACKUP_DIR=//p' "$ENV_FILE" | tail -1)
RETENTION=$(sed -n 's/^BACKUP_RETENTION_DAYS=//p' "$ENV_FILE" | tail -1)
BACKUP_DIR="${BACKUP_DIR:-/var/backups/vip-customs}"
RETENTION="${RETENTION:-14}"
case "$RETENTION" in ''|*[!0-9]*) die "BACKUP_RETENTION_DAYS must be an integer, got '$RETENTION'";; esac

# ── backup directory must be a private directory we own ─────────────────────────────────────
# Fail closed on anything ambiguous. A symlink here is the dangerous case: it would redirect
# every dump to a path an attacker chose, and `chmod 700` would be applied to the target.
if [ -L "$BACKUP_DIR" ]; then
  die "BACKUP_DIR $BACKUP_DIR is a symlink — refusing to write dumps through it"
fi
if [ -e "$BACKUP_DIR" ] && [ ! -d "$BACKUP_DIR" ]; then
  die "BACKUP_DIR $BACKUP_DIR exists and is not a directory"
fi
[ -d "$BACKUP_DIR" ] || mkdir -p "$BACKUP_DIR" || die "cannot create $BACKUP_DIR"
if [ "$(_owner_uid "$BACKUP_DIR")" != "$(id -u)" ]; then
  die "BACKUP_DIR $BACKUP_DIR is not owned by uid $(id -u) — refusing to write dumps into it"
fi
chmod 700 "$BACKUP_DIR" || die "cannot chmod 700 $BACKUP_DIR"
[ "$(_mode "$BACKUP_DIR")" = "700" ] || die "BACKUP_DIR $BACKUP_DIR is mode $(_mode "$BACKUP_DIR"), expected 700"
[ -w "$BACKUP_DIR" ] || die "BACKUP_DIR $BACKUP_DIR is not writable"

# shellcheck disable=SC2086
C=(docker compose -p "$PROJECT" $COMPOSE_FILES --env-file "$ENV_FILE")

"${C[@]}" ps -q postgres 2>/dev/null | grep -q . || die "no running postgres for project $PROJECT — nothing to back up"

STAMP=$(date -u +%F-%H%M%S)
DB_FILE="$BACKUP_DIR/db-$STAMP.dump"
UP_FILE="$BACKUP_DIR/uploads-$STAMP.tgz"
MANIFEST="$BACKUP_DIR/MANIFEST.txt"

log "== database dump → $DB_FILE"
# -Fc = custom format. Password comes from the container's own environment, never the CLI.
_new_private_file "$DB_FILE"
"${C[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$DB_FILE"
[ -s "$DB_FILE" ] || die "database dump is empty — refusing to report success"

log "== uploads archive → $UP_FILE  (one-off reader; see the consistency note above)"
# Read the uploads volume through a ONE-OFF container, NOT `docker compose exec`. `exec`
# requires a running container, so it cannot work during the quiesced procedure in
# docs/PRODUCTION_RUNBOOK.md §4, which stops `api` and `web` before taking the pair. A one-off
# container mounts the same `uploads` volume, so this still needs no knowledge of the volume's
# name or host path, and it starts no writer.
#   --no-deps        do not start postgres, and do not re-run the one-shot `migrate` service
#   -T               no pseudo-TTY: the archive is binary on stdout and a TTY would corrupt it
#   --rm             throw the container away afterwards
#   --pull never     never reach out to a registry (requires compose >= v2.8)
#   --entrypoint sh  bypass the image's own CMD, which is
#                    `sh -c "alembic upgrade head && uvicorn ..."`. Without this override a
#                    one-off container would RUN MIGRATIONS and then try to serve, instead of
#                    tarring the volume. `--entrypoint` also discards the compose `command`.
# `--build` is deliberately absent, so a present image is reused as-is; the pre-flight below
# fails closed rather than letting a backup silently trigger an image build.
UPLOADS_IMAGE=$("${C[@]}" config --images api 2>/dev/null | head -1 || true)
if [ -n "$UPLOADS_IMAGE" ]; then
  docker image inspect "$UPLOADS_IMAGE" >/dev/null 2>&1 \
    || die "api image '$UPLOADS_IMAGE' is not present locally — refusing to let a backup build or pull it"
else
  log "WARN: could not resolve the api image name — skipping the image pre-flight"
fi
_new_private_file "$UP_FILE"
"${C[@]}" run --rm --no-deps -T --pull never --entrypoint sh api \
  -c 'tar czf - -C /data/uploads .' > "$UP_FILE"
[ -s "$UP_FILE" ] || die "uploads archive is empty — refusing to report success"

log "== checksums"
for f in "$DB_FILE" "$UP_FILE"; do
  _new_private_file "$f.sha256"
  (cd "$(dirname "$f")" && _sha256 "$(basename "$f")") > "$f.sha256"
done

DEPLOYED_SHA=$(git -c safe.directory="$DEPLOY_PATH" rev-parse HEAD 2>/dev/null || echo unknown)
[ -e "$MANIFEST" ] || _new_private_file "$MANIFEST"
printf '%s db=%s(%s bytes, %s) uploads=%s(%s bytes, %s) deployed_sha=%s not_atomic=sequential\n' \
  "$STAMP" \
  "$(basename "$DB_FILE")" "$(wc -c < "$DB_FILE" | tr -d ' ')" "$(cut -d' ' -f1 < "$DB_FILE.sha256")" \
  "$(basename "$UP_FILE")" "$(wc -c < "$UP_FILE" | tr -d ' ')" "$(cut -d' ' -f1 < "$UP_FILE.sha256")" \
  "$DEPLOYED_SHA" >> "$MANIFEST"
# An older manifest may predate this hardening, so tighten it every run rather than assuming.
chmod 600 "$MANIFEST"

log "== permissions"
for f in "$DB_FILE" "$UP_FILE" "$DB_FILE.sha256" "$UP_FILE.sha256" "$MANIFEST"; do
  m=$(_mode "$f")
  [ "$m" = "600" ] || die "$f is mode $m, expected 600 — refusing to leave a readable dump"
done
log "dir $(_mode "$BACKUP_DIR") · artifacts 600"

log "== retention: delete local artifacts older than $RETENTION days"
# -maxdepth 1 and the name patterns keep this to this script's own artifacts. MANIFEST.txt is
# deliberately never pruned: it is the only record of what was taken and already deleted.
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'db-*.dump.sha256' \
  -o -name 'uploads-*.tgz' -o -name 'uploads-*.tgz.sha256' \) -mtime "+$RETENTION" -print -delete

log "== OK. db=$(wc -c < "$DB_FILE" | tr -d ' ') bytes uploads=$(wc -c < "$UP_FILE" | tr -d ' ') bytes"
echo
echo "REMINDER: this script keeps copies on the SAME HOST only. A host loss still loses the"
echo "data. Replicate $BACKUP_DIR off-host, and verify a restore on a schedule — an untested"
echo "backup is not a backup. The dump/archive pair is NOT an atomic snapshot (see the header"
echo "and docs/PRODUCTION_RUNBOOK.md §4). Restore procedure: docs/PRODUCTION_RUNBOOK.md"
