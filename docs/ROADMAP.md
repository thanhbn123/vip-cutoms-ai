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
