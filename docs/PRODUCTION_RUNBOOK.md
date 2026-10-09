# PRODUCTION RUNBOOK

**Nothing in this repository has been deployed to production.** This runbook is the procedure
to use *if and when* the owner decides to deploy. Read `docs/PRODUCTION_READINESS.md` first —
in particular the scope limit: this build produces internal drafts and has no customs-system
adapter (product rule #7).

Scope reminder for whoever runs these commands: the stack never submits anything to a customs
authority. "Phát hành" produces a versioned internal draft file.

## 0. Prerequisites

| | |
|---|---|
| Host | Linux with Docker ≥ 24 and the compose plugin; a user in the `docker` group. |
| Ports | Either 80/443 free (`TLS_MODE=acme`), or a reverse proxy you control plus loopback high ports (`TLS_MODE=off`, see B-06). |
| DNS | `PUBLIC_HOST` resolving to the host, before `acme` can issue a certificate. |
| Config | `infra/production/.env`, created from `infra/production/.env.production.example`, `chmod 600`, never committed. |
| Decisions | B-01/B-02 determine whether this is a limited-mode or full-mode deployment. Do not skip that question. |

Generate the two secrets **on the host** and nowhere else:

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(36))"   # POSTGRES_PASSWORD
python3 -c "import secrets;print(secrets.token_urlsafe(48))"   # APP_SECRET_KEY
```

## 1. Deploy a pinned release

The stack is always deployed at an exact git SHA; `IMAGE_TAG` carries the 12-char prefix so a
rollback is unambiguous. There is no production `deploy.sh`: `scripts/staging/deploy.sh` is
staging-specific (it hard-codes the staging compose file and project name) and reusing it for
production would silently deploy with staging's settings. Use these steps.

```bash
DEPLOY_SHA=<full-sha>
DEPLOY_PATH=/opt/vip-customs-ai
PROJECT=vip-customs-ai-production
ENV=$DEPLOY_PATH/infra/production/.env
C="docker compose -p $PROJECT -f infra/staging/docker-compose.staging.yml -f infra/production/docker-compose.production.yml --env-file $ENV"

cd $DEPLOY_PATH
git fetch origin --prune
git -c advice.detachedHead=false checkout --detach "$DEPLOY_SHA"
[ "$(git rev-parse HEAD)" = "$DEPLOY_SHA" ] || { echo "HEAD != DEPLOY_SHA"; exit 1; }
# Baseline backup FIRST, while .env still names the CURRENTLY deployed image. backup.sh
# resolves the api image from the compose config and refuses to run if it is not present
# locally, so bumping IMAGE_TAG before this line would make the baseline backup fail.
bash scripts/production/backup.sh          # step 4 — baseline (skip on a first deploy)

sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${DEPLOY_SHA:0:12}/" "$ENV"
$C build --no-cache
$C up -d
$C ps
$C exec -T api alembic current              # expect a single head; see step 2
```

Why both compose files: the production file is an **overlay**, not a replacement. Staging
defines the topology; production adds log rotation, a `web` healthcheck, memory limits and
`restart: always`. Passing only the production file is a configuration error and compose will
reject it.

### Verify before announcing

```bash
curl -fsS https://$PUBLIC_HOST/health      # {"status":"ok",...}
curl -fsS https://$PUBLIC_HOST/ready       # database ok · migrations <head> · ai_provider · environment production
curl -o /dev/null -w '%{http_code}\n' https://$PUBLIC_HOST/
docker inspect -f '{{.Name}} restarts={{.RestartCount}}' $($C ps -q)
$C logs --since 10m | grep -iE 'traceback|error' | head
```

`/ready` returning **503** is the system telling you it is misconfigured — read the `checks`
object rather than restarting. A provider or storage backend that is not implemented in this
build reports there by name.

## 2. Migrations

The one-shot `migrate` service runs `alembic upgrade head` before `api` starts, and `api`
waits on `service_completed_successfully`. If the migration fails the API never starts —
which is the desired behaviour: a schema mismatch must not serve traffic.

```bash
$C exec -T api alembic current              # applied revision
$C exec -T api alembic heads                # MUST be exactly one line
$C logs migrate
```

Every revision 0001–0010 has a tested downgrade path. Downgrading a migration that dropped a
column still loses that column's data — restore from the backup instead when data matters.

## 3. Rollback

**Triggers:** `/ready` ≠ 200 for more than 2 minutes after deploy · `migrate` exits non-zero ·
any container in a restart loop · a security finding · acceptance smoke fails.

```bash
$C down                                     # volumes are KEPT; omitting -v matters
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=<previous-12-char-sha>/" "$ENV"
cd $DEPLOY_PATH && git -c advice.detachedHead=false checkout --detach <previous-full-sha>
$C up -d
```

If the new release applied a migration the previous code cannot read, either
`$C run --rm api alembic downgrade <previous-head>`, or restore the pre-deploy backup (§4).

Rollback never touches `main`, never contacts a customs system, and never deletes audit
history — `audit_events` rejects UPDATE/DELETE via a database trigger.

## 4. Backup and restore

```bash
DEPLOY_PATH=/opt/vip-customs-ai ENV_FILE=infra/production/.env bash scripts/production/backup.sh
```

Writes to `BACKUP_DIR` (mode 0700, every artifact 0600): `db-<stamp>.dump` (pg_dump `-Fc`),
`uploads-<stamp>.tgz`, a `.sha256` beside each, and a line appended to `MANIFEST.txt` recording
sizes, checksums and the deployed SHA. Exits non-zero on any failure, including an empty dump,
so a timer reports it. It refuses to run if `BACKUP_DIR` is a symlink, is not a directory, or is
not owned by the invoking user.

A dump contains every customer document and every audit record in plaintext, so treat it as
being exactly as sensitive as the database. The script sets `umask 077` and chmods each
artifact rather than trusting the caller's umask, and the systemd unit sets `UMask=0077`; under
a normal 022 the dumps would otherwise be world-readable. Keep that property when you copy
them off-host — `scp` to a world-readable directory undoes all of it.

**The database alone is not a complete backup.** Documents live in object storage and the
database holds only keys; a database-only restore gives you cases whose documents 404.

### These two files are not an atomic snapshot

Be clear-eyed about what a live backup is worth. The dump and the archive are taken
sequentially from a running stack, so they are two snapshots at two different instants:

- `pg_dump` is internally consistent — it runs in one repeatable-read transaction, so the dump
  reflects a single database instant.
- The uploads archive is **not**. `tar` walks a live directory with no snapshot, so a file being
  written while it walks may be captured whole, partially, or not at all.
- The two are seconds apart. A document uploaded between them appears in the archive but not in
  the dump (an orphan file); a case row committed between them may reference a document whose
  bytes were archived, or — if the upload landed just after the `tar` — were not.

So a restore from a live backup does not reproduce any single instant of the system. Expect a
small number of dangling references around the backup window rather than silent corruption:
the database is self-consistent, and the mismatch is confined to document bytes near the
boundary. The audit hash chain is unaffected, because `audit_events` is append-only and the
dump is transactionally consistent.

**If the restore must be exact, quiesce writers first.** This is the only procedure here that
produces a coherent pair:

```bash
$C stop api web                             # no new cases, no new uploads; postgres stays up
DEPLOY_PATH=/opt/vip-customs-ai ENV_FILE=infra/production/.env bash scripts/production/backup.sh
$C start api web
```

This works because `backup.sh` reads the uploads volume with a **one-off container**
(`run --rm --no-deps -T --pull never --entrypoint sh api`) rather than `docker compose exec api`.
`exec` requires a running container and would fail here. The one-off reader mounts the same
`uploads` volume, starts no dependency and no writer, and `--entrypoint sh` bypasses the image's
CMD — which is `sh -c "alembic upgrade head && uvicorn ..."`, so without the override the
backup would apply migrations. `postgres` must stay up for `pg_dump`.

That costs a short write outage and is worth scheduling for a pre-deploy or pre-migration
baseline, where a half-matched pair is exactly what you cannot afford. The nightly timer
deliberately does **not** stop the stack: an unattended nightly outage is the wrong trade for a
routine copy. If you need coherent backups with no outage, that is a volume- or
filesystem-level snapshot (LVM, ZFS, or the hosting provider's disk snapshot) taken at one
instant across both the database and the uploads volume — not something this script can do, and
an infrastructure decision rather than an application one.

After **any** restore, reconcile the two halves before trusting the result. This one does use
`exec`, correctly: it runs after `$C up -d` above, so `api` is running again and it needs a live
database.

```bash
# documents whose stored bytes are missing from the restored uploads volume
$C exec -T api python -c "
from app.db import get_sessionmaker
from app.models.document import Document
from app.storage.base import get_storage
db, st = get_sessionmaker()(), get_storage()
missing = [str(d.id) for d in db.query(Document).all() if not st.exists(d.storage_key)]
print(f'documents with missing bytes: {len(missing)}'); print(*missing[:20], sep=chr(10))
"
```

A non-zero count localises the damage to specific documents, which an operator can re-request
from the customer. Record the count and the affected ids in `docs/DECISIONS.md`.

Automate it with the example units (installing them needs root — an owner decision):

```bash
sudo cp infra/production/vip-customs-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now vip-customs-backup.timer
systemctl list-timers vip-customs-backup.timer
journalctl -u vip-customs-backup.service -n 50
```

Then do the two things the script cannot do for you: **replicate `BACKUP_DIR` off-host**, and
**drill a restore on a schedule**.

### Verify a backup without touching the live database

Restore into a temporary database — the procedure G15C used successfully:

```bash
$C exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE IF EXISTS restore_test" -c "CREATE DATABASE restore_test"'
$C exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_test' < backups/db-<stamp>.dump
for t in cases documents goods_items audit_events; do
  echo "$t live=$($C exec -T postgres sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tAc 'select count(*) from $t'") restored=$($C exec -T postgres sh -c "psql -U \$POSTGRES_USER -d restore_test -tAc 'select count(*) from $t'")"
done
$C exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE restore_test"'
```

### Real restore

```bash
$C stop api web                             # stop writers; leave postgres up
$C exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/db-<stamp>.dump
# `api` is stopped, so the uploads volume is written through a one-off container, not `exec`
# (`exec` needs a running container). --no-deps starts nothing else, and --entrypoint sh
# bypasses the image CMD, which would otherwise run `alembic upgrade head` and then uvicorn.
$C run --rm --no-deps -T --pull never --entrypoint sh api \
  -c 'tar xzf - -C /data/uploads' < backups/uploads-<stamp>.tgz
$C up -d && curl -fsS https://$PUBLIC_HOST/ready
curl -fsS -H "Authorization: Bearer <token>" https://$PUBLIC_HOST/api/v1/audit/verify   # chain_valid must be true
```

`postgres` stays up on purpose: `pg_restore` needs a live server, and `exec` into it is correct
because it is still running. Only `api` and `web` are stopped, and only the uploads step needs
the one-off container.

## 5. Monitoring

Nothing currently watches this stack (`docs/PRODUCTION_READINESS.md` §2.2). Choosing a tool is
an owner decision; what to watch is not, so it is specified here.

| Signal | Check | Alert when |
|---|---|---|
| Liveness | `GET /health` → 200 | 2 consecutive failures, 60s apart |
| Readiness | `GET /ready` → 200 **and** body `.status == "ready"` | any non-200, or `.checks.database` ≠ `ok` |
| Migration drift | `.checks.migrations` from `/ready` | value changes without a deploy |
| Provider | `.checks.ai_provider` from `/ready` | value changes unexpectedly, or reports `error:` |
| TLS expiry | certificate `notAfter` on `PUBLIC_HOST` | fewer than 14 days remaining |
| Containers | `docker inspect .RestartCount` | any increase |
| Disk | `df` on the Docker data root and `BACKUP_DIR` | above 80% |
| Backup freshness | newest file in `BACKUP_DIR` | older than 36 hours |
| Audit integrity | `GET /api/v1/audit/verify` → `chain_valid: true` | ever false — treat as a security incident |
| Errors | 5xx rate in proxy logs | any sustained 5xx |

Alert on `/ready` rather than `/health`: a process that is up but cannot reach its database
answers `/health` with 200. Do not alert on a single `/health` failure — a deploy briefly
restarts the api container by design.

`GET /ready` is unauthenticated and reports the environment name, migration revision and
provider name. That is deliberate, for load balancers and monitors, but it means the endpoint
should not be reachable from the public internet in production if you would rather not publish
your migration revision. Restrict it at the proxy to your monitoring source if that matters.

## 6. Incident response

1. **Record the time and what you saw** before changing anything — a restart destroys the
   evidence.
2. **Triage:** `/health` and `/ready`; `$C ps`; `$C logs --since 30m api`; restart counts; disk.
3. **Do not restart as a first step** if `/ready` reports a specific failing check — fix the
   check. `/ready` is designed to tell you what is wrong.
4. **Rollback (§3) if the incident started with a deploy.** It is the fastest safe action.
5. **If audit integrity fails** (`chain_valid: false`): stop, do not restart, do not restore
   over it, preserve the database, and escalate to the owner. `audit_events` is append-only at
   the database level, so a broken chain means either a restore artefact or tampering.
6. **Never** fix an incident by editing data on the host, by weakening a fail-closed check, or
   by pointing the stack at demo knowledge data to make an issue clear.
7. Record the incident and its cause in `docs/DECISIONS.md`.

## 7. Secrets

| Variable | Rule |
|---|---|
| `POSTGRES_PASSWORD` | ≥ 32 random chars, generated on the host. The database is never published outside the compose network. |
| `APP_SECRET_KEY` | ≥ 32 chars; the API refuses to start without it outside development. **Rotating it invalidates every session** — all users must log in again. |
| provider keys | None exist. This build has no real provider (B-01). |
| `SEED_DEMO_PASSWORD` | Not part of a production config. `seed_demo.py` refuses to run when `APP_ENV` is not development/test. |

`.env*` is git-ignored except the `*.env.example` templates; `scripts/secret_scan.sh` runs in
`make verify` and in CI. Never paste a secret into a ticket, log or chat message. If one is
exposed: rotate it, restart the stack, and record the rotation (not the value) in
`docs/DECISIONS.md`.
