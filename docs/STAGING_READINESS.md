# STAGING READINESS (G13) — READY_FOR_STAGING = NO (owner inputs required)

| Area | State | Evidence / gap |
|---|---|---|
| Backend API (FastAPI) | ✅ | pytest suite on PostgreSQL 16 (see PROJECT_STATUS.md for count); `/health`, `/ready` |
| Database + migrations | ✅ | Alembic 0001→0008, single head, downgrade paths; audit append-only trigger + hash chain |
| Auth / RBAC / tenant isolation | ✅ scaffold | HMAC tokens, PBKDF2, 4 roles, server-side checks, cross-tenant tests; **OIDC/IdP not integrated** |
| Document storage | ✅ local adapter | private directory, path-safe keys, sha256; **S3/NAS adapter not implemented** |
| Parser / OCR / LLM | ⚠️ mock only | deterministic provider behind `AIProvider`; real providers need credentials (B-01) |
| Knowledge (HS/tariff/FTA/policy) | ⚠️ demo fixtures | versioned, effective-dated, fail-closed; authoritative source = BLOCKED_OWNER (B-02) |
| Reviewer workflow / release gate / drafts | ✅ | state machine, issue actions, release gate, versioned JSON/CSV drafts, no submission |
| AI Copilot | ✅ mock | case-scoped, sources validated, proposals require a second reviewer |
| Historical learning | ✅ | approved-only memory, outcome flags, boost + "do not auto-copy" |
| Frontend | ✅ functional parity | nine V12 pages; pixel polish + Playwright E2E pending |
| Docker Compose | ⚠️ written, not executed | daemon unavailable in the build session; YAML validated only |
| CI | ⚠️ CI_EXTERNAL_UNVERIFIED | `.github/workflows/ci.yml` present; not observable from the build session |
| Security review | ⚠️ partial | secret scan, RBAC tests, no public document URLs, CORS allow-list, fail-closed secret; **no pentest, rate limiting or CSP yet** |
| Backup / restore / rollback | 📄 documented | `docs/RUNBOOK.md`; not rehearsed on a staging host |

## Owner decisions required before staging (BLOCKED_OWNER)
1. **B-01** OCR/LLM provider + credentials (or accept mock for staging acceptance).
2. **B-02** Authoritative tariff / FTA / policy data source and update cadence.
3. **B-03** Staging host, domain, TLS, `APP_SECRET_KEY`, DB credentials (secret store, never git).
4. **B-04** Create `develop`, review/merge the PR from `claude/busy-davinci-9u8bye`; merge policy to `main`.

## Pre-staging engineering checklist (no owner input needed)
- [ ] Playwright E2E for the acceptance path (API-level acceptance exists: `tests/test_acceptance_mvp.py`)
- [ ] Rate limiting + security headers middleware
- [ ] S3-compatible storage adapter
- [ ] Token revocation / short-lived tokens or OIDC
- [ ] Observability: structured logs, request ids, metrics
- [ ] Run the demo case through the real UI on a staging host; screenshots for owner acceptance
