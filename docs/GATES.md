# GATES

Session gate list (owner brief) with mapping to `docs/ROADMAP.md`.

| Gate | Scope | ROADMAP ref | Evidence required |
|---|---|---|---|
| G00 | Repo assessment, plan, decisions, status | — | MASTER_PLAN, DECISIONS, GATES, STATUS |
| G01 | Foundation: structure, API boot, DB, Alembic, web shell, Docker, health/readiness, scripts, CI | ROADMAP G00 | health tests, migration upgrade on PG |
| G02 | Auth + RBAC + tenant + customer/supplier + case domain + audit base | ROADMAP G01 | RBAC, tenant isolation, audit tests |
| G03 | Document domain: upload, storage adapter, metadata, versioning, status | ROADMAP G02 | upload/version/authz tests |
| G04 | Parser provider abstraction + field mapping + lineage + conflict detection | ROADMAP G03 | lineage + package conflict tests |
| G05 | Goods + HS engine: candidates, confidence, reasoning, missing attrs, decisions | ROADMAP G04–G05 | low-confidence BLOCKED tests |
| G06 | Valuation + tax + C/O + policy scaffold, versioned effective-dated datasets | ROADMAP G06–G08 | dataset version traceability tests |
| G07 | Smart Declaration (field set with confidence/source/status, validation) | ROADMAP G09 (part) | API validation tests |
| G08 | Reviewer workflow, audit, release gate, draft export | ROADMAP G09 | state transition + release gate tests |
| G09 | AI Copilot (case-scoped, sourced, proposals) | ROADMAP G10 | copilot tests |
| G10 | Historical learning (approved-only) | ROADMAP G11 | learning tests |
| G11 | Frontend V12 parity | — | web build + unit tests |
| G12 | Full integration (acceptance MVP 1–13) | ACCEPTANCE | e2e API test |
| G13 | Staging readiness (runbook, compose, security checklist) | ROADMAP G13 (prep only) | checklist; deploy requires owner |
