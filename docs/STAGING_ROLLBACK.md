# STAGING ROLLBACK & BACKUP

## Backup (before every deploy and nightly)
```bash
cd infra/staging
docker compose -f docker-compose.staging.yml --env-file .env exec -T postgres pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB > backups/db-$(date +%F-%H%M).dump
docker run --rm -v vip-customs-staging_uploads:/data -v $PWD/backups:/b alpine tar czf /b/uploads-$(date +%F-%H%M).tgz -C /data .
```
Keep ≥ 7 daily copies off-host. Audit rows are append-only; a restore never rewrites them.

## Rollback triggers
`/ready` ≠ 200 for > 2 min after deploy · migrate service exit ≠ 0 · crash loop in `docker compose ps` · acceptance smoke fails · security finding.

## Rollback procedure
1. `docker compose … down` (volumes are kept).
2. Set `IMAGE_TAG` back to the previous SHA in `.env`; `docker compose … up -d`.
3. If the new release ran a migration the previous code cannot read: `docker compose … run --rm api alembic downgrade <previous head>`
   (all revisions 0001–0010 have tested downgrade paths), **or** restore the dump taken in step "Backup":
   `pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists backups/db-<stamp>.dump` and `tar xzf uploads-<stamp>.tgz` into the volume.
4. Verify `/ready`, login, case list; record the incident in `docs/DECISIONS.md`.

## What rollback does not do
It never touches `main`, never contacts customs systems, and never deletes audit history (DB trigger rejects UPDATE/DELETE/TRUNCATE).
