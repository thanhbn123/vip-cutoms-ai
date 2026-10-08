# STAGING READINESS (G13) — READY_FOR_STAGING = YES (local), staging execution needs owner inputs B-01…B-04

| Area | State | Evidence / gap |
|---|---|---|
| Backend API (FastAPI) | ✅ | 66 pytest on PostgreSQL 16 incl. 16-step acceptance; `/health`, `/ready` |
| Database + migrations | ✅ | Alembic 0001→0010, single head, downgrade verified; audit append-only trigger + hash chain |
| Auth / RBAC / tenant isolation | ✅ scaffold | HMAC tokens, PBKDF2, 4 roles, server-side checks, cross-tenant tests; **OIDC/IdP not integrated** |
| Document storage | ✅ local adapter | private directory, path-safe keys, sha256; **S3/NAS adapter not implemented** |
| Parser / OCR / LLM | ⚠️ mock only | deterministic provider behind `AIProvider`; real providers need credentials (B-01) |
| Knowledge (HS/tariff/FTA/policy) | ⚠️ demo fixtures | versioned, effective-dated, fail-closed; authoritative source = BLOCKED_OWNER (B-02) |
| Reviewer workflow / release gate / drafts | ✅ | state machine, issue actions, release gate, versioned JSON/CSV drafts, no submission |
| AI Copilot | ✅ mock | case-scoped, sources validated, proposals require a second reviewer |
| Historical learning | ✅ | approved-only memory, outcome flags, boost + "do not auto-copy" |
| Frontend | ✅ functional parity | nine V12 pages; Playwright E2E on the real stack PASS; pixel polish pending |
| Docker Compose | ⚠️ written, not executed | daemon unavailable in the build session; YAML validated; first task of the staging session |
| CI | ⚠️ CI_EXTERNAL_UNVERIFIED | `.github/workflows/ci.yml` present; not observable from the build session |
| Security review | ⚠️ partial | secret scan, RBAC tests, no public document URLs, CORS allow-list, fail-closed secret; **no pentest, rate limiting or CSP yet** |
| Backup / restore / rollback | 📄 documented | `docs/RUNBOOK.md`; not rehearsed on a staging host |

## Owner decisions required before staging (BLOCKED_OWNER)
1. **B-01** OCR/LLM provider + credentials (or accept mock for staging acceptance).
2. **B-02** Authoritative tariff / FTA / policy data source and update cadence.
3. **B-03** Staging host, domain, TLS, `APP_SECRET_KEY`, DB credentials (secret store, never git).
4. **B-04** Create `develop`, review/merge the PR from `claude/busy-davinci-9u8bye`; merge policy to `main`.

## Pre-staging engineering checklist (no owner input needed)
- [x] Playwright E2E on the real stack (`make e2e`); API-level 16-step acceptance (`tests/test_acceptance_mvp.py`)
- [ ] Rate limiting + security headers middleware
- [ ] S3-compatible storage adapter
- [ ] Token revocation / short-lived tokens or OIDC
- [ ] Observability: structured logs, request ids, metrics
- [ ] Run the demo case through the real UI on a staging host; screenshots for owner acceptance

## Local acceptance verdict
All local checks PASS (`docs/LOCAL_ACCEPTANCE_REPORT.md`). The only unexecuted item is the Docker Compose smoke, which needs a Docker daemon.
`main` is unchanged; `develop` is the release candidate for the staging session (`docs/NEXT_SESSION_STAGING.md`).
