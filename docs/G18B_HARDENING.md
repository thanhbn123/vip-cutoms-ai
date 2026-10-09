# G18B — HARDENING FOLLOW-UPS (no owner input required) · 2026-10-09

Scope: the engineering items left open by G16 (three LOW findings) and G18A (known limitations), all of which
could be closed without credentials, licensed data or a production host. Owner blockers B-01/B-02/B-06 are
unchanged; B-07 execution still needs the operator (`docs/G18_B07_DEMO_USERS.md`).

| # | Item | Before | After | Tests |
|---|---|---|---|---|
| 1 | Malformed signed token payload → 500 (G16 low) | `decode_token` parsed JSON without guarding; a correctly signed but garbled body raised in the dependency | `InvalidToken("malformed payload")` on bad base64/JSON/non-object/missing `sub`/`tid`/`exp` → **401** | `test_signed_but_malformed_token_is_401_not_500` (4 variants), `test_expired_and_valid_tokens_still_behave` |
| 2 | `nosniff` only at the proxy (G16 low) | API responses relied on Caddy for security headers | API middleware sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `Cache-Control: private, no-store` on `/api/*` | `test_api_responses_carry_security_headers` |
| 3 | Content-Disposition quoting (G16 low) | raw filename interpolated inside quotes (breaks on `"`/non-ASCII, header-injection surface) | `app/core/http.py:content_disposition` — safe ASCII fallback + RFC 5987 `filename*`, CR/LF stripped; used by document and draft downloads | `test_content_disposition_quotes_and_encodes`, `test_document_download_uses_safe_header` |
| 4 | Heading-only (4-digit) rate/policy lookups (G18A limitation) | `rates.get(hs_code[:4])` | `app/services/hs_lookup.py` longest-prefix match (full code → … → heading) in valuation, origin and policy; reasoning cites the matched line and dataset version | `test_lookup_prefers_the_most_specific_key`, `test_valuation_uses_eight_digit_line_when_authoritative_schedule_has_one` |
| 5 | SENIOR_REVIEWER verification only at service level (G18A limitation) | verify endpoint required `knowledge.manage` (ADMIN) | new permission `knowledge.verify` for ADMIN and SENIOR_REVIEWER; import/activate stay ADMIN-only (separation of duties kept) | `test_senior_reviewer_can_verify_but_not_import` |
| 6 | In-process AI cost ledger resets on restart (G18A limitation) | memory only | migration `0012_ai_usage_events`; every call persists an accounting row (no content); budget check = max(memory, persisted spend today) — DB unreachable → memory still enforced | `test_ledger_rows_are_persisted_and_budget_survives_a_restart` |
| 7 | `/metrics` reachable from the internet; proxy routes to a dead api (G18A note) | generic proxying | Caddyfile: `/metrics` served only to `private_ranges`/loopback, otherwise 404; `reverse_proxy api:8000` with `health_uri /health` (dependency-free) | `test_caddyfile_restricts_metrics_to_private_ranges_and_health_checks_the_api` + existing Caddyfile tests |

Migration: `0012_ai_usage_events` (head, single) — upgrade from zero, downgrade to `0011`, re-upgrade verified.

Not in scope (still requires owner input or a decision): rate limiting on `/auth/login` (proxy module choice
belongs to the B-06 proxy decision), OCR adapter (vendor), national 8-digit datasets (source), production
provisioning.
