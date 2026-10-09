# G15C — REAL STAGING DEPLOYMENT / ACCEPTANCE REPORT · 2026-10-09

## Verdict: **PASS — deployed to the real staging VPS and accepted. `READY_FOR_PRODUCTION_REVIEW = YES`.**

Production was **not** deployed and `main` was **not** touched.

> **This report supersedes the G15/G15B entry below.** G15 and G15B produced a `BLOCKED_OWNER`
> verdict and a **LOCAL DRY-RUN** only (the staging host was never supplied, and the build
> session had no `ssh`). Everything in the *Real staging* sections was executed against the
> actual VPS from the owner's MacBook. The two are kept clearly separated on purpose.

| | |
|---|---|
| Scope | **REAL STAGING** (not a dry-run, not localhost) |
| Operator | owner's MacBook (local Claude Code session), SSH to the VPS |
| Date | 2026-10-09 (UTC) |

---

## 1. Git identity

| | |
|---|---|
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` — **unchanged, not merged** |
| DEVELOP SHA at session start | `bfc82cb45cf40453a14208a43fef4660fcc1f067` (verified = `origin/develop`) |
| **INITIAL DEPLOY SHA** | `bfc82cb45cf40453a14208a43fef4660fcc1f067` — the exact verified candidate |
| Intermediate deploy SHA | `fed904f82f0de1fbe3e9b071639b0f7b9f94bd7a` (after the TLS/env/audit fix) |
| **FINAL DEPLOY SHA** | `9649ec79db189857628ced0b11eaeaf6635fb42c` |
| **FINAL DEVELOP SHA** | `9649ec79db189857628ced0b11eaeaf6635fb42c` — deployed SHA **equals** `origin/develop` |
| Working tree on host | clean (`git status --porcelain` → 0 lines) at the final SHA |

Both redeployments were forced by defects that only real staging exposed; each was fixed in
Git, merged to `develop`, and the new SHA deployed. No application source was ever edited on
the VPS.

## 2. Host identity (verified before any write)

| | |
|---|---|
| STAGING HOST | `160.22.170.20` |
| Hostname | `CIITNRVPlinux` |
| SSH | `root`, key `~/.ssh/vip_ai_staging_admin` (ed25519), host key pinned in `~/.ssh/vip_ai_staging_known_hosts` and identical across all three local `known_hosts` files |
| OS | Ubuntu 26.04 LTS (Resolute Raccoon), kernel 7.0.0-34-generic x86_64 |
| CPU / RAM / DISK | 4 vCPU · 7.2 GiB RAM (5.7 GiB available) · 89 GB disk, 14 % used |
| Docker | server 29.1.3 · Compose 2.40.3 |
| DEPLOY PATH | `/opt/vip-customs-ai` (fresh `git clone`; did not exist before) |
| STAGING DOMAIN | `hq.vipgroup.com.vn` |

**DNS:** `dig +short hq.vipgroup.com.vn` → `160.22.170.20` (A, TTL 300) — **PASS**.

## 3. Shared-host integration (the significant deviation from the brief)

This VPS is **shared** with four unrelated, live VIP projects (`viporder`, `vipphone-staging`,
`vip-staging`/shipping-gateway, `member`). Ports **80 and 443 were already owned** by a
shared Caddy reverse proxy — the `vip-staging-caddy` container (`caddy:2`, host networking,
Caddyfile bind-mounted from `/srv/vip-staging-proxy/Caddyfile`).

The brief's §7 asked for `TLS_MODE=acme`, which requires this stack to own ports 80/443 for
the ACME HTTP-01 challenge. That was impossible without taking the shared proxy down, which
§5 forbids. Per §5 ("integrate `hq.vipgroup.com.vn` into that proxy safely") the stack was
instead placed **behind** the shared proxy:

- the stack's own Caddy publishes **loopback-only** ports `127.0.0.1:18100` (HTTP) and
  `127.0.0.1:18543` (HTTPS), both previously free — nothing is exposed to the internet directly;
- `TLS_MODE=off` (the documented "upstream TLS terminator" mode);
- the shared Caddy owns the public name and terminates TLS with its own automatic Let's Encrypt.

Edge TLS is therefore a **real, publicly valid certificate**, which is what §13 requires.

The shared Caddyfile was changed using the convention documented inside that file itself:
backup → append → `caddy validate` → `caddy reload` (zero downtime, additive, no existing
site block modified).

| | |
|---|---|
| Backup | `/srv/vip-staging-proxy/Caddyfile.bak-before-vip-customs-ai-2026-10-09-105445` |
| Validation | passed before reload (a failure would have restored the backup without reloading) |
| Reload | `caddy reload` — shared proxy stayed `running`, `RestartCount=0` |
| Neighbours after reload | `qua.viporder.vn` 200 · `member.quangkhoiwellnessretreat.com` 200 · `web.viporder.vn` 200 · `cpn.viporder.vn` 404 (that app's own response; its block was not touched) |
| Other containers | all 11 unrelated containers still up, uptimes unbroken — **no collateral damage** |

## 4. Containers, images, ports, volumes

Compose project `vip-customs-ai-staging`, file `infra/staging/docker-compose.staging.yml`.

| Container | ID | Image | Image ID | Status | Ports | Restarts |
|---|---|---|---|---|---|---|
| `…-api-1` | `f870c067a0d2` | `vip-customs-api:9649ec79db18` | `sha256:69e7916236f3…` | Up (healthy) | `8000/tcp` (internal) | 0 |
| `…-web-1` | `68ad03f06253` | `vip-customs-web:9649ec79db18` | `sha256:bf31eb36f0eb…` | Up | `80/tcp` (internal) | 0 |
| `…-postgres-1` | `e9b735928e4e` | `postgres:16-alpine` | — | Up (healthy) | `5432/tcp` (internal) | 0 |
| `…-proxy-1` | `6437ce29b465` | `caddy:2-alpine` | — | Up | `127.0.0.1:18100->80`, `127.0.0.1:18543->443` | 0 |

Only the proxy publishes host ports, and only on loopback. **No crash loops** (all
`RestartCount=0`). Volumes (persistence): `…_pgdata`, `…_uploads`, `…_caddy_data`,
`…_caddy_config`.

## 5. Migration

`alembic current` → **`0010_copilot_meta (head)`**, `alembic heads` → **single head**. Matches
the expected value in §11.

## 6. Health / ready / frontend / TLS

| Check | Result |
|---|---|
| `GET https://hq.vipgroup.com.vn/health` | **200** `{"status":"ok","service":"vip-customs-api","version":"0.1.0"}` |
| `GET …/ready` | **200** `{"status":"ready","checks":{"database":"ok","migrations":"0010_copilot_meta","ai_provider":"mock","environment":"staging"}}` |
| `GET …/` (frontend) | **200** |
| `GET …/api/v1/cases` unauthenticated | **401** (correct) |
| TLS verification | `ssl_verify_result=0` — **certificate VALID** |
| Certificate | `CN=hq.vipgroup.com.vn`, issuer `C=US, O=Let's Encrypt, CN=YE1`, valid `2026-10-09 02:56:38Z` → `2027-01-07 02:56:37Z` |
| HTTP → HTTPS | **308** → `https://hq.vipgroup.com.vn/health` |

Ready confirms **database ok**, **migration head correct**, **AI provider = mock**.

## 7. Seeded demo data (§14)

`scripts/seed_demo.py --with-case`, demo tenant only, no real customer data.

| Required fixture | Present |
|---|---|
| Minh Phát | `CÔNG TY TNHH MINH PHÁT` (code `MINHPHAT`) |
| Guangzhou ABC | `GUANGZHOU ABC TRADING CO., LTD.` (CN) |
| INV-2026-889 | `invoice.number = INV-2026-889` (+ date `2026-10-05`, total `17900.00`) |
| Items ABC-500 / PVC-20 / CT-88 | 3 goods items; item 3 `model=CT-88` |
| Case | `VIP-HQ-261008-001`, status **BLOCKED**, 4 fixture documents parsed |

**Fail-closed verified on real staging:** item 3 (`CT-88`) is `hs_status=BLOCKED` with
`hs_confidence=0.64` and **`hs_code: null`** — no fabricated value, which is product rule #1.
Items 1/2 are `0.87` / `0.95` `NEEDS_REVIEW`.

## 8. Staging acceptance (§15) — run from the Mac against `https://hq.vipgroup.com.vn`

`BASE_URL=https://hq.vipgroup.com.vn … bash scripts/staging/acceptance.sh`, with `COMPOSE`
and `DOCKER` tunnelled over SSH. Evidence: `artifacts/test-results/staging-acceptance.txt`
(final run 2026-10-09 06:35 UTC against `9649ec7`). **No localhost results were substituted.**

| Section | Result |
|---|---|
| 1 external health + TLS + redirect | PASS |
| 2 demo seed (host side) | PASS |
| 3 Playwright (browser, remote base URL) | **2/2 passed** |
| 4 acceptance flow A–P over HTTP | **17/17 PASS** (`acceptance_exit=0`) |
| 5 negative / security tests | **18/18 PASS** (`negative_exit=0`) |
| 6 demo labels | PASS |
| 7 performance smoke | PASS (see §12) |
| 8 restart / persistence | PASS |
| 9 backup + restore into a temporary DB | PASS |
| 10 log / secret review | PASS |

**35 automated assertions in total (17 acceptance + 18 negative), all passing**, plus the two
browser tests. The brief's "20/20" has no counterpart in the tooling — the suite reports
17/17 and 18/18 — so the real counts are given rather than a number the tooling never emits.

Flow A–P covers: auth; case creation; 4-document upload; mock parse; the 124/126 package
conflict detected and *not* auto-resolved; 3 goods items; HS confidences with item 3 blocked;
valuation `17900 + 420 + 100 = 18420`; versioned `is_demo` C/O + policy rules; Copilot with
sources/confidence/`requires_review`; reviewer resolution with actor/before/after/reason
audit; release gate passing only after every check; `READY_TO_EXPORT`; versioned JSON+CSV
draft with watermark and legal notice; approved-only historical memory; and a similar next
case finding history (EXACT, +0.05, still `NEEDS_REVIEW`).

## 9. Remote Playwright (§16)

`E2E_BASE_URL=https://hq.vipgroup.com.vn npx playwright test` — **remote base URL, 2/2 passed**.

| Required proof | Covered by |
|---|---|
| login | `smoke.spec.ts` — real login form, seeded reviewer |
| dashboard | landing "Tổng quan" with the case status badge |
| V12 navigation | all **9** sidebar entries asserted visible, in order |
| Item 3 BLOCKED / 64 % | `CT-88` row: `8537.xx.xx`, `64–69 %`, badge `BLOCKED` |
| Copilot | "Còn thiếu gì để khai?" → answer contains `Item 3` + `requires review` |
| release blocked | Release Gate badge `BLOCKED`, "Phát hành bản nháp" **disabled** |
| reviewer path | automated over HTTP (flow steps K–M: approvals, resolution, `READY_TO_EXPORT`) |
| demo labels | `demo-labels.spec.ts` (**new this gate**) |

The `64–69 %` tolerance is the product's own approved-memory boost (+0.05) on a re-used
database; the seeded reference case itself still reads `0.64`.

## 10. Negative / security tests (§17) — actual status codes

| Check | Status |
|---|---|
| no token / tampered token / wrong password | **401** ×3 |
| operator cannot approve HS critical | **403** |
| operator cannot resolve issues | **403** |
| operator cannot mark READY | **403** |
| operator cannot export release draft | **403** |
| admin has no customs-decision permission | PASS |
| path-traversal filename | sanitised to basename, no error |
| `.exe` upload | **422** |
| unknown `doc_type` | **422** |
| oversized upload (21 MB vs 20 MB limit) | **413** |
| open issues block READY (reviewer) | **409** |
| release draft blocked while blocked | **409** |
| cross-tenant / unknown case id | **404** (no enumeration leak) |
| cross-tenant / unknown document | **404** |
| audit records critical actions (actor/before/after) | PASS |
| audit chain valid | PASS |

RBAC = PASS · TENANT ISOLATION = PASS · UPLOAD SECURITY = PASS · critical issue prevents
release = PASS · rejected suggestion not learned = PASS (flow step O) · audit written = PASS.

## 11. Restart, persistence, backup, restore

**Restart (§18)** — `compose restart`: `/ready` **200**, cases `8 → 8`, all `RestartCount=0`,
domain still served.

**Down/up persistence (§19)** — `compose down` (**never `-v`**) then `up -d`: `/ready` **200**,
cases **8 (unchanged)**, uploads **25 files present**, audit and approved memory intact.

**Backup (§20)** — `pg_dump -Fc` into `/opt/backups/vip-customs-ai/` (mode `700`, file `600`):

| | |
|---|---|
| File | `staging-2026-10-09T061749Z.dump` |
| Timestamp (UTC) | `2026-10-09T06:17:49Z` |
| Size | `157877` bytes |
| SHA256 | `c8b2c62100a9104f58223ee3bdcd4058ab23c2abee827bf2ddc1a281597be76c` |
| Format | PostgreSQL custom database dump v1.15-0 |

**Restore test (§21)** — restored into a **temporary** database `g15c_restore_test`; the live
staging database was never written to, and the temporary target was dropped afterwards.

| Table | Live | Restored |
|---|---|---|
| `cases` | 5 | 5 |
| `documents` | 16 | 16 |
| `goods_items` | 15 | 15 |
| `audit_events` | 264 | 264 |
| `product_memory` | 3 | 3 |
| `declaration_drafts` | 1 | 1 |
| `classification_decisions` | 3 | 3 |
| `knowledge_datasets` | 4 | 4 |

Live counts were identical before and after the restore test. (The acceptance suite also ran
its own independent restore: `cases=8 audit=455` at that later point.)

## 12. Logs, secrets, performance

**Log / secret review (§22)** — 500-line tail across all services: `traceback` 0 · `FATAL` 0 ·
HTTP 5xx **0** · crash/restart 0 · migration errors 0. The only 4 `ERROR` lines are
`relation "historical_memory" does not exist` / `column "status" does not exist`, caused by
**this operator's own exploratory SQL** (wrong table/column names), not by the application.

Secret review: the real `POSTGRES_PASSWORD`, `APP_SECRET_KEY` and `SEED_DEMO_PASSWORD` values
were each searched for verbatim in the logs — **none present**. `password` / `secret` /
`token` / `Authorization` keyword hits: **0**. `infra/staging/.env` is mode `600` and
git-ignored; no secret is in Git or in this report.

**Demo safety labels (§23)** — PASS. `/knowledge/notice` →
`DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING`, `demo_active=true`,
`non_demo_datasets: []`. All four datasets `is_demo=true` and versioned
(`demo-hs-2026.10`, `demo-tariff-2026.10`, `demo-fta-2026.10`, `demo-policy-2026.10`).
Draft export carries `meta.legal_notice` =
`DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING`, `meta.watermark` =
`DRAFT — INTERNAL RELEASE DRAFT — NOT A CUSTOMS SUBMISSION`, plus a top-level `demo_notice`.
Verified **in a real browser** on the banner, Knowledge Hub, per-item C/O / tax / policy
assessments, Smart Declaration and Reviewer & Release.

**Performance (§24)** — light, non-destructive, 10 sequential requests per endpoint on an
idle host (load average 0.26), **0 errors in 50 requests**:

| Endpoint | avg |
|---|---|
| `/health` | 41 ms |
| `/ready` | 123 ms |
| `/api/v1/cases` (authenticated, 8 cases) | 181 ms |
| `/api/v1/dashboard/summary` | 56 ms |
| `/api/v1/knowledge/datasets` | 223 ms |

The acceptance run's own section 7 recorded 0.9–14 s for the same endpoints because it
executed while `docker compose build --no-cache` was still saturating all 4 vCPUs. The table
above is the valid measurement; the discrepancy is recorded rather than hidden.

## 13. Defects found on real staging and fixed through Git (§25)

No fix was ever applied only on the VPS. Each was committed, pushed, merged to `develop`, and
the new SHA redeployed.

### D-1 · HIGH · `TLS_MODE` was unusable in two of its three documented modes
`infra/staging/Caddyfile` passed `TLS_MODE` straight into Caddy's `tls` directive. Caddy v2
accepts only `internal`, `force_automate` or an email address there, so both `off` **and
`acme` — the mode the brief prescribes** — aborted config adaptation and the proxy never
started:

```
adapting config using caddyfile: parsing caddyfile tokens for 'tls':
single argument must either be 'internal', 'force_automate', or an email address
```

Only `internal` worked. The proxy service now translates `TLS_MODE` into `SITE_ADDRESS` +
`TLS_ARG` and fails fast on an unknown mode; `off` uses the `http://` scheme so Caddy does not
claim 443 or attempt ACME behind an upstream terminator. **This defect blocked the deployment
architecture this host requires.**

### D-2 · MEDIUM · `deploy.sh` required a file that did not exist
`scripts/staging/deploy.sh` aborts with a message pointing at
`infra/staging/.env.staging.example`, which was absent from the repository. Added, with every
key compose and `deploy.sh` require and empty values for the three generated secrets. `.env.*`
was also ignoring it, so `.gitignore` now un-ignores `*.env.example` templates while real
`.env` files stay ignored.

### D-3 · HIGH · audit chain verification depended on the database session timezone
`app/services/audit.py` hashed `created_at.isoformat()`. `created_at` is a `timestamptz`, which
the driver returns in the **database session's** TimeZone, so one instant hashes as
`…+00:00` in a UTC session and `…+07:00` in `Asia/Ho_Chi_Minh`. `verify_chain` therefore
reported a perfectly valid chain as **tampered** wherever the session was not UTC — a false
integrity alarm on a critical guarantee (product rule #9), invisible on a UTC server and
reproducible on the owner's machine. The digest now normalises to UTC, which is byte-identical
to what a UTC session already wrote, so **existing chains still verify**.

### D-4 · LOW · acceptance suite was not actually client-runnable, and one check was undiagnosable
`restart counts` shelled out to a bare `docker`, which does not exist on a client machine, so
the line silently emitted no data despite the script documenting client-side use; the plain
docker transport is now a `DOCKER` variable mirroring `COMPOSE`. Separately, the 21 MB
oversize-upload check shared the client-wide 30 s timeout while the upload alone takes ~15 s
over a WAN link; it failed **once** during a full-suite run and passed on every isolated
re-run (and 18/18 for the whole suite). It now has its own 300 s timeout, and the three upload
checks report the status actually observed — the original failure left no way to tell 413 from
502 after the fact, because the suite's own `down`/`up` had already discarded the logs.

### Tests added
- `tests/test_staging_infra.py` (new root-level suite, **no database or Docker needed**) —
  executes the shipped `TLS_MODE` mapping with `/bin/sh` and asserts every documented mode
  resolves to valid Caddy v2 syntax, unknown modes fail fast, and the env template is complete
  and secret-free. **20 of its 21 tests fail against the pre-fix tree.**
- `apps/api/tests/test_auth_cases.py` — parametrised chain check over `UTC`,
  `Asia/Ho_Chi_Minh`, `America/Los_Angeles`; the two non-UTC cases fail pre-fix.
- `apps/web/e2e/demo-labels.spec.ts` — browser assertions for the demo-safety labels, which
  were previously only checked on the API payload.
- `scripts/verify.sh` now runs the infra suite.

Full local verification at the final SHA: **72 api + 21 infra + 3 web tests passed**, single
alembic head, secret scan clean, `VERIFY: ALL CHECKS PASSED`.

## 14. Known limitations

- `AI_PROVIDER=mock`; all HS / tariff / FTA / policy knowledge is **DEMO, non-authoritative**
  and labelled as such. Blockers B-01/B-02 stand.
- Edge TLS is terminated by the **shared** Caddy, so `hq.vipgroup.com.vn` availability is
  coupled to a proxy serving unrelated projects. The stack's own `acme` mode is now correct
  but unusable here because it cannot own ports 80/443.
- The seeded reference case carries one extra `OTHER` document (`big.txt`) left by the
  oversize-upload reproduction. The case status was restored to `BLOCKED` by re-running the
  application's own pipeline (not by editing data); item assertions are unaffected.
- Local web unit tests require **Node 22** (CI's version). On Node 26 jsdom 25 fails with
  `localStorage … undefined`; this is a local toolchain mismatch, not a product defect.
- Demo users still exist on staging; `docs/STAGING_SECRETS.md` says to delete them after
  acceptance.
- No production submission path exists, by design (product rule #7).

## 15. Rollback readiness — **YES**

- Previous images retained on the host for all three SHAs (`bfc82cb45cf4`, `fed904f82f0d`,
  `9649ec79db18`, api + web = 6 images) → roll back by re-tagging `IMAGE_TAG` and `up -d`.
- Pre-deploy `pg_dump -Fc` baselines + image manifests in `/opt/vip-customs-ai/backups/`
  (`db-predeploy-2026-10-09-1032.dump`, `…-1323.dump`).
- Independent verified backup in `/opt/backups/vip-customs-ai/` with a recorded SHA256.
- Shared-proxy rollback: `Caddyfile.bak-before-vip-customs-ai-2026-10-09-105445`.
- Procedure: `docs/STAGING_ROLLBACK.md`.

## 16. Success criteria (§28)

| Criterion | Result |
|---|---|
| SSH REAL HOST | PASS |
| HOST IDENTITY | VERIFIED |
| EXACT SHA DEPLOYED | PASS (deployed SHA = `origin/develop`) |
| DNS | PASS |
| TLS | PASS (valid Let's Encrypt) |
| CONTAINERS | HEALTHY (0 restarts) |
| MIGRATION | SINGLE HEAD (`0010_copilot_meta`) |
| HEALTH / READY / FRONTEND | 200 / 200 / 200 |
| STAGING ACCEPTANCE | PASS — 17/17 flow + 18/18 negative |
| REMOTE PLAYWRIGHT | PASS (2/2, remote base URL) |
| NEGATIVE TESTS · RBAC · TENANT ISOLATION · UPLOAD SECURITY | PASS |
| RESTART · PERSISTENCE | PASS |
| BACKUP · RESTORE TEST | PASS |
| LOG REVIEW · SECRET REVIEW | PASS |
| DEMO LABELS | PASS |
| CRITICAL BUGS / HIGH BUGS open | **0 / 0** (2 HIGH found, both fixed and redeployed) |
| ROLLBACK READY | YES |
| **READY_FOR_PRODUCTION_REVIEW** | **YES** |
| PRODUCTION DEPLOYED | **NO** (out of scope) |

---

## Appendix · G15/G15B — LOCAL DRY-RUN only (historical, superseded)

For the record, the earlier gates reached `BLOCKED_OWNER`: the brief carried placeholders
(`<IP_OR_HOSTNAME>`, `<SSH_USER>`, `<STAGING_DOMAIN_OR_NONE>`, `<DEPLOY_PATH>`) and the build
container had no `ssh`/`scp`/`rsync`, so **no remote system was touched and nothing was
deployed**. What they produced — `scripts/staging/deploy.sh`, `scripts/staging/acceptance.sh`,
`scripts/staging/negative_tests.py`, `infra/staging/`, and the staging docs — was exercised
only against the **local** Docker stack, evidence in
`artifacts/test-results/staging-acceptance-dryrun-local.txt`. That dry-run is **not** staging
evidence and does not support any claim in sections 1–16 above.
