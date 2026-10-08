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
