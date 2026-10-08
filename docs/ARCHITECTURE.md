# Architecture

## Monorepo

```text
apps/web        React/TypeScript UI
apps/api        FastAPI API + domain services
packages/shared contracts/schemas where useful
infra           local/staging deployment files
tests           cross-service E2E/acceptance
```

## Backend domains

- identity / RBAC
- customers / suppliers
- cases
- documents
- extraction / mapping
- goods
- classification
- valuation / tariff
- origin / FTA
- policy
- review
- declaration drafts
- audit
- knowledge / approved memory
- ai gateway

## Storage

PostgreSQL is the source of truth for structured state.

Documents live in object storage/NAS behind a storage adapter. Database records hold metadata and controlled object references; no public unrestricted document URLs.

## AI gateway

Use an interface such as:

- `extract_document()`
- `normalize_goods()`
- `propose_hs_candidates()`
- `explain_case()`
- `propose_description()`

Provider SDKs must remain behind the gateway.

## Deterministic rule engine

Validation, workflow state, authorization, release gating and effective-date checks must be deterministic application logic rather than prompt-only behavior.

## Initial deployment

Docker Compose for local/staging:

- web
- api
- postgres
- optional redis/worker when background work is introduced
- local S3-compatible storage only if needed for staging
