# PROJECT STATUS

Repo `thanhbn123/vip-cutoms-ai` · baseline main `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` · working branch `claude/busy-davinci-9u8bye`.

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
| G11 Frontend V12 parity | PASS | React+TS SPA reusing V12 CSS/sidebar: login, Tổng quan (readiness/mapped/history/release metrics, flow, critical issues, AI summary), Hồ sơ & chứng từ (create case, master data, Document Center upload+parse, lineage), Smart Declaration (5 sections, per-field confidence/source/status, edit/approve/approve-all, validation), Hàng hóa & HS (candidates, reasoning, attributes, HS decision, C/O decision, tax/policy), Knowledge Hub (versioned demo datasets, toggle), AI Copilot (chat, sources, proposals queue), Reviewer & Release (queue, issues resolve/waive, gate, DRAFT/READY/release, downloads), Lịch sử & Learning, Quản trị (metrics, production path, users, audit) · vitest 3 tests · seed script `scripts/seed_demo.py` |

## Current checkpoint (G15C · real staging accepted · 2026-10-09)

- Staging is **live and accepted** at `https://hq.vipgroup.com.vn` on deploy SHA `9649ec7` (= `origin/develop`); `READY_FOR_PRODUCTION_REVIEW = YES`. Production not deployed.
- Branches: `main` `2afdf6b` **unchanged** · `develop` `9649ec7` (staging-accepted).
- Tests at the deployed SHA: **72 pytest** + **21 infra pytest** (new, no DB/Docker) + 3 vitest + **2 Playwright** · `VERIFY: ALL CHECKS PASSED` · migration head `0010_copilot_meta` (single).
- Fixed on this gate (all through Git, never on the VPS): `TLS_MODE=off`/`acme` were invalid Caddy v2 syntax so the proxy could not start in either mode; the `.env.staging.example` that `deploy.sh` requires did not exist; audit-chain verification falsely reported tampering whenever the DB session timezone was not UTC; the acceptance suite was not actually runnable from a client machine.
- Still mocked / demo: OCR-LLM provider (`mock`), HS rules, tariff, FTA, policy (all `is_demo`, NON-AUTHORITATIVE), local file storage. Real providers, authoritative data, OIDC, S3, rate limiting/CSP and any customs-system connection remain out of scope.
- Local web unit tests require **Node 22** (CI's version); Node 26 breaks jsdom 25.

## Previous checkpoint (end of session 2 · 2026-10-08)

- Branches: `main` `2afdf6b` unchanged · `develop` = release candidate (feature/g00…g13 merged `--no-ff`, pushed) · `claude/busy-davinci-9u8bye` mirrors develop
- Tests: **68 pytest** (PostgreSQL 16, schema from zero) + **3 vitest** + **1 Playwright E2E** + HTTP acceptance 17/17 vs Docker; `make verify` and `scripts/collect_evidence.sh` green; CI: `CI_EXTERNAL_UNVERIFIED`
- Migration head: `0010_copilot_meta` (0001 → 0010, single head, downgrade verified)
- Works end-to-end locally (API + web): the owner's 16-step flow, V12 functional parity, reviewer workflow, release gate, versioned drafts, audit chain, approved-only learning.
- Mocked / demo: OCR-LLM provider (`mock`), HS rules, tariff, FTA, policy (all `is_demo`, NON-AUTHORITATIVE), local file storage.
- Docker Compose: executed in G14 (PASS). Staging compose (`infra/staging/`) prepared, not deployed. Not done: real providers, authoritative data, OIDC, S3, rate limiting/CSP, staging deploy, any customs-system connection.

## Next
**Owner production review** of `develop` `9649ec7` using `docs/G15_STAGING_ACCEPTANCE_REPORT.md`.
Only after that review: PR `develop` → `main`. Production deployment and any customs-system
integration remain separate, explicitly-gated decisions (product rule #7).

Open owner decisions before production: B-01 real OCR/LLM credentials · B-02 authoritative
tariff/FTA/policy source · B-06 whether `hq.vipgroup.com.vn` should keep depending on the
host's shared Caddy · B-07 delete the staging demo users once acceptance is signed off.
