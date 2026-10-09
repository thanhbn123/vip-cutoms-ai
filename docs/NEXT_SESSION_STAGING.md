# NEXT SESSION — STAGING

Inputs the owner must provide first (BLOCKED_OWNER): B-01 OCR/LLM provider + credentials (or confirm mock for staging acceptance) ·
B-02 authoritative tariff/FTA/policy source · B-03 staging host, domain, TLS, secret store for `APP_SECRET_KEY` / DB password ·
B-04 review the `develop` branch (PR to `main` only after staging acceptance).

## Plan
1. ~~Docker smoke~~ — done in G14 (`docs/G14_DOCKER_STAGING_PREFLIGHT.md`, `artifacts/test-results/docker-smoke.txt`). Staging package: `infra/staging/`, `docs/STAGING_DEPLOYMENT.md`, `docs/STAGING_ACCEPTANCE.md`, `docs/STAGING_ROLLBACK.md`, `docs/STAGING_SECRETS.md`.
2. **Provision staging** (single VM or container host): PostgreSQL 16 managed or container with volume; object storage (S3-compatible) → implement `S3Storage` behind `app/storage/base.py`.
3. **Providers**: implement `app/ai/<provider>.py` for OCR/LLM behind `AIProvider`; keep `mock` for CI. Output validation already exists in `services/mapping.parse_document` and `services/copilot.ask`.
4. **Knowledge**: load the owner-approved tariff/FTA/policy datasets as new `knowledge_datasets` versions (`is_demo=false`, effective dates, source refs); demo rows stay inactive.
5. **Hardening**: OIDC or short-lived tokens with revocation, rate limiting, security headers, structured logs + request ids, backups rehearsal (`docs/RUNBOOK.md`).
6. **Acceptance on staging**: walk the 16-step flow in the UI with the demo case; capture screenshots; then decide the PR `develop → main`.

## Do not
Connect to VNACCS/ECUS; present demo datasets as legal data; commit any secret.
