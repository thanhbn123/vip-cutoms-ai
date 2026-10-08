# STAGING DEPLOYMENT (prepared — not executed)

Scope: a single Docker host (VM) running `infra/staging/docker-compose.staging.yml`. No production, no customs-system connection.
Providers stay **mock** (`AI_PROVIDER=mock`): parser, HS, Copilot. Knowledge datasets are **DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING**.

## Components
| Service | Image | Exposure | Persistent data |
|---|---|---|---|
| postgres | postgres:16-alpine | internal only | volume `pgdata` |
| migrate | api image, `alembic upgrade head`, runs once before api | — | — |
| api | `apps/api/Dockerfile` (uvicorn, `--proxy-headers`) | internal only (`:8000`) | volume `uploads` (`LOCAL_STORAGE_DIR=/data/uploads`) |
| web | `apps/web/Dockerfile.staging` (static build on nginx) | internal only (`:80`) | — |
| proxy | caddy:2-alpine | `:80/:443` (configurable) | volumes `caddy_data`, `caddy_config` |

Reverse proxy: same origin for UI and API (`/api/*`, `/health`, `/ready`, `/docs` → api; rest → web). TLS: `TLS_MODE=internal` (self-signed,
private staging), `acme` (public DNS + 80/443 reachable), or `off` when an upstream terminator exists. Security headers + CSP are set in `Caddyfile`.

## Required inputs (owner) — see `docs/STAGING_SECRETS.md`
Host with Docker Engine ≥ 24 + Compose v2, 2 vCPU / 4 GB / 20 GB; `PUBLIC_HOST`; TLS mode; secrets (`POSTGRES_PASSWORD`, `APP_SECRET_KEY`);
decision whether to seed the demo tenant (`SEED_DEMO_PASSWORD`).

## Procedure
```bash
git clone <remote> vip-customs && cd vip-customs && git checkout <develop SHA from G14 evidence>
cp infra/staging/.env.staging.example infra/staging/.env   # fill values; chmod 600
cd infra/staging
docker compose -f docker-compose.staging.yml --env-file .env build
docker compose -f docker-compose.staging.yml --env-file .env up -d        # migrate runs to head, then api starts
docker compose -f docker-compose.staging.yml --env-file .env ps
curl -fsS https://$PUBLIC_HOST/health && curl -fsS https://$PUBLIC_HOST/ready   # add -k for TLS_MODE=internal
# optional demo tenant for acceptance:
docker compose -f docker-compose.staging.yml --env-file .env exec -e APP_ENV=development api python scripts/seed_demo.py --with-case
```
`seed_demo.py` refuses to run unless `APP_ENV` is development/test — the override above is deliberate and should be removed after acceptance.

## Migration procedure (every deploy)
1. `docker compose … pull/build` the new `IMAGE_TAG`. 2. Backup (`docs/STAGING_ROLLBACK.md`). 3. `up -d` → the `migrate` service applies
`alembic upgrade head` and must exit 0 before api starts. 4. Verify `/ready` reports the expected head (`checks.migrations`).
Migrations are forward-only in production practice; downgrade scripts exist for all revisions (`alembic downgrade <rev>`), tested 0010→0008→0010.

## Health checks
`/health` (liveness), `/ready` (DB + migration head + provider; 503 when not ready). Compose healthchecks on postgres and api; the proxy only
starts routing when api/web are up. Restart policy `unless-stopped`.

## Smoke tests after deploy
`docs/STAGING_ACCEPTANCE.md` §Smoke (health/ready, login, nav, the V12 case, release gate BLOCKED, preview draft).
