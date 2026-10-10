# G18G — User lifecycle: ADMIN account management, self-service password change, token voiding

Why now: after G18F an ADMIN could only *create* users (API only). There was no way to deactivate or reactivate an
account, change a role, reset a forgotten password, or for a person to change their own password — so B-07 (retire
the demo users) needed a shell script on the host, and onboarding a real tenant needed `curl`. G18G closes that gap as
a vertical slice (API + UI + audit + tests) without touching anything that needs an owner decision. Decision: D-043.

## API (all tenant-scoped; other tenants' users look non-existent — 404, no leak)

| Endpoint | Who | Behaviour |
|---|---|---|
| `PATCH /users/{id}` `{full_name?, role?, is_active?, reason}` | `user.manage` (ADMIN) | rename / re-role / deactivate / reactivate a colleague. Refuses: changing **own** role or active flag (`409 SELF_CHANGE_FORBIDDEN`), removing the tenant's last active ADMIN (`409 LAST_ADMIN`, defence in depth), a no-op (`422 NO_CHANGE`). Audit `user.updated` / `user.deactivated` / `user.reactivated` with before/after + reason |
| `POST /users/{id}/reset-password` `{password ≥10, reason}` → 204 | `user.manage` | sets a new password for a colleague; **all of that user's tokens become void**. Not for one's own account (409). Audit `user.password_reset` (never contains the password) |
| `POST /auth/change-password` `{current_password, new_password ≥10}` → fresh `TokenOut` | any signed-in user | requires the current password; wrong guesses count against the login throttle (pair + e-mail dimensions → 429); same password refused (`422 SAME_PASSWORD`). Audit `auth.password_changed`. Every older token is void; the response carries the replacement token |
| `UserOut.is_active` | — | added; `GET /users` now lets the UI show inactive accounts |

### Stateless revocation (migration `0014_password_changed_at`)
Tokens are HMAC-signed and stateless (D-012). G18G adds `iat` to every token and `users.password_changed_at`;
`current_user` refuses a token whose `iat` is older than the last password change (a token without `iat` counts as
issued at epoch 0, so pre-G18G tokens die at the first password change). Deactivation already killed tokens
(`is_active` check). Role changes apply immediately because permissions are read from the DB row, not the token.
Granularity is one second: a token issued in the same second as the change survives — that is the token the change
endpoint itself returns.

## Web
- **Quản trị → Roles & users** (ADMIN): inactive badge, role `<select>` per colleague, `vô hiệu hoá` / `kích hoạt lại`,
  `đặt lại mật khẩu`, `Tạo tài khoản` form. The admin's own row shows `(bạn)` and no self-locking controls. Every action
  asks for a reason (≥5 chars) and shows the API error verbatim on failure.
- **Sidebar → Đổi mật khẩu** (everyone): current + new password prompts; the fresh token replaces the stored one.

## B-07 consequence
Retiring the demo users no longer needs SSH: an ADMIN of tenant DEMO (a real one, created first) can deactivate
`operator/reviewer/senior/admin@demo.local` from the UI; each deactivation is a `user.deactivated` audit event by that
admin. `scripts/staging/deactivate_demo_users.sh` remains the batch alternative (SYSTEM actor). `--verify` of that
script still confirms the end state either way.

## Tests
`apps/api/tests/test_g18g_user_lifecycle.py` (6): rename/re-role/deactivate/reactivate with audit and immediate
effect on existing tokens · self-change / no-change / cross-tenant 404 / RBAC 403 guards · two-admin rotation and
the last-admin helper · admin reset voids old tokens, audit has no password, self-reset refused · self-service change:
wrong current → 401, same → 422, success returns a working fresh token and kills the old one, guesses throttle to 429 ·
legacy tokens without `iat` work until the first password change. `Manage.test.tsx` (+2): admin controls call the
audited API with reasons, reviewer sees read-only. Playwright/Docker acceptance unchanged (login flow untouched).

## Not done (owner or later)
No e-mail delivery (no mail provider is an owner input), so a reset password is handed over out of band — the UI says
so. No password-complexity policy beyond length ≥10 (owner policy, `docs/G18_OWNER_INPUTS.md`). No session list /
"log out everywhere" beyond the implicit voiding by password change.
