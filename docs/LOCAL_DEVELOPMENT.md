# LOCAL DEVELOPMENT

Two supported modes. **Native** is what this repository was built and verified with; **Docker Compose** is prepared for staging and
must be smoke-tested on a host with a Docker daemon (none was available in the build session — see `docs/LOCAL_ACCEPTANCE_REPORT.md`).

## Native (recommended for development)
Requirements: Python 3.12, Node 22, PostgreSQL 16 running locally.
```bash
make db            # role vip_customs + DBs vip_customs / vip_customs_test (local-only credentials)
make setup         # venv + pip install -e '.[dev]'; npm ci
make db-migrate    # alembic upgrade head → 0010_copilot_meta
SEED_DEMO_PASSWORD='choose-≥10-chars' make seed   # demo users + datasets + case VIP-HQ-261008-001
make dev           # API :8000 (+ /docs) and web :5173
```
Login with `reviewer@demo.local` (or operator / senior / admin `@demo.local`) and the password you chose.

## Docker Compose (staging shape)
```bash
cp .env.example .env    # set POSTGRES_PASSWORD and APP_SECRET_KEY (≥32 chars); never commit .env
make docker-up          # postgres:16 + api (runs alembic upgrade head on start) + web (vite)
```
Health: `curl localhost:8000/health` · readiness: `curl localhost:8000/ready` (DB + migration head + AI provider).

## Daily commands
| Task | Command |
|---|---|
| backend tests | `make test-api` (schema rebuilt from zero on the test DB) |
| frontend tests / typecheck / build | `make test-web` · `make typecheck` · `make build` |
| lint | `make lint` |
| browser E2E on the real stack | `make e2e` (set `PW_CHROMIUM_PATH` to reuse an installed Chromium, else `npx playwright install chromium` once) |
| full verification | `make verify` |
| new migration | `cd apps/api && .venv/bin/alembic revision --autogenerate -m "..."` then review the file |

## Configuration (`.env.example`)
`APP_ENV` (development/test/staging/production), `DATABASE_URL`, `APP_SECRET_KEY` (required outside development),
`AI_PROVIDER` (`mock` only in this build), `OBJECT_STORAGE_PROVIDER` (`local`), `LOCAL_STORAGE_DIR`, `CORS_ORIGINS`.

## Layout
`apps/api/app/{core,models,services,ai,storage,api}` · `apps/api/alembic/versions` · `apps/api/tests` (+ `fixtures/minh_phat`) ·
`apps/web/src/{pages,components.tsx,api.ts}` · `apps/web/e2e` · `infra/docker-compose.yml` · `scripts/` · `docs/`.
