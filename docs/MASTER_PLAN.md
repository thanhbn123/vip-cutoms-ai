# MASTER PLAN — VIP Customs AI

Baseline: `main` @ `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (bootstrap only: docs + prototypes, no code).
Product reference: `prototype/index.html` (V12 FINAL). Historical prototypes: `docs/prototypes/v1..v11.html`.

## 1. Repo inventory at baseline (G00)

| Path | Content | Assessment |
|---|---|---|
| `README.md`, `CLAUDE.md`, `PROJECT_STATUS.md` | bootstrap docs, controller rules | valid, consistent |
| `docs/PRODUCT_SPEC.md`, `AI_RULES.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `ACCEPTANCE.md` | product/AI/architecture contract | valid; roadmap numbering differs from owner's session gate list (see DECISIONS D-002) |
| `prototype/index.html` | V12 FINAL (9 sidebar pages) | canonical UX |
| `docs/prototypes/v1..v11.html` | design history | v12 is not duplicated here; `docs/prototypes/index.html` links to non-existent `vip-customs-ai-prototype-vN.html` names (cosmetic; left untouched, noted) |
| `apps/web`, `apps/api`, `packages/shared`, `infra`, `tests` | `.gitkeep` only | empty skeleton |
| `.env.example` | 4 non-secret vars | OK, extended in G01 |
| `MANIFEST.sha256`, `PUSH_TO_GITHUB.sh`, `START_CLAUDE.txt` | bootstrap artefacts | kept as-is (manifest describes the bootstrap snapshot only) |

## 2. Prototype → requirement map

| V12 page (sidebar) | Origin prototype(s) | Requirement scope | Gate |
|---|---|---|---|
| Tổng quan (dashboard) | V4, V12 | readiness %, mapped fields, history matches, release flag, critical issues, flow | G08/G11 |
| Hồ sơ & chứng từ (Document Center + lineage) | V2, V4, V5 | case create, upload 6 doc types, version, status, parse %, lineage | G02–G04 |
| Smart Declaration | V3, V4, V5 | general info, B/L, invoice, valuation, goods list, per-field confidence/source/status | G07 |
| Hàng hóa & HS | V1, V4, V5 | items, attributes, HS candidates, confidence, reasoning, missing attrs, BLOCKED | G05 |
| Knowledge Hub | V8 | versioned, effective-dated datasets (HS rules, tariff, FTA, policy) — demo labelled | G06 |
| AI Copilot | V6 | case-scoped Q&A with sources; proposals require reviewer | G09 |
| Reviewer & Release | V4, V6, V9, V11 | queue, approve/reject w/ reason, release gate, DRAFT export | G08 |
| Lịch sử & Learning | V7 | approved-only memory, fingerprints, “do not auto-copy” consultation cases | G10 |
| Quản trị | V9, V10, V11 | roles, metrics, audit, environment status | G11 |

## 3. Target architecture

```
apps/web   React 18 + TypeScript + Vite (V12 layout/CSS ported)
apps/api   FastAPI (Python 3.12) + SQLAlchemy 2 + Alembic + psycopg 3
  app/core        config, security (tokens, password hashing), RBAC
  app/models      ORM models (tenant-scoped)
  app/services    deterministic domain services: workflow, validation, hs engine,
                  valuation/tax, C/O, policy, release gate, declaration, learning, audit
  app/ai          AI gateway: provider protocol + deterministic MockProvider
  app/storage     storage abstraction: LocalFileStorage (S3 adapter later)
  app/api         HTTP routers
PostgreSQL 16     source of truth; audit table append-only (DB trigger + hash chain)
infra/            docker-compose (postgres, api, web), Dockerfiles
```

Pipeline: `Upload → Parse (provider) → ExtractedField (lineage) → Mapping → CaseField / GoodsItem → HS engine → Valuation/Tax/C/O/Policy → Issues → Reviewer → Release gate → Declaration draft (versioned JSON/CSV) → Audit → Learning memory`.

## 4. Gate plan (session numbering, owner-approved list)

See `docs/GATES.md` for acceptance/evidence per gate.

## 5. Out of scope until explicit owner gate

- any VNACCS/ECUS connection or submission (adapter interface only)
- real OCR/LLM provider calls (needs credentials) — mock provider used
- authoritative tariff / FTA / policy data (needs owner-selected source)
- staging/production hosts
