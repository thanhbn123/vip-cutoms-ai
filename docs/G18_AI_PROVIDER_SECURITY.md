# G18 — AI PROVIDER SECURITY, PII AND DOCUMENT HANDLING

Applies to any real provider (`http-llm` today). The mock sends nothing anywhere.

## 1. What leaves the host, and when

| Capability | Payload sent | Contains |
|---|---|---|
| document extraction | document **text** (decoded UTF-8) + document type + allowed keys | trade data: parties, prices, invoice/BL numbers, goods descriptions — commercially sensitive, may include personal names/addresses |
| HS reasoning | one item's structured data | goods description, model, attributes |
| Copilot | the structured case context (`app/services/copilot.py:build_context`) + question | case summary, items, issues, valuation; reviewer identities are **not** included |
| health probe | none (GET /models) | — |

Binary documents (scans, PDFs) are **not** sent by `http-llm` (no OCR); they are reported unreadable. An OCR
provider, when chosen, will send the image itself — that is a separate data-processing decision for the owner.

## 2. Non-negotiables

1. **Data-processing agreement before enablement.** A real provider is enabled only after the owner confirms
   the vendor contract covers customer trade documents (retention, training opt-out, region). Recorded in
   `docs/G18_OWNER_INPUTS.md` → B-01.
2. **Credential handling.** `AI_PROVIDER_API_KEY` lives only in the host env file (chmod 600) or the host
   secret manager. Never in Git (`scripts/secret_scan.sh` blocks `sk-…` shapes; the production template keeps
   the key empty and `tests/test_production_infra.py` asserts it). Rotation: replace the value, restart `api`.
3. **No prompt/response bodies in logs, audit or metrics.** `app/ai/redaction.py`: only byte size and a 12-hex
   SHA-256 fingerprint are logged. Audit evidence for parse failures carries the error class, not the payload.
   `redact()` additionally masks bearer tokens, key-like strings, e-mail addresses and ≥8-digit numbers in any
   free text that reaches a log line.
4. **Correlation, not content.** Every call has a UUID `X-Request-ID`, recorded in the accounting log, in the
   extraction warnings and in Copilot reasoning, so a vendor-side incident can be matched to a case without
   storing the exchanged text.
5. **Fail closed.** Provider failure or invalid output produces **no** value; critical fields remain
   `NEEDS_REVIEW` with no value, the case is `BLOCKED` with `AI_PROVIDER_FAILED`, Copilot returns 503.
6. **Untrusted output.** Provider output is validated twice: schema (adapter) and business rules (services).
   Sources not present in the case context are dropped; `requires_review` is forced true.
7. **Transport.** HTTPS only (`AI_PROVIDER_BASE_URL` must be `https://` in production — operator check; a
   plain-HTTP gateway is acceptable only on a loopback/self-hosted address). Timeouts bounded.
8. **Volume limits.** `AI_MAX_DOCUMENT_BYTES` (default 5 MiB) refuses oversize documents instead of truncating
   them; the daily budget stops runaway spend (`G18_AI_PROVIDER_COST_CONTROL.md`).
9. **Tenant isolation is unchanged.** Context is built from one case the caller is authorised for; nothing in
   the provider path crosses tenants.

## 3. Logging policy (what a log line may contain)

`correlation_id, capability, provider, model, outcome, attempts, latency_ms, in_tokens, out_tokens, cost_usd`
and, for invalid envelopes, `{"bytes": N, "sha256_12": "…"}`. Nothing else.

## 4. Incident playbook (provider side)

- Suspected key leak → rotate at the vendor, update env, restart `api`, check `vip_ai_calls_total` for unexpected volume.
- Vendor outage → `/ready` shows `providers.<cap>.healthy=false`; in full mode the stack reports 503 (by design);
  in limited mode reviewers continue manually. Do **not** switch to `mock` on a production host to "unblock".
- Suspected data exposure → use correlation ids from the accounting log to list affected cases; notify per the
  owner's data-protection process.
