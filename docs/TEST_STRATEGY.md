# TEST STRATEGY

## Principles
- **Business rules are tested without an LLM.** The AI gateway is mocked deterministically; every fail-closed rule (NEEDS_REVIEW,
  BLOCKED, release gate, approved-only learning, RBAC, tenant isolation) is asserted in plain pytest against PostgreSQL.
- **Schema from zero on every run.** `tests/conftest.py` drops and recreates the test schema and runs `alembic upgrade head`, so the
  migration chain itself is exercised on every test session.
- **Evidence, not assertions of intent.** Results are written to `artifacts/test-results/` by `scripts/collect_evidence.sh`.

## Layers
| Layer | Tool | Location | What it proves |
|---|---|---|---|
| API unit/integration | pytest + FastAPI TestClient + PostgreSQL 16 | `apps/api/tests/test_*.py` | every gate's behaviour (66 tests) |
| Acceptance (owner's 16 steps) | pytest | `tests/test_acceptance_mvp.py` | the full MVP path through the public API |
| Script-path regression | pytest | `tests/test_seed_and_registration.py` | seed/pipeline evaluate identically to HTTP |
| Frontend unit | vitest + Testing Library (jsdom) | `apps/web/src/**/*.test.tsx` | V12 navigation, login gate, goods states |
| Browser E2E | Playwright (Chromium) on the real stack | `apps/web/e2e/smoke.spec.ts` via `scripts/e2e.sh` | login → V12 pages → BLOCKED item → Copilot → release gate |
| Static | ruff, tsc, vite build, secret scan | `scripts/verify.sh` | lint, types, bundle, no secrets |

## Mandatory scenarios (owner brief) → tests
1. package count conflict → `test_mapping::test_package_count_conflict_detected_with_evidence`
2. low-confidence HS → NEEDS_REVIEW/BLOCKED → `test_goods_hs::test_low_confidence_item_is_blocked_and_blocks_case`
3. critical issue prevents release → `test_review_release::test_critical_issue_prevents_release_but_allows_watermarked_preview`
4. reviewer approval changes state → `test_goods_hs::test_reviewer_approval_changes_item_state_and_clears_issue`, `test_full_reviewer_path_…`
5. rejected AI suggestion never learned → `test_learning::test_rejected_ai_suggestion_does_not_enter_memory`, `test_request_info_…`
6. approved decision enters history → `test_learning::test_approved_decision_enters_memory_with_lineage`
7. document source lineage → `test_documents`, `test_mapping::test_pipeline_parses_documents_and_maps_fields_with_lineage`
8. RBAC on critical actions → `test_auth_cases`, `test_goods_hs::test_hs_decision_rbac_validation_and_override_rules`, `test_issue_actions_rbac_…`
9. audit event written → `test_auth_cases::test_audit_is_append_only_and_hash_chained`, every flow test checks `/audit`
10. API validation → `test_auth_cases::test_case_api_validation`, `test_documents::test_upload_validation`

## Not yet covered (tracked in docs/STAGING_READINESS.md)
Real provider adapters (need credentials), S3 storage adapter, load/perf, Docker Compose execution (no daemon in the build session).
