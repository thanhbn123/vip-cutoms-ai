# G18H — Tenant-level audit feed, browser coverage of account flows, Playwright in CI

Three gaps left after G18G, all closable without an owner decision:

1. **Audit events that belong to no case were invisible.** `user.*`, `auth.login_locked`, `auth.password_changed`,
   knowledge import/verify/supersede are all written to the append-only chain (D-013), but the only reader was
   `GET /cases/{id}/audit`. Rule 9 ("every critical state transition must be audited") is only useful if someone can
   look. → `GET /audit` (tenant feed) + the Audit card on *Quản trị* defaults to it.
2. **No browser test touched tenant-code login or account management.** → `apps/web/e2e/admin-users.spec.ts`.
3. **Playwright ran only on a developer machine / in the Docker acceptance script, never in CI.** → `e2e` job.

## API
`GET /audit?entity_type=&action_prefix=&include_cases=false&limit=100` (`audit.read`, every role in its own tenant):
newest first, tenant isolation in the query, `case_id IS NULL` unless `include_cases=true`, `action_prefix` is a
literal prefix (`%`/`_` escaped, not a LIKE pattern), `limit` 1–500. Same `AuditOut` shape as the case audit.
Test: `apps/api/tests/test_g18h_audit_feed.py`.

## Web
*Quản trị → Audit* has a scope select: **Tenant (tài khoản, knowledge, lockout)** (default, `/audit?limit=50`) or
**Hồ sơ đang chọn** (the previous behaviour). Account actions on the same page refresh the feed, so an ADMIN sees the
`user.deactivated` row with its reason right after clicking. Vitest: `Manage.test.tsx` (+1).

## Browser E2E (`admin-users.spec.ts`)
admin logs in with the tenant code `demo` (case-insensitive) → sidebar shows `ADMIN · DEMO` → *Quản trị* → own row is
`(bạn)` → creates a colleague (fresh e-mail per run, so a re-used database is fine) → re-roles via the select → deactivates
with a prompted reason → inactive badge → tenant audit shows `user.created` / `user.updated` / `user.deactivated` with the
reason → logs out → the deactivated colleague gets the generic `invalid email, tenant or password`.
Runs in `scripts/e2e.sh` (3 specs) and inside `scripts/docker_acceptance.sh` against the compose stack.

## CI
New `e2e` job in `.github/workflows/ci.yml`: PostgreSQL 16 service, Python 3.12 + Node 22, `pip install -e apps/api[dev]`,
`npm ci`, `npx playwright install --with-deps chromium`, `E2E_PYTHON=python bash scripts/e2e.sh`; API/Vite logs are
uploaded as an artifact on failure. `scripts/e2e.sh` gained `E2E_PYTHON` (default: the repo venv) for that purpose.
CI now has five jobs: api · web · infra · e2e · secrets.
