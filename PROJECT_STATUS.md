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
| G05 Goods + HS engine | PASS | goods items from invoice/PL/CO lines w/ lineage + attributes (description heuristics, catalogue match), versioned demo HS_RULES dataset (fail-closed if none active), deterministic candidates w/ confidence+reasoning+missing attrs, <0.70 → CRITICAL/BLOCKED, reviewer APPROVE/REJECT w/ 8-digit code, override = Senior+evidence, audit (migration 0005) |
| G06 Valuation + Tax + C/O + Policy scaffold | PASS | versioned effective-dated demo TARIFF/FTA/POLICY datasets (labelled NON-AUTHORITATIVE, admin can deactivate → evaluators fail closed), deterministic customs-value arithmetic, per-item tax only after approved HS, C/O assessment states + reviewer APPLY (fail-closed on ineligible), policy UNDETERMINED (critical) → requirements after HS approval, assessments API, issue ownership by evaluator (migration 0006) |
| G07 Smart Declaration | PASS | read-model with 5 sections, every field = value+confidence+source+reasoning+review status, 3 items w/ HS/CO/tax/policy, deterministic validation list, readiness % (`GET /cases/{id}/declaration`) |
| G08 Reviewer / Audit / Release | PASS | issue resolve/waive (critical waive = Senior + evidence), approve-all critical fields (skips conflicted), release gate (all CRITICAL checks), mark-ready → READY_TO_EXPORT, immutable versioned drafts: PREVIEW anytime (watermark) / RELEASE only from READY_TO_EXPORT → DRAFT_EXPORTED, JSON+CSV internal adapters (no VNACCS), reviewer queue, dashboard summary, hash-chain verified (migration 0007) |
| G09 AI Copilot | PASS | case-scoped context (tenant-authorised only), deterministic mock intents (MISSING / HS_WHY / CO / VALUATION / DESCRIBE / GENERAL) with sources + reasoning, provider output validated (fabricated source ids dropped), DESCRIBE → Proposal (PROPOSED) applied only by a reviewer other than the requester, messages persisted + audited |
| G10 Historical learning | PASS | product_memory written only from APPROVE decisions (evidence hash, fingerprint, reviewer), rejected decisions never stored, EXACT/MODEL history refs + +0.05 boost for reusable memory, CONSULTATION/DISPUTE outcome (Senior) → reference-only "do not auto-copy", item history/price-delta API, Copilot price-anomaly answer (migration 0008) |
| G11 Frontend V12 parity | PASS | React+TS SPA reusing V12 CSS/sidebar: login, Tổng quan (readiness/mapped/history/release metrics, flow, critical issues, AI summary), Hồ sơ & chứng từ (create case, master data, Document Center upload+parse, lineage), Smart Declaration (5 sections, per-field confidence/source/status, edit/approve/approve-all, validation), Hàng hóa & HS (candidates, reasoning, attributes, HS decision, C/O decision, tax/policy), Knowledge Hub (versioned demo datasets, toggle), AI Copilot (chat, sources, proposals queue), Reviewer & Release (queue, issues resolve/waive, gate, DRAFT/READY/release, downloads), Lịch sử & Learning, Quản trị (metrics, production path, users, audit) · vitest 3 tests · seed script `scripts/seed_demo.py` |
