# G14 — DOCKER / STAGING PREFLIGHT · 2026-10-08

| | |
|---|---|
| BASE SHA (develop at start) | `9c1e6a6f57cd61cf6ac450d27b9f3183c415b78a` (= expected; `origin/main` = `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0`, unchanged) |
| HEAD SHA (this gate) | `__HEAD_SHA__` on `feature/g14-docker-staging-preflight` |
| Docker | Engine 29.8.2 (Server), API 1.56, storage overlayfs · Compose v5.6.0 |
| Daemon | not running at session start; started `dockerd` in-session (root). On a developer Mac: start Docker Desktop (`open -a Docker`) before `make docker-smoke`. |

## Clean Docker boot (`scripts/docker_smoke.sh` → `artifacts/test-results/docker-smoke.txt`)
`down -v --remove-orphans` → `build --no-cache` → `up -d` → host-side checks. Fresh `.env` from `.env.example` with generated `POSTGRES_PASSWORD` / `APP_SECRET_KEY` (never committed).

| Item | Result |
|---|---|
| Build (api + web, `--no-cache`) | __BUILD__ |
| Containers | __CONTAINERS__ |
| Migration from empty volume | __MIGRATION__ |
| `GET /health` (host) | __HEALTH__ |
| `GET /ready` (host) | __READY__ |
| Frontend (host) | __FRONTEND__ |
| Logs (200 lines/service) | __LOGS__ |
| Secret leak check | __LEAK__ |

Environment-specific fixes made during the gate (all generic, no host details committed):
- `POSTGRES_HOST_PORT` (default 5432) — the first boot failed with "address already in use" because a native PostgreSQL held 5432.
- Optional BuildKit secret `ca_bundle` (`BUILD_CA_BUNDLE`, default `/dev/null`) — this host's egress is TLS-intercepted, so `pip`/`npm` inside BuildKit needed the CA; absent → default trust store, TLS never disabled (D-026).
- api image now carries `tests/fixtures` so `seed_demo.py --with-case` works inside the container.
- Dockerfile upgrades `pip` (pip-audit flagged the base image's pip 24.0).

## Docker acceptance flow (`scripts/docker_acceptance.sh` → `artifacts/test-results/docker-acceptance.txt`)
Seed inside the api container → Playwright against the Docker web → HTTP A–P (`scripts/acceptance_http.py`) against the Docker api.

__ACCEPTANCE__

## Full test suite, clean state (`scripts/collect_evidence.sh`, native stack, alternate E2E ports)
| Check | Result |
|---|---|
| backend pytest | __PYTEST__ |
| frontend vitest | __VITEST__ |
| typecheck (tsc) | __TSC__ |
| lint (ruff) | __RUFF__ |
| build (vite) | __VITE__ |
| Playwright (native stack) | __PW__ |
| migration from zero + downgrade/upgrade | __MIG2__ |
| api smoke | __APISMOKE__ |

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
