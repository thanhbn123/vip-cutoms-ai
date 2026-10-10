# G18I — Owner acceptance extended to tenant login and account lifecycle (steps Q–R)

`scripts/acceptance_http.py` is what the operator runs against staging (`scripts/staging/acceptance.sh` §3) and what
`scripts/docker_acceptance.sh` runs against the compose stack. Until G18I it stopped at P (historical learning), so
nothing the owner executes on a deployed stack exercised G18F–G18H. Two steps added; the flow is now **A–R, 19 steps**.

| Step | Asserts |
|---|---|
| **Q** tenant-aware login | `tenant: "demo"` (lower-case) → 200 and `user.tenant_code == "DEMO"`; unknown tenant code → 401; wrong password → 401; both failures carry the same `INVALID_CREDENTIALS` code (no enumeration) |
| **R** account lifecycle + audit | ADMIN creates a colleague (time-stamped e-mail, so a re-used database is fine) → 201; re-role to REVIEWER → 200; ADMIN deactivating themselves → 409; colleague logs in, changes their own password → 200 with a fresh token, the pre-change token → 401, the fresh one → 200; ADMIN deactivates the colleague → 200, the colleague's token → 401 and re-login → 401; `GET /audit?entity_type=user` holds `user.created`, `user.updated`, `auth.password_changed`, `user.deactivated` for that account |

Also in this gate: `docs/ACCEPTANCE.md` gains the security criteria these steps prove (tenant-aware login without
enumeration, audited tenant-scoped lifecycle, token voiding, throttling, readable tenant audit) and records that browser
E2E runs in CI; `docs/ROADMAP.md` gains G15–G19 entries (it ended at G14); the operator runbook expects **A–R 19/19**.

Verified: native stack on a fresh database (`19/19`), compose stack via `scripts/docker_acceptance.sh`, negative suite
`20/20`. The deactivated acceptance account stays in the tenant as an inactive row (accounts are never deleted, D-036).
