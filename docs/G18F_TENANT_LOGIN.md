# G18F — Tenant-aware login (closes the cross-tenant e-mail oracle)

Owner request (2026-10-10): "làm đăng nhập theo tenant đi". Closes `docs/G18C_REVIEW_REMEDIATION.md` finding #13
(the only documented limitation of the G18C review) and supersedes the "global e-mail" part of D-012. Decision: D-042.

## What changed

| Area | Before | After (G18F) |
|---|---|---|
| Identity | `users.email` globally UNIQUE | UNIQUE per tenant: `uq_users_tenant_email (tenant_id, email)` + `ix_users_email` (migration `0013_tenant_scoped_email`) |
| `POST /auth/login` | `{email, password}` | `{email, password, tenant?}`; `tenant` = tenant code, case-insensitive, optional |
| Resolution | one user per e-mail | all **active** accounts holding the e-mail (narrowed by tenant code when given); the password is verified against each candidate; exactly one match → token for that account |
| Ambiguity | n/a | password valid in ≥ 2 tenants and no tenant code → `401 TENANT_REQUIRED` with `details.tenants` (only reachable by the password holder); counted as a failed attempt |
| Wrong password / unknown e-mail / unknown or wrong tenant code | `401 INVALID_CREDENTIALS` | same generic `401 INVALID_CREDENTIALS` (unknown e-mails still pay a dummy hash check) |
| `POST /users` (ADMIN) | 409 if the e-mail exists **anywhere** (oracle) | 409 only if it exists **in the admin's tenant** |
| `UserOut` | — | `tenant_code` added (login response, `/auth/me`, `/users`) |
| Throttling | keys `ip\|email`, `email`, `ip` | unchanged and deliberately tenant-agnostic: naming a tenant never grants a fresh budget; a lockout is audited for **every** candidate account |
| Web login | e-mail + password | optional "Mã tenant" field (link to reveal; auto-revealed and required after `TENANT_REQUIRED`); not sent when empty |
| Seed script | looked up users by e-mail globally | scoped to the DEMO tenant |

Back-compat: every existing client (acceptance scripts, Playwright, operator runbook, demo users) logs in exactly as
before because each demo/test e-mail exists in one tenant. Tokens are unchanged (`sub`, `tid`, `role`, `exp`) and
`current_user` still rejects a token whose `tid` differs from the user's tenant.

## Security reasoning

- **No enumeration**: an unauthenticated caller cannot distinguish "e-mail unknown", "wrong password", "wrong tenant"
  or "e-mail in several tenants" — all are `INVALID_CREDENTIALS`. `TENANT_REQUIRED` needs a password that is valid in
  at least two tenants, i.e. the account holder, and the attempt is still counted by the throttle.
- **Oracle removed**: a tenant ADMIN creating an account learns only about their own tenant.
- **Cost bound**: the number of hash verifications per request equals the number of active accounts holding that
  e-mail, bounded by the number of tenants; the throttle still runs before any hashing.
- **Database guarantee**: the per-tenant uniqueness is a constraint, not just an application check; the `downgrade`
  refuses to run while the same e-mail exists in two tenants (fail closed, no silent data loss).

## Tests (`apps/api/tests/test_g18f_tenant_login.py`, 9; `apps/web/src/Login.test.tsx`, 3)

same e-mail in two tenants selected by tenant code (case-insensitive) with tenant-bound tokens · unique e-mail without
code · wrong/unknown tenant code → generic 401 · ambiguous + same password → `TENANT_REQUIRED`, wrong password stays
generic · ambiguous + different passwords resolves by password · inactive accounts are not candidates · ADMIN creates an
e-mail that exists in another tenant (201, not 409) and the per-tenant 409 remains · DB constraint per tenant · tenant
code grants no fresh throttle budget, lockout audited per candidate · `TENANT_REQUIRED` counts as a failure.
Web: field not sent when empty · `TENANT_REQUIRED` reveals the field and the retry carries the code · generic error.

## Operator notes

- Deploying `0013` on staging: `alembic upgrade head` after `0012`; nothing to backfill. Rollback requires that no e-mail
  is duplicated across tenants (the downgrade checks and refuses otherwise).
- Users who hold accounts in several tenants with the same password will be asked for the tenant code once; the UI
  guides them. Tenant codes are the `tenants.code` values (e.g. `DEMO`).
