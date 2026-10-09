#!/usr/bin/env bash
# Off-host backup replication (G18, design: docs/G18_OFFHOST_BACKUP.md). PREPARED — the destination is an
# OWNER INPUT; this script carries no credential and refuses to run until one is configured.
#
#   DEPLOY_PATH=/opt/vip-customs-ai ENV_FILE=infra/production/.env bash scripts/production/backup_offsite.sh
#
# Reads from ENV_FILE (never printed):
#   BACKUP_DIR                 local directory written by scripts/production/backup.sh (required)
#   OFFSITE_METHOD             rclone | ssh                                              (required)
#   OFFSITE_TARGET             rclone remote path "remote:bucket/prefix" or "user@host:/path" (required)
#   OFFSITE_ENCRYPT_RECIPIENT  age public key; when set every artifact is encrypted BEFORE leaving the host
#   OFFSITE_RETENTION_DAILY / _WEEKLY / _MONTHLY   copies to keep remotely (defaults 7 / 4 / 6 — PROPOSED, owner approval required)
#   BACKUP_STATUS_FILE         JSON status the API reads for /ready in full mode (default $BACKUP_DIR/backup-status.json)
#
# Behaviour:
#   * copies the NEWEST db-*.dump + uploads-*.tgz pair (+ .sha256 + MANIFEST.txt) produced by backup.sh
#   * verifies the local checksums first — a corrupt artifact is never replicated
#   * encrypts with `age` when a recipient is configured (no plaintext customer documents off-host otherwise refused
#     unless OFFSITE_ALLOW_PLAINTEXT=yes is set explicitly)
#   * uploads to the daily/ prefix; on Sundays also weekly/, on the 1st also monthly/ (GFS retention)
#   * prunes remote copies beyond the retention counts (rclone method; ssh method prints the prune command instead)
#   * writes BACKUP_STATUS_FILE {"last_success_at", "destination_kind", "offsite": true, "artifacts": [...]} ONLY on success
#   * exit non-zero on any failure so the systemd timer reports it; never prints the env file or a credential
set -euo pipefail
umask 077

DEPLOY_PATH="${DEPLOY_PATH:-/opt/vip-customs-ai}"
ENV_FILE="${ENV_FILE:-$DEPLOY_PATH/infra/production/.env}"
[ -f "$ENV_FILE" ] || { echo "offsite: missing ENV_FILE $ENV_FILE" >&2; exit 1; }
getvar() { { grep -E "^$1=" "$ENV_FILE" || true; } | tail -1 | cut -d= -f2- | tr -d '"' ; }  # absent key → empty, not a pipefail exit
BACKUP_DIR="$(getvar BACKUP_DIR)"; OFFSITE_METHOD="$(getvar OFFSITE_METHOD)"; OFFSITE_TARGET="$(getvar OFFSITE_TARGET)"
RECIPIENT="$(getvar OFFSITE_ENCRYPT_RECIPIENT)"; ALLOW_PLAIN="$(getvar OFFSITE_ALLOW_PLAINTEXT)"
R_DAILY="$(getvar OFFSITE_RETENTION_DAILY)"; R_WEEKLY="$(getvar OFFSITE_RETENTION_WEEKLY)"; R_MONTHLY="$(getvar OFFSITE_RETENTION_MONTHLY)"
STATUS_FILE="$(getvar BACKUP_STATUS_FILE)"
R_DAILY="${R_DAILY:-7}"; R_WEEKLY="${R_WEEKLY:-4}"; R_MONTHLY="${R_MONTHLY:-6}"
[ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ] || { echo "offsite: BACKUP_DIR not set or missing" >&2; exit 1; }
STATUS_FILE="${STATUS_FILE:-$BACKUP_DIR/backup-status.json}"
case "$OFFSITE_METHOD" in rclone|ssh) ;; "") echo "offsite: OFFSITE_METHOD not configured — OWNER INPUT (docs/G18_OWNER_INPUTS.md)" >&2; exit 3 ;;
  *) echo "offsite: unsupported OFFSITE_METHOD '$OFFSITE_METHOD' (rclone|ssh)" >&2; exit 1 ;; esac
[ -n "$OFFSITE_TARGET" ] || { echo "offsite: OFFSITE_TARGET not configured — OWNER INPUT" >&2; exit 3; }
for n in "$R_DAILY" "$R_WEEKLY" "$R_MONTHLY"; do [[ "$n" =~ ^[0-9]+$ ]] || { echo "offsite: retention must be an integer" >&2; exit 1; }; done
if [ -z "$RECIPIENT" ] && [ "$ALLOW_PLAIN" != "yes" ]; then
  echo "offsite: refusing to send PLAINTEXT dumps off-host. Set OFFSITE_ENCRYPT_RECIPIENT (age public key) or OFFSITE_ALLOW_PLAINTEXT=yes." >&2; exit 4
fi

cd "$BACKUP_DIR"
DUMP="$(ls -1t db-*.dump 2>/dev/null | head -1 || true)"; UPL="$(ls -1t uploads-*.tgz 2>/dev/null | head -1 || true)"
[ -n "$DUMP" ] && [ -n "$UPL" ] || { echo "offsite: no local backup pair found in BACKUP_DIR (run backup.sh first)" >&2; exit 1; }
for f in "$DUMP" "$UPL"; do
  [ -s "$f" ] || { echo "offsite: $f is empty" >&2; exit 1; }
  [ -f "$f.sha256" ] || { echo "offsite: missing $f.sha256" >&2; exit 1; }
  sha256sum -c --quiet "$f.sha256" || { echo "offsite: checksum mismatch for $f — NOT replicated" >&2; exit 1; }
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"; WORK="$(mktemp -d "${TMPDIR:-/tmp}/offsite.XXXXXX")"; trap 'rm -rf "$WORK"' EXIT
ART=()
for f in "$DUMP" "$UPL" "$DUMP.sha256" "$UPL.sha256"; do
  if [ -n "$RECIPIENT" ] && [[ "$f" != *.sha256 ]]; then
    command -v age >/dev/null || { echo "offsite: age not installed" >&2; exit 1; }
    age -r "$RECIPIENT" -o "$WORK/$f.age" "$f"; ART+=("$f.age")
  else
    cp "$f" "$WORK/$f"; ART+=("$f")
  fi
done
[ -f MANIFEST.txt ] && { cp MANIFEST.txt "$WORK/MANIFEST.txt"; ART+=("MANIFEST.txt"); }

PREFIXES=("daily/$STAMP")
[ "$(date -u +%u)" = "7" ] && PREFIXES+=("weekly/$STAMP")
[ "$(date -u +%d)" = "01" ] && PREFIXES+=("monthly/$STAMP")

upload() { # $1 = remote prefix
  case "$OFFSITE_METHOD" in
    rclone) command -v rclone >/dev/null || { echo "offsite: rclone not installed" >&2; exit 1; }
            rclone copy --checksum --transfers 2 "$WORK" "$OFFSITE_TARGET/$1" ;;
    ssh)    ssh -o BatchMode=yes "${OFFSITE_TARGET%%:*}" "mkdir -p '${OFFSITE_TARGET#*:}/$1'"
            scp -q -o BatchMode=yes "$WORK"/* "$OFFSITE_TARGET/$1/" ;;
  esac
}
prune() { # $1 = class  $2 = keep
  if [ "$OFFSITE_METHOD" = "rclone" ]; then
    rclone lsf --dirs-only "$OFFSITE_TARGET/$1" 2>/dev/null | sort | head -n -"$2" | while read -r old; do
      [ -n "$old" ] && rclone purge "$OFFSITE_TARGET/$1/$old"; done
  else
    echo "offsite: prune $1 beyond $2 copies manually on the ssh target (ssh method has no safe remote listing here)"
  fi
}
for p in "${PREFIXES[@]}"; do upload "$p"; echo "offsite: uploaded ${#ART[@]} artifact(s) to $p"; done
prune daily "$R_DAILY"; prune weekly "$R_WEEKLY"; prune monthly "$R_MONTHLY"

TMP_STATUS="$(mktemp "${STATUS_FILE}.XXXXXX")"
printf '{"last_success_at": "%s", "destination_kind": "%s", "offsite": true, "encrypted": %s, "artifacts": [%s], "prefixes": [%s]}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$OFFSITE_METHOD" "$([ -n "$RECIPIENT" ] && echo true || echo false)" \
  "$(printf '"%s",' "${ART[@]}" | sed 's/,$//')" "$(printf '"%s",' "${PREFIXES[@]}" | sed 's/,$//')" > "$TMP_STATUS"
chmod 600 "$TMP_STATUS"; mv -f "$TMP_STATUS" "$STATUS_FILE"
echo "offsite: OK — status written to $STATUS_FILE"
