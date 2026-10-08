# VIP Customs AI

AI-assisted customs declaration operating system for Vietnamese import/export workflows.

## Product goal

Build a controlled customs workflow that turns commercial documents into a reviewable customs declaration draft:

`Documents → Parse/OCR → Field Mapping → Goods Normalization → HS AI → Tax/C/O/Policy → Reviewer → Draft Export → Audit → Learning`

The system is **fail-closed**: AI may extract, compare, explain, recommend, and prepare changes, but it must not silently finalize critical customs decisions when evidence is incomplete.

## Current status

- Product/UI prototype: **V12 FINAL**
- Backend: not implemented yet
- Database: not implemented yet
- OCR/LLM integrations: not implemented yet
- Staging: not deployed yet
- Production: not deployed

Open `prototype/index.html` for the owner-approved design direction.

## Repository layout

```text
vip-cutoms-ai/
├── prototype/                 # canonical owner-review prototype (V12)
├── docs/
│   ├── prototypes/            # V1–V12 design history
│   ├── prompts/               # controller prompts for coding agents
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── AI_RULES.md
│   ├── ROADMAP.md
│   └── ACCEPTANCE.md
├── apps/
│   ├── web/                   # React/TypeScript frontend (to be implemented)
│   └── api/                   # FastAPI/Python backend (to be implemented)
├── packages/shared/           # shared contracts/types
├── infra/                     # Docker/deployment/IaC
├── tests/                     # cross-service acceptance/e2e
├── CLAUDE.md                  # mandatory instructions for Claude Code
├── PROJECT_STATUS.md
└── .gitignore
```

## Recommended implementation stack

- Web: React + TypeScript + Vite
- API: FastAPI + Python 3.12+
- Database: PostgreSQL 16+
- Migrations: Alembic
- File storage: S3-compatible object storage or controlled NAS adapter
- Background jobs: Redis + worker only when needed
- Auth: RBAC with Operator / Reviewer / Senior Reviewer / Admin
- AI gateway: provider abstraction; no provider-specific logic in business rules
- Tests: pytest + frontend unit tests + browser E2E

## First implementation milestone

The first working vertical slice must support:

1. Create a customs case.
2. Upload Invoice + Packing List.
3. Parse document fields into structured data.
4. Show source/provenance for every extracted field.
5. Detect one cross-document conflict.
6. Create/edit line items.
7. Produce an HS candidate with confidence and `NEEDS_REVIEW` when uncertain.
8. Reviewer approves/rejects the proposed change.
9. Generate a versioned customs declaration draft.
10. Preserve immutable audit history.

Do **not** connect to production VNACCS/ECUS or submit customs declarations during the MVP.

## Start with Claude

Claude Code must read, in this order:

1. `CLAUDE.md`
2. `PROJECT_STATUS.md`
3. `docs/PRODUCT_SPEC.md`
4. `docs/AI_RULES.md`
5. `docs/ARCHITECTURE.md`
6. `docs/ROADMAP.md`
7. `docs/ACCEPTANCE.md`
8. `prototype/index.html`

Then execute Gate G00 from `docs/ROADMAP.md`.
