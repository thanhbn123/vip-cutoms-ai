# Gate Roadmap

## G00 — Foundation

Goal: executable repository skeleton.

Acceptance:
- web and api boot locally
- health/readiness endpoints
- PostgreSQL connection + Alembic initialized
- basic lint/test commands
- Docker Compose local environment
- `.env.example`, no secrets
- architecture decisions recorded

## G01 — Identity + RBAC + Case Model

- Operator / Reviewer / Senior Reviewer / Admin
- tenants/customers/cases
- authorization tests
- audit base event model

## G02 — Document Intake

- upload Invoice/Packing List
- controlled storage adapter
- document metadata/status
- test fixtures

## G03 — Parser + Field Lineage

- parser abstraction
- structured extraction result
- field source/provenance/confidence
- UI shows extracted fields
- conflicting field fixture

## G04 — Goods Normalization

- line-item model
- edit workflow
- source mapping
- versioning of edits

## G05 — HS Candidate Engine

- candidate list
- evidence/reason summary
- confidence
- `NEEDS_REVIEW` / `BLOCKED`
- reviewer decision workflow

## G06 — Valuation + Tax Skeleton

- deterministic calculation primitives
- demo tariff fixture clearly marked non-authoritative
- valuation issues and reviewer controls

## G07 — C/O + FTA Assessment

- Form E fixture
- cross-document matching
- assessment state, not automatic legal approval
- effective-date/version fields

## G08 — Policy Engine

- effective-dated policy rules
- requirements/evidence
- blocked state on insufficient inputs

## G09 — Smart Declaration Draft

- map approved case data to declaration-draft schema
- immutable draft versions
- validation summary
- internal export only

## G10 — AI Copilot

- case-scoped chat
- retrieval only from authorized case/knowledge data
- explanations and proposed edits
- proposals require approval for critical fields

## G11 — Historical Learning

- approved product fingerprints
- similarity search
- never auto-copy blocked/rejected historical decisions

## G12 — Operations + Management

- queues
- SLA/escalation
- management metrics
- AI correction/quality metrics

## G13 — Staging Acceptance

- real PostgreSQL
- storage
- selected OCR/LLM providers
- security review
- browser E2E
- backup/restore and rollback runbook

## G14 — External Customs Adapter Assessment

No production write integration without explicit owner approval and documented legal/technical interface assessment.

## G15–G17 — Staging acceptance, RC freeze, owner-approved main merge

Done (see `PROJECT_STATUS.md`): staging stack accepted, release candidate frozen, `main` = `4a2acb9`.

## G18 — Full-production preparation (limited mode, no owner credentials)

- explicit runtime modes `demo|limited|full`, fail-closed FULL startup/readiness (G18A)
- four AI capability boundaries + vendor-neutral adapter, authoritative-data governance (G18A/B)
- review remediation, login throttling, Knowledge Hub steward UI (G18C–E)
- tenant-aware login, user lifecycle, tenant audit feed, browser E2E in CI (G18F–H)
- owner inputs collected in `docs/G18_OWNER_INPUTS.md` (B-01 provider, B-02 data source, B-06 host, backup/monitoring destinations)

## G19 — Production provisioning in limited mode (needs owner inputs)

- dedicated host, DNS, TLS, secrets per `docs/PRODUCTION_SECRETS.md`
- off-host backup + monitoring destinations live, restore drill
- real AI provider in limited mode with acceptance record; first authoritative dataset verified
- no VNACCS/ECUS submission; drafts remain internal
