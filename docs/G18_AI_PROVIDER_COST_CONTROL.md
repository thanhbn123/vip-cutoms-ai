# G18 — AI PROVIDER COST CONTROL

## 1. Mechanism (`apps/api/app/ai/accounting.py`)

- Every logical provider call produces one `CallMeta` (tokens in/out from the vendor `usage` block, attempts,
  latency, outcome) and one ledger line in the log (`vip.ai.accounting`).
- Cost = `in_tokens/1000 × AI_COST_PER_1K_INPUT_TOKENS_USD + out_tokens/1000 × AI_COST_PER_1K_OUTPUT_TOKENS_USD`.
  Prices come from the vendor's list and are configuration, not code. With prices at 0 the ledger still counts
  tokens and calls.
- `AI_DAILY_BUDGET_USD`: checked **before** each call against the UTC-day spend; when reached, the call is
  refused with `ProviderBudgetExceeded` (fail closed: no value, CRITICAL issue / 503). Required in full mode.
- `AI_MAX_DOCUMENT_BYTES` caps the largest single prompt source.
- `/metrics` exposes `vip_ai_calls_total`, `vip_ai_failures_total`, `vip_ai_cost_usd_today`,
  `vip_ai_tokens_today{direction}` for alerting (`G18_MONITORING_ALERTS.md`).

## 2. Limits of the current implementation (stated, not hidden)

- The ledger is in-process memory: a restart resets the day's counter. For a single `api` container this
  under-counts only across restarts; a persistent ledger table is the planned follow-up once a vendor is
  chosen (it needs real prices to be meaningful).
- Retries are not charged separately; vendors do not bill failed requests in most cases, and a failed call is
  counted as one failure.

## 3. Proposed budget policy (PROPOSED — owner approval required)

| Setting | Proposal | Rationale |
|---|---|---|
| `AI_DAILY_BUDGET_USD` (staging evaluation) | 5 | enough for the 20-document acceptance sample several times over |
| `AI_DAILY_BUDGET_USD` (production, limited/full) | sized from the sample: average cost per case × expected daily cases × 1.5 | measured, not guessed |
| alert at | 80 % of budget | time to react before refusals start |
| per-document cap | `AI_MAX_DOCUMENT_BYTES` 5 MiB | a 5 MiB text document is already anomalous |

## 4. Reporting

Weekly: `vip_ai_cost_usd_today` daily maxima, calls, failure ratio, cost per case (calls per case are visible
in audit: `document.parsed` / `document.parse_failed` carry the provider name). The first report belongs in the
B-01 acceptance record.
