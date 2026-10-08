# RUNBOOK — local / staging-candidate operation

## Prerequisites
Python 3.12, Node 22, PostgreSQL 16 (native or Docker). No external credentials are required: the AI provider is `mock`.

## 1. Databases (native PostgreSQL)
```bash
bash scripts/dev_db.sh            # creates role vip_customs + DBs vip_customs, vip_customs_test (local-only creds)
```
Or with Docker: `cp .env.example .env`, set `POSTGRES_PASSWORD`, `APP_SECRET_KEY` (and `POSTGRES_HOST_PORT` if 5432 is taken), then `make docker-smoke` / `docker compose -f infra/docker-compose.yml --env-file .env up --build`. Staging shape: `infra/staging/` + `docs/STAGING_DEPLOYMENT.md`.

## 2. API
```bash
cd apps/api && python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
export DATABASE_URL=postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs
.venv/bin/alembic upgrade head                     # head: 0008_copilot_memory
SEED_DEMO_PASSWORD='<choose ≥10 chars>' .venv/bin/python scripts/seed_demo.py --with-case
.venv/bin/uvicorn app.main:app --reload --port 8000
```
Health: `GET /health` (liveness), `GET /ready` (DB + migration head + provider). OpenAPI: `http://localhost:8000/docs`.
Demo users (development only, created by the seed, password = `SEED_DEMO_PASSWORD`): `operator@demo.local`, `reviewer@demo.local`, `senior@demo.local`, `admin@demo.local`.

## 3. Web
```bash
cd apps/web && npm ci && npm run dev               # http://localhost:5173 (proxies /api → :8000)
```

## 4. Verification (what CI runs)
```bash
bash scripts/verify.sh   # ruff, pytest on PostgreSQL, single alembic head, tsc, vitest, vite build, secret scan
```

## 5. Operational notes
- **Secrets**: `APP_SECRET_KEY` (≥32 chars) is mandatory outside development; the API refuses to start without it. Never commit `.env`.
- **Uploads**: stored privately under `LOCAL_STORAGE_DIR` (keyed `tenant/case/document-id`); the DB holds keys only. Back up this directory together with the database.
- **Backup**: `pg_dump vip_customs > backup.sql` + copy of `LOCAL_STORAGE_DIR`. **Restore**: `psql vip_customs < backup.sql`, restore the directory, `alembic upgrade head`.
- **Rollback**: `alembic downgrade <rev>` exists for every migration; application rollback = redeploy the previous commit/image. Audit rows are append-only (DB trigger).
- **Audit integrity**: `GET /api/v1/audit/verify` recomputes the per-tenant SHA-256 hash chain.
- **Knowledge datasets**: every seeded dataset is `is_demo=true` and labelled NON-AUTHORITATIVE. Admins can deactivate a dataset; evaluators then fail closed (CRITICAL issue) instead of guessing.
- **No customs submission**: there is no VNACCS/ECUS adapter. "Phát hành" only produces an internal, watermarked, versioned draft.
