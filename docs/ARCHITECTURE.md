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

## G18 — runtime modes, provider boundaries, authoritative data

```
APP_MODE ──► app/core/modes.py ──► startup gate (create_app) + readiness gate (/ready)
                 │
   demo/limited: mock AI + demo datasets allowed (banner)   full: real providers + verified authoritative data only
                 │
app/ai/gateway.get_capability(cap) ── cap ∈ {document_ocr, document_ai, hs_ai, copilot}
        ├── mock        app/ai/mock_provider.py          (deterministic, offline)
        └── http-llm    app/ai/http_llm_provider.py      (vendor-neutral; timeouts, retries, schema validation,
                                                          correlation id, cost ledger app/ai/accounting.py, redaction)
        failures → ProviderError → mapping: PARSE_FAILED + CRITICAL AI_PROVIDER_FAILED · copilot: 503 (no fallback)

app/services/customs_data.py ── select_dataset(kind, on, mode)  ← the only path evaluators use
        candidates: active ∧ effective ∧ not superseded
        full: is_authoritative ∧ verified ∧ ¬demo ; >1 → ConflictingDatasets (reviewer) ; 0 → NoActiveDataset
        import (FileImportProvider / POST /knowledge/datasets/import) → verify (ADMIN/SENIOR) → activate → supersede
        knowledge_datasets provenance columns (migration 0011), CHECK NOT (is_authoritative AND is_demo)

identity (G18F): users.email UNIQUE per (tenant_id, email) · POST /auth/login {email, password, tenant?}
        candidates = active accounts with the e-mail (∩ tenant code if given) → verify password against each
        1 match → token{sub, tid, role} ; ≥2 matches → 401 TENANT_REQUIRED (password holder only) ; else 401 INVALID_CREDENTIALS
        create_user: uniqueness checked inside the admin's tenant only (no cross-tenant oracle)
        lifecycle (G18G): PATCH /users/{id} · POST /users/{id}/reset-password · POST /auth/change-password — audited, reason required
        GET /audit (G18H): tenant feed of non-case events (user.*, auth.*, knowledge.*), newest first; case audit stays per case
        token{iat} < users.password_changed_at → 401 (stateless revocation, migration 0014); is_active=false → 401; role read from DB row

/ready  mode · database · migrations vs head · providers[cap] · customs_data_authoritative[kind] · backup_status · release_sha · blocking[]
/metrics  Prometheus text (app/core/metrics.py + readiness.metrics_lines): http, 5xx, ai calls/failures/cost/tokens, dataset age, backup age
```
