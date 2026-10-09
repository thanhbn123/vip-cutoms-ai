# G18C — CODE-REVIEW REMEDIATION · 2026-10-09

A structured code review of the whole G18 diff (`main...develop`, high effort) produced 20 findings. This gate
disposes of every one. No owner input was needed; owner blockers B-01/B-02/B-06 and the B-07 staging execution
are unchanged.

## Findings and disposition

| # | Finding | Severity | Disposition | Where | Tests |
|---|---|---|---|---|---|
| 1 | A REVIEWER could `resolve` any system-detected CRITICAL issue (knowledge unavailable, provider failed, low-confidence HS, …) with a sentence, and `issues.sync` never reopened it → fail-closed condition permanently hidden | **HIGH** | `resolve` refuses (`409 SYSTEM_ISSUE_NOT_RESOLVABLE`) for CRITICAL + `auto_resolvable`; only a Senior **waive** with evidence remains. `sync` now **reopens** a SYSTEM-resolved issue when the condition is detected again (audited `issue.reopened`) | `app/api/review.py`, `app/services/issues.py` | `test_reviewer_cannot_resolve_system_detected_critical_issue`, `test_auto_resolved_issue_reopens_when_condition_reappears` |
| 2 | Stale `CaseField` kept the value/source of a superseded document version when the new version no longer yielded the field | HIGH | AI-origin, unapproved field is cleared (value None, NEEDS_REVIEW, lineage cleared, `MAP-STALE-CLEARED`) + `FIELD_MISSING`; an APPROVED one raises `APPROVED_SOURCE_GONE` | `app/services/mapping.py` | `test_stale_ai_field_is_cleared_when_new_document_version_lacks_it` |
| 3 | `approve_field` turned an as-is approval (UI sends the same value) into a manual entry, destroying AI lineage | HIGH | same value on an unconflicted field = plain approval (lineage kept); a different value, or a choice among conflicting values, stays a reviewer entry | `app/api/pipeline.py` | `test_approve_field_with_same_value_keeps_ai_lineage`, existing `test_mapping` conflict test |
| 4 | Decisions on a `DRAFT_EXPORTED`/`READY_TO_EXPORT` case mutated data while the status stayed exported | HIGH | `release.reopen_if_exported` → `REVIEW_REQUIRED` (audited) before HS decision, C/O decision, field approve/approve-all, issue resolve/waive, proposal apply | `app/services/release.py` + 5 endpoints | `test_hs_decision_after_export_reopens_case` |
| 5 | `build_items` KeyError when an invoice row lacked `description` → pipeline 500 | HIGH | CRITICAL `ITEM_DESCRIPTION_MISSING`, row skipped (fail closed) | `app/services/goods.py` | covered by validation path; no 500 reachable |
| 6 | Imported TARIFF/FTA/POLICY packages were stored unvalidated → evaluators KeyError on activation | HIGH | `customs_data.validate_payload(kind, payload)` at import (`422 INVALID_PACKAGE` with problem list) | `app/services/customs_data.py` | `test_invalid_packages_are_refused_at_import` (6 cases), `test_valid_packages_pass_validation` |
| 7 | A document that parsed to zero values (scan) raised no issue; the case could reach REVIEWED | HIGH | every current `PARSE_FAILED` document raises CRITICAL `DOCUMENT_UNREADABLE` (or `AI_PROVIDER_FAILED`) | `app/api/pipeline.py` | `test_unreadable_document_raises_critical_issue_and_blocks` |
| 8 | Tax applied the *recomputed* preferential rate instead of the rate the reviewer approved | MEDIUM | rate from `reviewer_decision.preferential_duty_pct` wins | `app/services/valuation.py` | existing C/O tests |
| 9 | APPROVE accepted a `candidate_id` whose heading differed from `hs_code` | MEDIUM | `422 INVALID_CANDIDATE` | `app/api/goods.py` | `test_hs_decision_rejects_candidate_heading_mismatch` |
| 10 | A goods line no longer on the invoice stayed in drafts after a WARNING was resolved | MEDIUM | `ITEM_NOT_ON_INVOICE` is CRITICAL (Senior waive with evidence) | `app/services/goods.py` | release flow tests |
| 11 | `/metrics` guard `private_ranges` admitted everyone behind an upstream proxy (`TLS_MODE=off`) | MEDIUM | `remote_ip {$METRICS_ALLOW_FROM:127.0.0.1/32}` — closed by default; operator sets the monitoring host CIDR | `infra/staging/Caddyfile`, compose, env template | `test_caddyfile_restricts_metrics_to_private_ranges_and_health_checks_the_api` |
| 12 | CSV formula injection via document-extracted strings | MEDIUM | `csv_safe` prefixes `=`, `+`, `-`, `@`, tab, CR with `'` | `app/services/export_adapters.py` | `test_csv_cells_neutralise_formulas` |
| 13 | `create_user` reveals whether an e-mail exists in another tenant (global unique e-mail) | LOW | **Not fixed — documented limitation.** E-mail is the global login identifier (`users.email UNIQUE`); per-tenant uniqueness needs tenant-aware login (D-012 identity work). The oracle is available to tenant ADMINs only | — | — |
| 14 | `supersede` accepted self-supersession / already-superseded datasets | MEDIUM | guards: same id, old already superseded, new itself superseded → `409 INVALID_SUPERSESSION` | `app/services/customs_data.py` | `test_supersede_guards` |
| 15 | Signed token with non-UUID `sub` → 500 | MEDIUM | UUID parse inside the 401 path | `app/api/deps.py` | `test_signed_token_with_non_uuid_subject_is_401` |
| 16 | REJECT left `hs_code` set → rejected code still exported | MEDIUM | `hs_code` cleared on REJECT; `hs_decision_id` points at the reject | `app/api/goods.py` | `test_reject_clears_hs_code` |
| 17 | N+1 queries in review queue and item candidates | LOW | single grouped query each | `app/api/review.py`, `app/api/goods.py` | existing queue/items tests |
| 18 | `/docs` + `/openapi.json` exposed to the internet | LOW | API disables them outside development; Caddy no longer proxies them | `app/main.py`, `infra/staging/Caddyfile` | `test_openapi_docs_disabled_outside_development`, Caddyfile test |
| 19 | Web client `JSON.parse` on proxy HTML errors → raw SyntaxError | LOW | non-JSON error → `ApiError(status, "UPSTREAM")` | `apps/web/src/api.ts` | `src/api.test.ts` (vitest include widened to `.ts`) |
| 20 | Test-suite robustness: a leaked session made the per-test cleanup hang forever | LOW (test infra) | `SET LOCAL lock_timeout='10s'` in the cleanup fixture → loud failure | `apps/api/tests/conftest.py` | observed during this gate |

Process change recorded in D-038: a system-detected CRITICAL issue is never "resolved" by a person; the acceptance
flows (`scripts/acceptance_http.py`, `tests/test_review_release.py`) were updated to waive with evidence as a
Senior Reviewer, which is what D-009 always intended.

## Verification (fresh, this gate)
| Check | Result |
|---|---|
| Backend pytest | **152 passed**, 1 skipped (candidate-mismatch test skips when the fixture yields a single heading) |
| Infra pytest | **103 passed** |
| Vitest | **5 passed** (3 files; `api.test.ts` added) |
| tsc · ruff · vite build · secret scan | PASS (`VERIFY: ALL CHECKS PASSED`) |
| Playwright native | **2 passed** (isolated DB; a first run shared `vip_customs_test` with a concurrent pytest run and failed on login — environment, not product) |
| Docker boot from zero | migrate to `0012_ai_usage_events`, health/ready 200, 0 restarts, 0 secret leaks |
| Docker acceptance A–P (updated flow: Senior waives criticals with evidence) | **17/17** · Playwright vs Docker **2/2** |
