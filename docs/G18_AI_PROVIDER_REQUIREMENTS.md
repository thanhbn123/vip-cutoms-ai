# G18 — AI PROVIDER REQUIREMENTS (B-01 architecture)

Status: **architecture and adapter boundary implemented; vendor, credentials and acceptance test are OWNER INPUTS**
(`docs/G18_OWNER_INPUTS.md`). B-01 stays `BLOCKED_OWNER` until a real provider passes acceptance in staging.

## 1. Capabilities (one boundary each, selectable by configuration)

| Capability | Env variable | Protocol (`apps/api/app/ai/base.py`) | Mock | `http-llm` |
|---|---|---|---|---|
| Document OCR (image/PDF → text) | `DOCUMENT_OCR_PROVIDER` | `DocumentOcrProvider.ocr()` | text pass-through only | **not implemented** — OCR vendor is an owner input |
| Document extraction (text → fields) | `DOCUMENT_AI_PROVIDER` | `DocumentExtractionProvider.extract_document()` | regex over fixture text | yes |
| HS reasoning (item → description + reasoning) | `HS_AI_PROVIDER` | `HsReasoningProvider.propose_description()` | deterministic | yes |
| Customs Copilot (question + context → answer) | `COPILOT_PROVIDER` | `CopilotProvider.answer_case_question()` | template answers | yes |

`AI_PROVIDER` is the default for all four; each specific variable overrides it. Resolution lives in
`app/ai/gateway.py:get_capability(capability)`. Domain services (`mapping`, `copilot`, `hs_engine`) import
the gateway only — no vendor name appears outside `app/ai/`.

Implemented provider names: `mock`, `http-llm`. Any other name → `ProviderNotConfigured` → `/ready` 503.
`http-llm` selected without `AI_PROVIDER_BASE_URL` + `AI_PROVIDER_API_KEY` + `AI_PROVIDER_MODEL` → refused.
**There is no fallback from a failed or unconfigured real provider to the mock, in any mode.**

## 2. `http-llm` — the vendor-neutral adapter (`app/ai/http_llm_provider.py`)

Wire format: `POST {AI_PROVIDER_BASE_URL}/chat/completions` with `model`, `messages`, `temperature: 0`,
`response_format: {"type": "json_object"}`; health probe `GET {base_url}/models`. This is the widely
implemented chat-completions JSON shape that many vendors and self-hosted gateways accept, so the owner's
vendor choice is a configuration + acceptance exercise, not a code fork. No vendor-specific behaviour exists.

| Requirement (owner brief §5) | Implementation | Test |
|---|---|---|
| timeouts | `httpx.Timeout(AI_TIMEOUT_SECONDS, connect≤10s)`; health probe 5 s | `test_timeout_raises_provider_timeout` |
| retries | bounded (`AI_MAX_RETRIES`, default 2) with exponential backoff on 408/429/5xx and transport errors; 4xx never retried | `test_retries_on_5xx_then_succeeds`, `test_non_retryable_4xx_fails_immediately` |
| structured output validation | pydantic schemas per capability; any violation rejects the WHOLE answer (`ProviderInvalidOutput`) | `test_extraction_validates_structured_output…`, `test_non_json_content_is_invalid_output` |
| token/cost accounting | `app/ai/accounting.py`: per-call tokens, USD at configured prices, UTC-day ledger, exported on `/metrics` | `…accounts_cost`, `test_daily_budget_blocks_before_the_call` |
| request correlation id | UUID per logical call, sent as `X-Request-ID`, logged, appended to warnings/reasoning | `…accounts_cost` |
| no silent fallback / fail closed | every failure raises `ProviderError`; `mapping.parse_document` → `PARSE_FAILED` + CRITICAL `AI_PROVIDER_FAILED`, zero values; Copilot → HTTP 503 `AI_PROVIDER_UNAVAILABLE` | `test_provider_failure_yields_no_values…`, `test_copilot_provider_failure_returns_503…` |
| PII / document handling | documented in `docs/G18_AI_PROVIDER_SECURITY.md`; size cap `AI_MAX_DOCUMENT_BYTES` (refuse, never truncate) | `test_oversized_document_is_refused_not_truncated` |
| redaction / logging policy | `app/ai/redaction.py`: bodies never logged, only size + fingerprint; emails/long numbers/keys redacted | `test_redaction_never_leaks…` |
| provider health status | `health()` = configured + cached live probe (30 s), surfaced per capability in `/ready` and `/metrics` | `test_health_probe_and_cache`, `test_health_reports_unreachable_endpoint` |
| review is mandatory | real-provider Copilot answers always carry `requires_review=True`, whatever the model claims | `test_copilot_answer_always_requires_review…` |

Business-layer validation is unchanged and still applies on top: unknown keys, out-of-range confidence,
empty values and fabricated sources are dropped in `app/services/mapping.py` / `app/services/copilot.py`.

## 3. Prompts

`app/ai/prompts.py` holds the three system prompts and the JSON schema hints. Prompts demand strict JSON,
forbid inventing or normalising values, require line references and confidences, and instruct the model to
report unknowns. Prompts contain no tariff, legal or HS knowledge: that stays in versioned datasets (B-02).

## 4. Mode interaction

| Mode | mock allowed | real provider required | on real-provider failure |
|---|---|---|---|
| demo | yes | no | n/a (mock) |
| limited | yes | no (may be enabled for evaluation) | fail closed as above; case BLOCKED |
| full | **no** (startup refused, `/ready` 503) | yes, configured **and** healthy for all four capabilities | fail closed as above |

## 5. Acceptance criteria before B-01 can be marked RESOLVED

1. Owner supplies vendor, endpoint, model, credential and a data-processing agreement (`G18_OWNER_INPUTS.md`).
2. Credential is placed on the staging host only (`infra/staging/.env`, chmod 600); never in Git.
3. `AI_PROVIDER=http-llm` on staging in **limited** mode; `/ready` reports `providers.*.healthy=true`.
4. Extraction accuracy on the owner's 20-document sample: measure field-level precision/recall against reviewer
   truth; record in `docs/G19_AI_ACCEPTANCE.md`. Threshold is an owner decision (proposed ≥ 0.90 precision on
   critical fields; recall is less important because missing fields fail closed).
5. Cost report: tokens and USD for the sample from `/metrics` and the ledger logs; daily budget set.
6. Negative drills: revoke the key → `/ready` 503 within the health cache window; provider 5xx → `AI_PROVIDER_FAILED`.
7. OCR: binary documents need a `DocumentOcrProvider`. Until an OCR vendor is chosen, scanned documents are
   reported unreadable and reviewed manually (fail closed). This is part of B-01.
