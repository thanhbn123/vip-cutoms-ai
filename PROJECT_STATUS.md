# PROJECT STATUS

Repo `thanhbn123/vip-cutoms-ai` · baseline main `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (unchanged) · `develop` `c7fdafdbba139991cd537d5093b4af46d3a61052` · release candidate `release/g16-rc1`.

Canonical UX: `prototype/index.html` (V12 FINAL). Plan: `docs/MASTER_PLAN.md`, decisions: `docs/DECISIONS.md`, gates: `docs/GATES.md`.

## Gate log

| Gate | Status | Evidence |
|---|---|---|
| G00 Repo assessment | PASS | docs/MASTER_PLAN.md, DECISIONS.md, GATES.md, STATUS.md |
| G01 Foundation | PASS | API boots, /health + /ready, Alembic head 0001, web shell (V12 sidebar), compose, CI file, `scripts/verify.sh` green |
| G02 Auth + Case domain | PASS | token auth, RBAC matrix (4 roles), tenant-scoped queries, case CRUD + numbering, append-only hash-chained audit (migration 0002) |
| G03 Document domain | PASS | storage adapter (local, private, path-safe), upload w/ type+ext+size validation, sha256, versioning/supersede, duplicate guard, tenant-scoped download, audit (migration 0003) |
| G04 Parser / mapping | PASS | provider abstraction + deterministic mock, validated extraction w/ lineage (extracted_fields), source-priority field mapping, package-count conflict, FOB valuation warnings, approved values never overwritten, manual/approve endpoints (migration 0004) |
| G05 Goods + HS engine | PASS (+ session 2: REQUEST_INFO decision, V12 confidences 0.87/0.95/0.64, migration 0009) | goods items from invoice/PL/CO lines w/ lineage + attributes (description heuristics, catalogue match), versioned demo HS_RULES dataset (fail-closed if none active), deterministic candidates w/ confidence+reasoning+missing attrs, <0.70 → CRITICAL/BLOCKED, reviewer APPROVE/REJECT w/ 8-digit code, override = Senior+evidence, audit (migration 0005) |
| G06 Valuation + Tax + C/O + Policy scaffold | PASS | versioned effective-dated demo TARIFF/FTA/POLICY datasets (labelled NON-AUTHORITATIVE, admin can deactivate → evaluators fail closed), deterministic customs-value arithmetic, per-item tax only after approved HS, C/O assessment states + reviewer APPLY (fail-closed on ineligible), policy UNDETERMINED (critical) → requirements after HS approval, assessments API, issue ownership by evaluator (migration 0006) |
| G07 Smart Declaration | PASS | read-model with 5 sections, every field = value+confidence+source+reasoning+review status, 3 items w/ HS/CO/tax/policy, deterministic validation list, readiness % (`GET /cases/{id}/declaration`) |
| G08 Reviewer / Audit / Release | PASS | issue resolve/waive (critical waive = Senior + evidence), approve-all critical fields (skips conflicted), release gate (all CRITICAL checks), mark-ready → READY_TO_EXPORT, immutable versioned drafts: PREVIEW anytime (watermark) / RELEASE only from READY_TO_EXPORT → DRAFT_EXPORTED, JSON+CSV internal adapters (no VNACCS), reviewer queue, dashboard summary, hash-chain verified (migration 0007) |
| G09 AI Copilot | PASS (+ session 2: confidence / recommended_actions / requires_review, five mandated questions, migration 0010) | case-scoped context (tenant-authorised only), deterministic mock intents (MISSING / HS_WHY / CO / VALUATION / DESCRIBE / GENERAL) with sources + reasoning, provider output validated (fabricated source ids dropped), DESCRIBE → Proposal (PROPOSED) applied only by a reviewer other than the requester, messages persisted + audited |
| G10 Historical learning | PASS | product_memory written only from APPROVE decisions (evidence hash, fingerprint, reviewer), rejected decisions never stored, EXACT/MODEL history refs + +0.05 boost for reusable memory, CONSULTATION/DISPUTE outcome (Senior) → reference-only "do not auto-copy", item history/price-delta API, Copilot price-anomaly answer (migration 0008) |
| G12 Full integration | PASS (+ session 2: step 16 history on similar case, Playwright browser E2E on the real stack) | `tests/test_acceptance_mvp.py` executes the owner's 13-step acceptance end-to-end via the API; live smoke run of uvicorn + seed (health/ready/login/pipeline/copilot/drafts); regression test for script-path evaluation |
| G13 Local acceptance / staging readiness | PASS (local) | clean-checkout + migrate-from-zero + full suite + browser E2E PASS, evidence in `artifacts/test-results/`; Makefile; `docs/LOCAL_ACCEPTANCE_REPORT.md`, `docs/LOCAL_DEVELOPMENT.md`, `docs/TEST_STRATEGY.md`, `docs/NEXT_SESSION_STAGING.md`; Docker smoke NOT_RUN (no daemon) |
| G14 Docker / staging preflight | PASS | real `docker compose` boot from zero (build, 3 containers, migrate to 0010, health/ready 200, 0 restarts, no secret leak), in-container seed, Playwright vs Docker web, HTTP acceptance A–P 17/17; demo-data labelling (banner, notice API, legal notice) + `test_demo_labels.py`; staging package `infra/staging/` + 4 docs; security preflight; evidence `docs/G14_DOCKER_STAGING_PREFLIGHT.md` |
| G15 Staging deployment / acceptance | BLOCKED_OWNER | no staging host/SSH user/domain supplied (placeholders) and no ssh in the build session → nothing deployed; deploy record pinned to `474f7d8`; host-side `deploy.sh` + client-side `acceptance.sh` (A–P, negative, restart/persistence, backup/restore, logs, perf) written and dry-run against the local Docker stack; staging compose validated |
| G15C Real staging deployment / acceptance | **PASS** | deployed from the owner's MacBook over SSH to the real VPS `160.22.170.20` (`CIITNRVPlinux`, Ubuntu 26.04) at `https://hq.vipgroup.com.vn`; final deploy SHA `9649ec79db189857628ced0b11eaeaf6635fb42c` = `origin/develop`, host tree clean; 4 containers healthy with 0 restarts, only loopback ports published; migration `0010_copilot_meta` single head; valid Let's Encrypt TLS via the host's **shared** Caddy (`TLS_MODE=off` behind it — the stack cannot own 80/443); health/ready/frontend 200; **17/17** HTTP flow A–P + **18/18** negative/security + **2/2** remote Playwright; restart and `down`/`up` persistence verified (cases and uploads intact); `pg_dump -Fc` backup with recorded SHA256 + restore into a temporary DB (all representative counts equal, live DB untouched); logs 0 5xx / 0 secret hits; demo labels verified in a real browser; 4 defects found and fixed through Git (2 HIGH), 0 open; rollback ready; production **not** deployed and `main` **not** merged. Evidence: `docs/G15_STAGING_ACCEPTANCE_REPORT.md`, `docs/G15_DEPLOY_RECORD.md`, `artifacts/test-results/staging-acceptance.txt` |
| G16 RC closeout | PASS (LIMITED MODE) | PR #1 reviewed (G16 scope only, no runtime change), `infra` CI job added (71 root tests), full verification on exact PR head + CI 4/4, merged `--no-ff` into develop (`d21fd77`), clean checkout from zero, RC frozen (`docs/G16_RC_FREEZE.md`), PR #2 develop→main updated for owner review. B-01/B-02/B-06/B-07 open; production NOT deployed |
| G17 main release freeze | PASS (LIMITED MODE) | Owner approved PR #2 `develop → main`; re-verified head `54a00e7` (CI 8/8 green, clean, evidence unchanged); merged with merge commit `4a2acb9`; `develop` intact, identical tree; `docs/G17_MAIN_RELEASE_FREEZE.md`. Production deployment NOT AUTHORIZED; B-01/B-02/B-06/B-07 open. Next: G18 |
| G18A full-production preparation | PASS (preparation; B-01/B-02/B-06 remain BLOCKED_OWNER, B-07 BLOCKED pending operator) | `APP_MODE=demo|limited|full` (`app/core/modes.py`) with FULL refusing startup on mock/missing credentials/budget/backup path and `/ready` 503 on unhealthy providers, non-authoritative data, migration drift or stale backup; `/metrics`; four AI capability protocols + per-capability env selection + `http-llm` vendor-neutral adapter (timeouts, retries, schema validation, correlation id, cost ledger/budget, redaction, health) with fail-closed `AI_PROVIDER_FAILED`/503 paths; migration `0011_dataset_provenance` + `customs_data` service (import/verify/supersede, authoritative-only selection in full mode, conflicts → reviewer) + API; B-07 `deactivate_demo_users.py` + staging wrapper; `backup_offsite.sh` + units; web mode banner; **122** api pytest · **102** infra pytest · 3 vitest · Playwright 2/2 native + 2/2 Docker · Docker smoke (head `0011`, 0 restarts, 0 leaks) · A–P 17/17 · `VERIFY: ALL CHECKS PASSED`; 14 G18 docs incl. `G18_OWNER_INPUTS.md`. Production NOT deployed, `main` unchanged |
| G18B hardening follow-ups | PASS | closed G16 LOW findings (malformed signed token → 401 not 500; `nosniff`/`DENY`/`no-referrer`/`no-store` at the API layer; RFC 6266/5987 Content-Disposition) and G18A limitations (longest-prefix HS lookups so 8-digit authoritative lines win over heading defaults; `knowledge.verify` permission for SENIOR_REVIEWER + ADMIN; persistent AI usage ledger migration `0012_ai_usage_events` with restart-safe daily budget; Caddy `/metrics` restricted to private ranges + `health_uri` on the api upstream). 12 new api tests (134), 1 new infra test (103); migration 0012 up/down/up verified. Owner blockers unchanged |
| G18C code-review remediation | PASS | high-effort review of `main...develop` → 20 findings, 19 fixed + 1 documented limitation (`docs/G18C_REVIEW_REMEDIATION.md`): fail-closed gaps closed (system criticals waive-only + reopen on recurrence, unreadable docs CRITICAL, stale fields cleared, package validation, orphan invoice lines CRITICAL), lineage kept on as-is approval, post-export decisions reopen the case, reviewer-approved preferential rate honoured, HS candidate/heading consistency, REJECT clears code, CSV formula injection, `/metrics` default-closed, `/docs` hidden, token edge → 401, N+1 queries, web client robustness, test-cleanup lock timeout. 18 new api tests (152 + 1 skip), 5 vitest; acceptance flows updated to waive criticals as Senior |
| G18D login throttling + Knowledge Hub steward UI | PASS | in-process sliding-window limiter on `/auth/login` (per client IP and per e-mail, 429 + `Retry-After` before any hash work, success clears the e-mail key, `vip_login_throttled_total`), settings `LOGIN_MAX_ATTEMPTS/WINDOW/LOCKOUT` in templates/compose; Knowledge Hub shows provenance/checksum/verification/lineage with `xác minh` (`knowledge.verify`), `thay thế`, JSON import (ADMIN) and translated provenance problems. admin page renders `/ready` structurally (mode, providers, authoritative data, backup, blockers). 5 api tests (166 + 1 skip), 3 vitest (8), infra 106 |
| G18E throttle/UI hardening + clean checkout | PASS | review of G18D → 11 items closed: limiter split into pair/e-mail/ip dimensions (`LOGIN_MAX_ATTEMPTS`/`LOGIN_EMAIL_MAX_ATTEMPTS`/`LOGIN_IP_MAX_ATTEMPTS`, 0 disables), bounded key store with eviction (`LOGIN_MAX_TRACKED_KEYS`), lock-time 429 counted + `vip_login_locks_total` + tracked-keys gauge, `auth.login_locked` audit, residual account-lockout risk documented; Knowledge badge fails closed, import panel stays open on failure, prompt validation, DOM nesting; admin panel distinguishes reason/error from kinds. Clean checkout of develop `f2989b1` from zero: all suites + build + Playwright green. 11 api tests (170 + 1 skip), vitest 9, infra 108 |
| G11 Frontend V12 parity | PASS | React+TS SPA reusing V12 CSS/sidebar: login, Tổng quan (readiness/mapped/history/release metrics, flow, critical issues, AI summary), Hồ sơ & chứng từ (create case, master data, Document Center upload+parse, lineage), Smart Declaration (5 sections, per-field confidence/source/status, edit/approve/approve-all, validation), Hàng hóa & HS (candidates, reasoning, attributes, HS decision, C/O decision, tax/policy), Knowledge Hub (versioned demo datasets, toggle), AI Copilot (chat, sources, proposals queue), Reviewer & Release (queue, issues resolve/waive, gate, DRAFT/READY/release, downloads), Lịch sử & Learning, Quản trị (metrics, production path, users, audit) · vitest 3 tests · seed script `scripts/seed_demo.py` |
| G16 Production review / RC freeze | **PASS_LIMITED_MODE** | reviewed `develop` `c7fdafd`; proved the only drift from the accepted staging SHA `9649ec7` is documentation (every code subtree hash identical, so staging runs the reviewed code and was **not** redeployed); fresh clean-checkout regression on an isolated DB with Node 22: **72** api pytest + **64** infra pytest (21 → 64) + **3** vitest + **2** Playwright + A–P **17/17** + negative/security **18/18**, ruff clean, single head `0010_copilot_meta` from zero, secret scan clean, `vite build` reproducing the exact asset hashes staging serves; 5 fail-closed probes verified (missing/short `APP_SECRET_KEY`, unimplemented AI provider → `/ready` 503, unimplemented storage, `seed_demo` refused in production); read-only live staging + VPS evidence; security/auth/RBAC/tenant-isolation/upload/secret review — 0 high, 3 low hardening items; production templates + runbooks prepared (`infra/production/`, `scripts/production/backup.sh`, systemd units verified by `systemd-analyze`, overlay validated by real `docker compose config`); B-01/B-02/B-06/B-07 reviewed, all still **OPEN**; CI observed green (run `37900514439`, 3/3 jobs) retiring `CI_EXTERNAL_UNVERIFIED`; supervisor review then found `backup.sh` wrote dumps world-readable under a normal umask — hardened (`umask 077`, explicit `chmod 600`/`700`, `BACKUP_DIR` symlink+ownership validation, `UMask=0077`) and covered by 13 execution tests with a mocked `docker`, plus honest documentation that the sequential dump/archive pair is **not** an atomic snapshot. `READY_TO_MERGE_MAIN = NO` (the G16 additions are not in `develop` yet, the owner's limited-mode review is open) · `READY_TO_DEPLOY_PRODUCTION = NO`. Evidence: `docs/G16_PRODUCTION_REVIEW.md`, `docs/PRODUCTION_READINESS.md`, `docs/PRODUCTION_RUNBOOK.md` |

## Current checkpoint (G16 · production review / RC freeze · 2026-10-09)

- **G16 verdict: PASS_LIMITED_MODE** — approved for internal demo/drafting use only. `PASS_FULL_MODE`
  is **not** achieved: it needs B-01 (real OCR/LLM provider) and B-02 (authoritative tariff/FTA/policy
  data) resolved, plus automated/off-host backup, monitoring and login rate limiting. Until then the
  system must not be used to prepare a real customs filing — its tariff/FTA/policy data is demo fixture data.
- `READY_TO_MERGE_MAIN = **NO**`. Three things must be true first and none is yet: the G16 additions
  are not in `develop` (they are on `release/g16-rc1` under review in draft PR #1 → `develop`, per
  D-003), the owner's limited-mode review is open, and `develop` has not been re-verified and frozen.
  A GitHub `MERGEABLE` flag means only "no textual conflict" and is not a readiness signal.
  `READY_TO_DEPLOY_PRODUCTION = NO`. Nothing was deployed by this gate; `main` was not merged,
  modified or pushed.
- CI is **observable and green**, which retires the long-standing `CI_EXTERNAL_UNVERIFIED` (D-004):
  run `37900514439` on `release/g16-rc1` @ `6768a17`, jobs `api`/`web`/`secrets` all success.
  Caveat: `ci.yml`'s `api` job runs only `apps/api/tests`, so the root `tests/` infra suite (64 tests,
  including every backup permission test) is **not** run by CI — recommended to add, left out of scope.
- Branches: `main` `2afdf6b` **unchanged** · `develop` `c7fdafd` · RC `release/g16-rc1`
  (draft PR #1 → `develop`, **not merged**).
- Which SHA each check covered: full suite + A–P + negative + fail-closed probes at the baseline
  `c7fdafd`; local `scripts/verify.sh` at `08ff835`; CI at the final SHA. The gate's later commits are
  evidence and the supervisor corrections, not code under review.
- Staging (verified read-only this gate) is live at `https://hq.vipgroup.com.vn` on `9649ec7`, host tree
  clean, 4 containers 0 restarts, `/health` and `/ready` 200 (`database ok`, `0010_copilot_meta`, provider
  `mock`, env `staging`), valid Let's Encrypt to 2027-01-07, security headers present, 401 on unauthenticated
  API calls. `9649ec7` and `c7fdafd` differ only in documentation, so staging needed no redeployment.
- Tests re-measured in a clean checkout (not copied from G15C): **72** api pytest · **64** infra pytest ·
  **3** vitest · **2** Playwright · A–P **17/17** · negative/security **18/18** · 0 server errors.
  A–P and the negative suite were run against a **local** stack on an isolated database, because both
  mutate data and `scripts/staging/acceptance.sh` additionally restarts the stack.
- Added this gate: `infra/production/` (env template, compose overlay, systemd backup units),
  `scripts/production/backup.sh` (database **and** uploads, checksums, manifest, retention),
  `docs/PRODUCTION_READINESS.md`, `docs/PRODUCTION_RUNBOOK.md`, `docs/G16_PRODUCTION_REVIEW.md`,
  43 new infra tests, 13 of which execute `backup.sh` against a mocked `docker` (one contract test caught `.env.production.example` being silently excluded by `.gitignore` — found only because the final verify ran in a clean checkout). A supervisor review then found `backup.sh` created dumps under the caller's umask (0644, world-readable under a normal 022); hardened to `umask 077` + explicit `chmod 600`/`700`, symlink and ownership validation on `BACKUP_DIR`, `UMask=0077` on the unit, and the sequential dump/archive pair documented as **not** an atomic snapshot with quiesced-backup and post-restore reconciliation guidance. Fixed a stale migration head reference in `docs/RUNBOOK.md`.
- Security review: 0 high/critical. 3 low hardening items (unescaped quote in `Content-Disposition`
  filename; download echoes client-supplied `content_type` without its own `nosniff`; `current_user`
  parses `sub` outside its `try`, so a malformed signed payload would 500 rather than 401) — none
  attacker-reachable as shipped. Plus 2 known gaps: no login rate limiting, and knowledge datasets are
  global rather than tenant-scoped (deliberate, fails closed).
- Still mocked / demo: OCR-LLM provider (`mock`), HS rules, tariff, FTA, policy (all `is_demo`,
  NON-AUTHORITATIVE), local file storage. No customs-system adapter exists, by design (product rule #7).

## Previous checkpoint (end of session 2 · 2026-10-08)

- Branches: `main` `2afdf6b` unchanged · `develop` = release candidate (feature/g00…g13 merged `--no-ff`, pushed) · `claude/busy-davinci-9u8bye` mirrors develop
- Tests: **68 pytest** (PostgreSQL 16, schema from zero) + **3 vitest** + **1 Playwright E2E** + HTTP acceptance 17/17 vs Docker; `make verify` and `scripts/collect_evidence.sh` green; CI: `CI_EXTERNAL_UNVERIFIED`
- Migration head: `0010_copilot_meta` (0001 → 0010, single head, downgrade verified)
- Works end-to-end locally (API + web): the owner's 16-step flow, V12 functional parity, reviewer workflow, release gate, versioned drafts, audit chain, approved-only learning.
- Mocked / demo: OCR-LLM provider (`mock`), HS rules, tariff, FTA, policy (all `is_demo`, NON-AUTHORITATIVE), local file storage.
- Docker Compose: executed in G14 (PASS). Staging compose (`infra/staging/`) prepared, not deployed. Not done: real providers, authoritative data, OIDC, S3, rate limiting/CSP, staging deploy, any customs-system connection.

## Next
**Review draft PR #1 (`release/g16-rc1` → `develop`).** No merge is authorised in this gate.

Then, in order: owner decides the limited-mode question → merge PR #1 into `develop` → re-verify
and freeze `develop` at that merge commit (local `scripts/verify.sh` plus a green CI run on
`develop` at the frozen SHA) → only then prepare `develop` → `main`. `READY_TO_MERGE_MAIN` stays
**NO** until those are done.

CI is **observable and green** (this corrects the long-standing `CI_EXTERNAL_UNVERIFIED`):
GitHub Actions run `37900514439` on `release/g16-rc1`, head SHA `6768a17`, jobs `api`/`web`/
`secrets` all success. Note that `ci.yml`'s `api` job runs only `apps/api/tests`, so the root
`tests/` infra suite (64 tests, including every backup permission test) is **not** run by CI;
`scripts/verify.sh` runs it locally. Adding it to `ci.yml` is recommended and was left out of
scope.

Production deployment and any customs-system integration remain separate, explicitly-gated
decisions (product rule #7).

Open owner decisions, all **unresolved**: B-01 real OCR/LLM credentials · B-02 authoritative
tariff/FTA/policy source · B-06 whether `hq.vipgroup.com.vn` keeps depending on the host's shared
Caddy · B-07 remove the staging demo users. Options and a recommendation for each:
`docs/PRODUCTION_READINESS.md` §4.
