# G18D — LOGIN THROTTLING (API LAYER) + KNOWLEDGE HUB STEWARD UI · 2026-10-09

Two items that needed no owner input.

## 1. Login throttling at the API layer (closes the G16 gap)

`apps/api/app/core/ratelimit.py` — in-process sliding window, applied in `POST /auth/login`:

| Setting | Default | Meaning |
|---|---|---|
| `LOGIN_MAX_ATTEMPTS` | 10 | failed attempts per key inside the window |
| `LOGIN_WINDOW_SECONDS` | 300 | sliding window |
| `LOGIN_LOCKOUT_SECONDS` | 300 | refusal period once the limit is reached |

Keys: client IP (uvicorn runs with `--proxy-headers` behind the stack's own Caddy, so the real peer address is
used) and lower-cased e-mail. A locked key is refused with **429 `TOO_MANY_ATTEMPTS`** and `Retry-After`
**before** the password hash is computed. A successful login clears the e-mail counter; the IP counter is not
cleared by a success (a client that keeps failing across accounts is still throttled). Unknown e-mails count the
same way, so throttling reveals nothing about account existence. `vip_login_throttled_total` is on `/metrics`.

Limits, stated: the counters are per `api` process. One container today; if the stack ever scales out, a shared
store (or the proxy layer) is the follow-up. Tests: `apps/api/tests/test_g18d_login_ratelimit.py` (window/lockout
arithmetic, 429 after N failures including with the correct password, e-mail reset vs IP persistence, unknown
e-mail, metric). The test suite resets the limiter between tests.

## 2. Knowledge Hub steward UI (`apps/web/src/pages/Knowledge.tsx`)

What the owner's data steward and verifier will use once a B-02 source exists:

- every dataset shows provenance (authority · legal document · reference), checksum prefix, verification date,
  supersession lineage, and badges `demo` / `chưa xác minh` / `authoritative` / `superseded`;
- `chi tiết` opens the dataset: the list of provenance problems (translated), or the legal-source line when it
  qualifies, plus the payload/rules;
- actions by permission: `bật/tắt` and `thay thế` (`knowledge.manage`), `xác minh` (`knowledge.verify` —
  ADMIN and SENIOR_REVIEWER), `Import gói dữ liệu (JSON)` (`knowledge.manage`) with a pre-filled package
  template and the reminder that an import lands INACTIVE and UNVERIFIED;
- header shows the runtime mode and which authoritative datasets are active; the demo banner stays while any
  demo dataset is active.

Tests: `apps/web/src/pages/Knowledge.test.tsx` (admin sees provenance/badges/actions and `verify` posts the
reason; a reviewer sees provenance but no management actions).

## 3. Admin readiness panel (`apps/web/src/pages/Manage.tsx`)
The "Production path" card now renders `/ready` structurally instead of `key=value` text: mode and build SHA, database
and migration-vs-head, each AI capability's provider (mock / healthy / unhealthy), authoritative status per knowledge
kind, off-host backup freshness, and the `blocking[]` list that explains a 503. Test: `Manage.test.tsx`.

## Verification
Backend pytest **166 passed**, 1 skipped · infra pytest **106** · vitest **8** · `VERIFY: ALL CHECKS PASSED` ·
Playwright native **2/2** · Docker boot from zero + acceptance A–P **17/17** (results recorded in
`artifacts/test-results/g18d-*.txt`).

## G18E — review of G18D and hardening (same day)

A high-effort review of the G18D diff found 11 items; all are closed.

| # | Finding | Fix |
|---|---|---|
| 1 | Limiter key store grew without bound (unique random e-mails → OOM) | `LOGIN_MAX_TRACKED_KEYS` (20 000) per dimension: stale keys swept, oldest evicted; `vip_login_tracked_keys{dimension}` gauge |
| 2 | One shared client address (NAT, upstream proxy with `TLS_MODE=off`) could lock every user with 10 failures | three dimensions with separate thresholds: **pair** (ip+e-mail, 10), **e-mail** (50), **ip** (100, `0` disables); a pair lock never affects other accounts or clients |
| 3 | Account-lockout DoS via the e-mail key not stated | pair key is the ordinary brake; the e-mail key needs 50 failures/window from rotating addresses to hold a victim locked — residual risk documented; CAPTCHA/proxy limits/SSO are owner-level mitigations (B-06, D-012) |
| 4 | Knowledge header badge failed open when `/knowledge/notice` errored | warning stays unless the notice positively reports no demo data — tested |
| 5 | Lock-time 429 not counted in `vip_login_throttled_total` | counted at lock time; `vip_login_locks_total` added |
| 6 | Admin panel printed `reason`/`error` keys as dataset kinds | only entries with an `authoritative` flag are kinds; `reason`/`error` shown as a note — tested |
| 7 | Import panel closed even when the import failed | `run` returns success; panel closes only on success |
| 8 | Prompt promised ≥3 chars but `ask` requires 5; supersede picker could not accept short versions | messages say ≥5 with feedback; picker uses a plain prompt with its own validation |
| 9 | `<div>` inside `Row`'s `<p>` (invalid nesting) | block-level `<span>` |
| 10 | `--forwarded-allow-ips "*"` trusts any peer's XFF | accepted and documented in the compose file: the api is reachable only on the compose-internal network from the stack's own proxy; never publish `api:8000` on a host interface |
| 11 | Lockouts not in the audit trail | `auth.login_locked` SYSTEM audit event when a known account enters the locked state |

Clean-checkout verification of develop `f2989b1` from zero (fresh clone, empty DB): migrate to `0012`, seed → BLOCKED,
ruff, **166** api / **106** infra / **8** vitest, tsc, build, Playwright **2/2**, secret scan clean.
