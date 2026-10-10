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

## G18F-2 — self-review of the G18F diff (same day)

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | The web header showed role and mode but not **which tenant** the session belongs to — a person holding accounts in several tenants could not tell them apart | sidebar shows `· <tenant_code>` from `/auth/me` | `App.test.tsx` |
| 2 | After `TENANT_REQUIRED` the UI asked the user to **type** the tenant code although the API had already returned the list (to the password holder only) | the field becomes a `<select>` of the returned tenants; free text remains for the manual "Đăng nhập theo mã tenant" path and when no list came back | `Login.test.tsx` (4) |
| 3 | A lockout reached through a **wrong tenant code** locked the real account (pair/e-mail keys are tenant-agnostic) but produced **no `auth.login_locked` audit**, because the candidate list had been filtered by tenant | the audit covers every active account holding the e-mail, with `tenant_code_given` in `after` | `test_lockout_through_a_wrong_tenant_code_still_audits_the_real_account` |
| 4 | The staging negative suite had no tenant-aware probe | `negative_tests.py` +2: unknown tenant code → generic 401 `INVALID_CREDENTIALS`; `tenant: "demo"` (case-insensitive) → 200 with `tenant_code = DEMO` — the suite is now **20** checks | run against the local Docker stack (`artifacts/test-results/g18f2-docker.txt`) |

Considered and kept as is: `TENANT_REQUIRED` discloses the tenant list to a caller who already holds a valid password
(needed so the person can pick; counted as a failed attempt so it cannot be used to probe); `User.tenant` is eager-joined
(one extra join on user loads, negligible); the e-mail dimension of the throttle remains shared across tenants by design.
