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

## Verification
Backend pytest **166 passed**, 1 skipped · infra pytest **106** · vitest **7** · `VERIFY: ALL CHECKS PASSED` ·
Playwright native **2/2** · Docker boot from zero + acceptance A–P **17/17** (results recorded in
`artifacts/test-results/g18d-*.txt`).
