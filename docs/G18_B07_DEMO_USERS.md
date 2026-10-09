# G18 — B-07: STAGING DEMO USERS (inventory, mechanism, runbook)

## 1. Inventory (from the seed, `apps/api/scripts/seed_demo.py`)

| E-mail | Role | Tenant | Purpose | Real workflow depends on it? |
|---|---|---|---|---|
| `operator@demo.local` | OPERATOR | DEMO | acceptance flow A–P, Playwright | no — test-only |
| `reviewer@demo.local` | REVIEWER | DEMO | acceptance flow, negative tests | no |
| `senior@demo.local` | SENIOR_REVIEWER | DEMO | critical waiver / override tests | no |
| `admin@demo.local` | ADMIN | DEMO | knowledge toggles, user creation in tests | no |

All four exist on staging (`hq.vipgroup.com.vn`) with the password set at G15C acceptance. They are the only
accounts in tenant DEMO. Their historical actions (case `VIP-HQ-261008-001`, reviewer decisions, audit chain)
must remain attributable → **deactivate, do not delete** (G16 recommendation, now implemented).

## 2. Mechanism (implemented, tested)

- `apps/api/scripts/deactivate_demo_users.py` — targets **only** `^[a-z0-9._-]+@demo\.local$`; aborts if the
  LIKE filter and the regex disagree; default is read-only inventory; `--execute` requires
  `DEACTIVATE_CONFIRM=demo.local`; sets `is_active=false`; one `user.deactivated` audit event per account
  (SYSTEM actor, reason recorded); idempotent (already-inactive accounts are skipped, no duplicate events);
  `--verify` exits 1 while any demo account is active or no non-demo ADMIN remains active in the tenant.
- Login path already enforces `is_active` before the password check (`app/api/auth.py`), so a deactivated
  account cannot obtain a token; existing tokens expire within `TOKEN_TTL_SECONDS` (8 h).
- `scripts/staging/deactivate_demo_users.sh` — operator wrapper that runs the script **inside** the `api`
  container (no DB credential leaves the host), asks for the confirmation token, then proves a demo login
  returns 401 and `/ready` is unchanged.
- Production seed never creates demo users: `seed_demo.py` refuses outside `APP_ENV=development/test`
  (`test_seed_refuses_outside_development`), and the production template has no `SEED_DEMO_PASSWORD`.

Tests: `apps/api/tests/test_g18_demo_users_and_failclosed.py` (filter exactness, read-only inventory, confirmation
token, login 401 + non-demo admin OK + audit + idempotency, verify, seed refusal) and
`tests/test_g18_production_prep.py` (wrapper contract).

## 3. Staging execution runbook (operator with the deploy key)

```bash
ssh deploy@160.22.170.20
cd /opt/vip-customs-ai && git fetch origin && git checkout -q <DEVELOP_SHA_WITH_G18>   # the script runs inside the running api image: rebuild/redeploy first if the image predates G18
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh              # 1. inventory — expect the 4 accounts, active=True
# optional: create a real ADMIN for tenant DEMO first if the tenant stays in use (POST /api/v1/users as admin@demo.local)
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --execute    # 2. type demo.local when prompted
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --verify     # 3. VERIFY: OK
curl -fsS https://hq.vipgroup.com.vn/ready | head -c 300                                    # 4. unchanged
```
Expected `--execute` output: `deactivated: [4 e-mails]`, `demo login -> 401 (expected 401)`, `VERIFY: OK`.
Record the output in `docs/G15_DEPLOY_RECORD.md` (staging log) and flip B-07 to RESOLVED in `docs/STATUS.md`.

Note: the api image on staging must contain `scripts/deactivate_demo_users.py` (it is copied by the Dockerfile),
i.e. staging must be redeployed to a `develop` SHA that includes G18 before step 2. That redeploy is a staging
change the owner must allow (it does not change the accepted runtime behaviour in limited mode).

## 4. Status after G18A

Mechanism: **READY**. Execution on staging: **NOT PERFORMED from this session** — the build session has no egress
to `160.22.170.20:22` or `hq.vipgroup.com.vn` (connections time out). B-07 stays **BLOCKED (operator execution
pending)** until the runbook above has been run and its output recorded.
