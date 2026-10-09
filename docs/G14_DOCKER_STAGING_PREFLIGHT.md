# G14 — DOCKER / STAGING PREFLIGHT · 2026-10-08

| | |
|---|---|
| BASE SHA (develop at start) | `9c1e6a6f57cd61cf6ac450d27b9f3183c415b78a` (= expected; `origin/main` = `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0`, unchanged) |
| HEAD SHA (this gate) | `see `git log feature/g14-docker-staging-preflight` (part 1 `165cb0b`, part 2 `1189695`, evidence fixes after)` on `feature/g14-docker-staging-preflight` |
| Docker | Engine 29.8.2 (Server), API 1.56, storage overlayfs · Compose v5.6.0 |
| Daemon | not running at session start; started `dockerd` in-session (root). On a developer Mac: start Docker Desktop (`open -a Docker`) before `make docker-smoke`. |

## Clean Docker boot (`scripts/docker_smoke.sh` → `artifacts/test-results/docker-smoke.txt`)
`down -v --remove-orphans` → `build --no-cache` → `up -d` → host-side checks. Fresh `.env` from `.env.example` with generated `POSTGRES_PASSWORD` / `APP_SECRET_KEY` (never committed).

| Item | Result |
|---|---|
| Build (api + web, `--no-cache`) | PASS — `build_exit=0`, api + web images in ~20 s (`vip-customs-api:latest`, `vip-customs-web:latest`) |
| Containers | vip-customs-postgres-1 (postgres:16-alpine, healthy, host :55432) · vip-customs-api-1 (:8000) · vip-customs-web-1 (:5173); restart counts 0/0/0 |
| Migration from empty volume | PASS — `alembic current` = `0010_copilot_meta (head)`, `alembic heads` = 1, 21 tables created from an empty volume |
| `GET /health` (host) | 200 `{"status":"ok","service":"vip-customs-api","version":"0.1.0"}` |
| `GET /ready` (host) | 200 `{"status":"ready","checks":{"database":"ok","migrations":"0010_copilot_meta","ai_provider":"mock","environment":"development"}}` |
| Frontend (host) | `HTTP/1.1 200 OK` on :5173 |
| Logs (200 lines/service) | no traceback / crash loop / DB connection error (one benign postgres line: logical replication launcher exited) |
| Secret leak check | 0 occurrences of POSTGRES_PASSWORD / APP_SECRET_KEY in `docker compose logs` |

Environment-specific fixes made during the gate (all generic, no host details committed):
- `POSTGRES_HOST_PORT` (default 5432) — the first boot failed with "address already in use" because a native PostgreSQL held 5432.
- Optional BuildKit secret `ca_bundle` (`BUILD_CA_BUNDLE`, default `/dev/null`) — this host's egress is TLS-intercepted, so `pip`/`npm` inside BuildKit needed the CA; absent → default trust store, TLS never disabled (D-026).
- api image now carries `tests/fixtures` so `seed_demo.py --with-case` works inside the container.
- Dockerfile upgrades `pip` (pip-audit flagged the base image's pip 24.0).

## Docker acceptance flow (`scripts/docker_acceptance.sh` → `artifacts/test-results/docker-acceptance.txt`)
Seed inside the api container → Playwright against the Docker web → HTTP A–P (`scripts/acceptance_http.py`) against the Docker api.

| Step | Result |
|---|---|
| seed inside api container | tenant DEMO, 4 users, 4 demo datasets, case VIP-HQ-261008-001 → BLOCKED (4 docs parsed) |
| Playwright vs Docker web | **1 passed** (login → V12 nav → CT-88 8537 64% BLOCKED, ABC-500 87%, PVC-20 95% → Copilot → gate BLOCKED → declaration) |
| HTTP A–P vs Docker api | **17/17 PASS** — A login · B case · C 4 docs · D mock parse · E 124/126 conflict · F 3 items · G 0.87/0.95/0.64 · H CIF 18420.00 · I C/O+policy demo rules · J Copilot · K reviewer resolution + audit chain · L gate · M READY_TO_EXPORT · N release draft JSON+CSV w/ legal notice · O approved-only memory · P similar case EXACT +0.05 |
| containers after flow | all Up, restart counts 0; 11 documents in the `uploads` volume |

## Full test suite, clean state (`scripts/collect_evidence.sh`, native stack, alternate E2E ports)
| Check | Result |
|---|---|
| backend pytest | PASS — 68 passed |
| frontend vitest | PASS — 3 passed (2 files) |
| typecheck (tsc) | PASS |
| lint (ruff) | PASS |
| build (vite) | PASS |
| Playwright (native stack) | PASS — 1 passed (ports 8010/5183, test DB from zero) |
| migration from zero + downgrade/upgrade | PASS — 0001→0010, downgrade 0010→0008, upgrade → head, single head |
| api smoke | PASS — health/ready 200, login, cases, 401 unauth |

## Security preflight (`artifacts/test-results/security-preflight.txt`)
secret scan clean · no `.env`/keys/tokens tracked · `pip-audit`: only the venv's own `pip 24.0` flagged (tooling; Dockerfile upgrades pip) ·
`npm audit --omit=dev`: 0 vulnerabilities (dev-only advisories exist in test tooling) · RBAC / tenant-isolation / upload-validation / waiver tests:
16 passed · storage path traversal (`../`, absolute keys) rejected · logs contain no secrets.

## Demo safety labels (D-029, `tests/test_demo_labels.py`)
Every knowledge dataset: `is_demo=true`, label **DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING**, version `demo-*`, source recorded.
Surfaces carrying the wording: Knowledge Hub, persistent app banner (`/knowledge/notice`), Goods assessments badge, declaration `demo_notice` +
disclaimer, draft JSON `meta.legal_notice`, draft CSV header. Rule-derived values (HS candidates, tax, C/O, policy) always reference the dataset version.

## Known mocks
OCR/LLM provider `mock` (parser, HS reasoning templates, Copilot templates); local file storage; no VNACCS/ECUS adapter.

## Known demo datasets
`HS_RULES demo-hs-2026.10` · `TARIFF demo-tariff-2026.10` · `FTA demo-fta-2026.10` · `POLICY demo-policy-2026.10` — fixtures in
`apps/api/app/services/demo_fixtures.py`, seeded by `scripts/seed_demo.py` / lazily in development, never in staging/production.

## Staging package (prepared, NOT deployed)
`infra/staging/docker-compose.staging.yml` (postgres · one-shot migrate · api · static web/nginx · Caddy TLS proxy), `infra/staging/Caddyfile`,
`infra/staging/.env.staging.example`, `apps/web/Dockerfile.staging`, `docs/STAGING_DEPLOYMENT.md`, `docs/STAGING_ACCEPTANCE.md`,
`docs/STAGING_ROLLBACK.md`, `docs/STAGING_SECRETS.md`. Staging boots with `AI_PROVIDER=mock`. No IP/domain hard-coded.
Not executed here: the staging compose itself (needs `PUBLIC_HOST`; the dev compose is what was booted).

## Blockers
B-01 provider credentials (not needed for staging boot) · B-02 authoritative customs data · B-03 staging host/TLS/secrets · B-04 owner review of `develop`.
