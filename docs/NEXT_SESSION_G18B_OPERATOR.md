# NEXT SESSION — G18B OPERATOR RUNBOOK (apply owner inputs on staging)

Audience: the operator holding the `deploy` key for `160.22.170.20` (`hq.vipgroup.com.vn`) and the owner's
data steward/verifier. Everything below is **staging only**; production stays undeployed until G19 is authorised.
Prerequisite reading: `docs/G18_OWNER_INPUTS.md` (what the owner must supply), `docs/G18A_REPORT.md`,
`docs/G18C_REVIEW_REMEDIATION.md`, `docs/G18D_LOGIN_THROTTLING_AND_KNOWLEDGE_UI.md`.

Current `develop` head to deploy: see the latest `PROJECT_STATUS.md` row (CI green). `main` stays at `4a2acb9`.

## 0. Before touching staging
```bash
git fetch origin && git log --oneline -1 origin/develop          # the SHA you will deploy; CI must be green on it
# read-only health of the current staging stack
curl -fsS https://hq.vipgroup.com.vn/health; curl -fsS https://hq.vipgroup.com.vn/ready | head -c 400
```
Expected today: `{"status":"ok",...}` and `/ready` 200 with `"migrations":"0010_copilot_meta"` (the G15C image).

## 1. Redeploy staging to the current develop SHA (limited mode)
The G15C image predates every G18 change (migrations 0011/0012, modes, throttling). Deploy with the same
pinned-SHA procedure as G15C; the stack defaults to `APP_MODE=limited`.
```bash
ssh deploy@160.22.170.20
cd /opt/vip-customs-ai
# add the G18 keys to infra/staging/.env (values are safe defaults; no credential yet):
#   APP_MODE=limited  METRICS_ALLOW_FROM=127.0.0.1/32  LOGIN_MAX_ATTEMPTS=10 LOGIN_EMAIL_MAX_ATTEMPTS=50 LOGIN_IP_MAX_ATTEMPTS=100
#   (set LOGIN_IP_MAX_ATTEMPTS=0 if the shared Caddy hides client addresses — check: curl -s https://hq.vipgroup.com.vn/ready from
#    two different networks and compare the api access log; if both show the proxy's address, disable the ip dimension)
DEPLOY_SHA=<develop sha> DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deploy.sh
```
deploy.sh takes a pre-deploy `pg_dump`, builds, migrates (`0010 → 0011 → 0012 → 0013`), prints `/health` `/ready`.
Expected `/ready`: `"mode":"limited"`, `"migrations":"0013_tenant_scoped_email"`, `migration_in_sync:true`,
`blocking: []`, providers all `mock`. Then from a client:
```bash
BASE_URL=https://hq.vipgroup.com.vn bash scripts/staging/acceptance.sh     # A–P 17/17, negative 18/18, Playwright, persistence, backup/restore
```
Rollback if anything fails: `docs/STAGING_ROLLBACK.md` (previous SHA `9649ec7`, restore the pre-deploy dump
**before** downgrading, because 0011/0012 added columns/tables and 0013 changed the e-mail uniqueness: `alembic downgrade 0010_copilot_meta` is available; 0013's downgrade refuses while one e-mail exists in two tenants).

## 2. B-07 — deactivate the demo users (after acceptance is signed off)
```bash
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh              # inventory: 4 accounts, active=True
# create a real ADMIN for tenant DEMO first if the tenant stays in use (POST /api/v1/users as admin@demo.local)
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --execute    # type demo.local
DEPLOY_PATH=/opt/vip-customs-ai bash scripts/staging/deactivate_demo_users.sh --verify     # VERIFY: OK
```
Record the output in `docs/G15_DEPLOY_RECORD.md`; set B-07 = RESOLVED in `docs/STATUS.md`.
Note: `scripts/staging/acceptance.sh` seeds and logs in as the demo users — run B-07 **after** the acceptance of §1.

## 3. B-01 — enable the real AI provider on staging (when the owner supplies vendor, endpoint, model, key, DPA)
In `infra/staging/.env` (chmod 600, never in Git):
```
AI_PROVIDER=http-llm
DOCUMENT_OCR_PROVIDER=mock            # until an OCR vendor is chosen: scans stay manual (fail closed)
AI_PROVIDER_BASE_URL=https://<vendor endpoint>/v1
AI_PROVIDER_API_KEY=<key>
AI_PROVIDER_MODEL=<model id>
AI_COST_PER_1K_INPUT_TOKENS_USD=<price>  AI_COST_PER_1K_OUTPUT_TOKENS_USD=<price>  AI_DAILY_BUDGET_USD=5
```
`docker compose ... up -d api` → `/ready` must show `providers.document_ai/hs_ai/copilot` = `http-llm`,
`configured:true`, `healthy:true`. Then the acceptance per `docs/G18_AI_PROVIDER_REQUIREMENTS.md` §5: the owner's
20-document sample, precision on critical fields vs reviewer truth, cost from `/metrics`
(`vip_ai_cost_usd_today`, `vip_ai_tokens_today`), negative drills (revoke key → `/ready` provider unhealthy within
30 s; provider 5xx → `AI_PROVIDER_FAILED` CRITICAL, no values). Record in `docs/G19_AI_ACCEPTANCE.md`.
Mode stays **limited**: real provider + demo data is allowed and visibly labelled.

## 4. B-02 — first authoritative package (when the owner names the source, licence, steward, verifier)
1. Steward converts the licensed file into the package format (`docs/G18_CUSTOMS_DATA_SCHEMA.md`) — one package per
   kind, with `source_authority`, `source_document`, `source_reference`, effective dates, version.
2. In the Knowledge Hub as ADMIN: **Import gói dữ liệu (JSON)** → dataset appears `inactive · chưa xác minh`;
   `chi tiết` must show "Đủ nguồn pháp lý" (no provenance problems).
3. Verifier (ADMIN or SENIOR_REVIEWER) spot-checks against the legal text, then **xác minh** → badge `authoritative`.
4. **Shadow compare on staging**: activate (`bật`), re-run the pipeline on the reference cases, compare assessments
   with the demo results; attach the diff to the change ticket (`docs/G18_DATA_UPDATE_PROCESS.md` §2.5).
5. Supersede the demo dataset of that kind (`thay thế`) or deactivate it. `/ready` →
   `customs_data_authoritative.<KIND>.authoritative:true`. Repeat per kind. The demo banner disappears only when
   no demo dataset is active.
Guard rails already in place: demo data can never be verified (DB CHECK); two authoritative datasets of one kind
effective on the same date block affected cases with `*_KNOWLEDGE_CONFLICT`; unverified data is never used in
full mode.

## 5. Monitoring and backups on staging (owner inputs: notification destination, off-site destination)
- `METRICS_ALLOW_FROM=<monitoring host CIDR>` in `.env`, `docker compose up -d proxy`; scrape
  `https://hq.vipgroup.com.vn/metrics` from that host; alert rules per `docs/G18_MONITORING_ALERTS.md` §2.
- Off-site backup: `OFFSITE_METHOD`, `OFFSITE_TARGET`, `OFFSITE_ENCRYPT_RECIPIENT` (age public key), retention; rclone
  credential in `~deploy/.config/rclone/rclone.conf` (0600). Install both systemd timers (root, once):
  `vip-customs-backup.timer`, `vip-customs-backup-offsite.timer`. First run by hand:
  `bash scripts/production/backup.sh && bash scripts/production/backup_offsite.sh` → `backup-status.json` written;
  `/ready` `backup_status.state:"fresh"` once `BACKUP_STATUS_FILE` is mounted (production overlay does this).
- Restore drill: `docs/G18_OFFHOST_BACKUP.md` §4.

## 6. What must NOT be done in this session
No `APP_MODE=full` anywhere (it refuses to start until B-01 + B-02 + backup are real, by design). No production host,
DNS or certificate changes (B-06 is an owner decision — `docs/G18_PRODUCTION_INFRA_OPTIONS.md`). No VNACCS/ECUS
credentials. No real customs filing from any output.

## 7. Exit criteria for G18B
Staging on the current develop SHA, acceptance green, B-07 RESOLVED, real provider healthy in limited mode with the
acceptance record, at least one authoritative dataset verified and shadow-compared, metrics scraped and backups
replicated off-host with a successful restore drill. Then G19 (production provisioning in limited mode) can be
proposed to the owner.
