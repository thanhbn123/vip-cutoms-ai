# G18A — FULL-PRODUCTION PREPARATION · REPORT · 2026-10-09

## Verdict
**G18A: PASS (preparation scope).** Everything that could be built without owner credentials, licensed data or
a production host is built, tested and documented. B-01, B-02 and B-06 remain `BLOCKED_OWNER` by definition;
B-07's mechanism is ready but its staging execution could not be performed from the build session.
`main` = `4a2acb9` unchanged. Production NOT deployed. Staging NOT modified.

## Git
| | |
|---|---|
| MAIN SHA | `4a2acb9130afb47b30350ed7b52197e28717847a` (unchanged, not rewritten) |
| PRE-DEVELOP SHA | `781a98d82a8b97f6eca997e969effadeb9b44646` |
| Feature branch | `feature/g18-full-production-prep` (merged `--no-ff` into `develop`; FINAL DEVELOP SHA in the final report) |
| Release tag `v0.1.0-rc1` | local at `4a2acb9`, push refused by the session credential → **TAG_EXTERNAL_BLOCKED** (operator: `git push origin refs/tags/v0.1.0-rc1`) |

## What was built

| Area | Delivered | Where |
|---|---|---|
| Runtime modes | `APP_MODE=demo\|limited\|full`; FULL refuses startup with mock providers, missing `AI_PROVIDER_*`, missing budget or backup path, dev env; policy per mode (mock allowed, demo data allowed, filing decisions) | `app/core/modes.py`, `app/core/config.py`, `app/main.py` |
| Readiness | `/ready` reports mode, DB, migration vs head, providers per capability, authoritative data per kind, backup status, release SHA, `blocking[]`; FULL → 503 on any gap; `/health` reports mode + SHA; `/metrics` Prometheus text | `app/services/readiness.py`, `app/api/health.py`, `app/core/metrics.py` |
| AI provider boundaries (B-01) | protocols for OCR / extraction / HS / Copilot; per-capability env selection; `http-llm` vendor-neutral adapter: timeouts, bounded retries + backoff, pydantic output validation, correlation id, token/cost ledger + daily budget, redaction, health probe, size cap; **no fallback**: `PARSE_FAILED` + CRITICAL `AI_PROVIDER_FAILED`, Copilot 503 | `app/ai/{base,gateway,http_llm_provider,accounting,redaction,prompts}.py`, `app/services/{mapping,copilot}.py`, `app/api/pipeline.py` |
| Authoritative data (B-02) | provenance columns + `CHECK NOT (is_authoritative AND is_demo)`; package model + `FileImportProvider` + `DemoFixtureProvider`; `register/verify/supersede`; `select_dataset` (expired/superseded never; full = authoritative-only; conflicts → `ConflictingDatasets`); evaluators raise `*_KNOWLEDGE_CONFLICT`; API import/verify/supersede; notice carries mode/providers/authoritative sets | migration `0011_dataset_provenance`, `app/services/customs_data.py`, `app/services/knowledge.py`, `app/api/knowledge.py`, 4 evaluators |
| B-07 | `deactivate_demo_users.py` (exact `*@demo.local`, inventory default, confirm token, idempotent, SYSTEM audit per user, `--verify`) + `scripts/staging/deactivate_demo_users.sh` wrapper (in-container, proves 401) | `apps/api/scripts/`, `scripts/staging/`, `docs/G18_B07_DEMO_USERS.md` |
| Off-host backup | `backup_offsite.sh` (checksum verify, age encryption, GFS prefixes, retention, status JSON, refuses without owner destination/plaintext), systemd service+timer, production overlay mounts backup dir read-only for `/ready` | `scripts/production/backup_offsite.sh`, `infra/production/vip-customs-backup-offsite.*`, `docker-compose.production.yml` |
| Config wiring | env templates (`.env.example`, `.env.production.example` with `APP_MODE=limited`, empty credential placeholders, retention 7/4/6 PROPOSED), staging compose passthrough with safe defaults | `.env.example`, `infra/production/.env.production.example`, `infra/staging/docker-compose.staging.yml` |
| Web | runtime-mode banner (`role=status`) naming the mock provider; mode in the sidebar | `apps/web/src/App.tsx`, `api.ts`, `App.test.tsx` |
| Docs | `G18_AI_PROVIDER_REQUIREMENTS/SECURITY/COST_CONTROL`, `G18_AUTHORITATIVE_DATA_REQUIREMENTS`, `G18_CUSTOMS_DATA_SCHEMA`, `G18_DATA_UPDATE_PROCESS`, `G18_LEGAL_SOURCE_GOVERNANCE`, `G18_PRODUCTION_INFRA_OPTIONS` (+ proxy design), `G18_OFFHOST_BACKUP`, `G18_MONITORING_ALERTS`, `G18_PRODUCTION_ACCESS`, `PRODUCTION_SECRETS`, `G18_OWNER_INPUTS`, `G18_B07_DEMO_USERS`; DECISIONS D-033…D-036; ARCHITECTURE | `docs/` |

## Verification (fresh, this gate, Node 22.22.0, Python 3.12)

| Check | Result |
|---|---|
| Backend pytest (`apps/api`) | **122 passed** (72 → 122; 50 new G18 tests) |
| Infra pytest (root `tests/`) | **102 passed** (71 → 102) |
| Vitest | **3 passed** |
| tsc · ruff · vite build · secret scan | PASS (`VERIFY: ALL CHECKS PASSED`) |
| Playwright native / Docker | **2 passed / 2 passed** |
| Migration from zero | `0011_dataset_provenance` (head, single); downgrade to `0010` drops 10 columns + 2 constraints; re-upgrade OK; DB rejects `is_demo AND is_authoritative` (verified by a failing INSERT) |
| Docker boot from zero | build, migrate to `0011`, `/health` 200, `/ready` 200 (`mode=demo`, `blocking=[]`, provider `mock`), 21 tables, 0 restarts, 0 secret leaks |
| Docker acceptance A–P | **17/17** |

### Full-mode negative tests (owner brief §16)
| Scenario | Result | Test |
|---|---|---|
| FULL + mock AI | startup refused (`RuntimeError: APP_MODE=full refused: … mock …`) **and** `/ready` 503 `mock provider not allowed` | `test_full_mode_with_mock_ai_refuses_startup`, `test_create_app_refuses_full_mode_with_mock`, `test_full_mode_readiness_fails_with_mock_ai_and_demo_data` |
| FULL + demo customs data | `/ready` 503 `authoritative customs data unavailable for: HS_RULES, TARIFF, FTA, POLICY` | `test_full_mode_readiness_fails_with_mock_ai_and_demo_data`, `test_demo_dataset_can_never_be_verified_and_is_rejected_in_full_mode` |
| FULL + expired authoritative dataset | `/ready` 503, every kind `authoritative=false` | `test_full_mode_readiness_fails_on_expired_authoritative_dataset`, `test_expired_rule_rejected` |
| FULL + missing provider credential | startup refused; `get_capability` → `ProviderNotConfigured` (no fallback) | `test_full_mode_with_missing_provider_credential_refuses_startup`, `test_per_capability_provider_selection` |
| FULL + stale/missing backup status | `/ready` 503 `backup status stale/missing` | `test_full_mode_readiness_fails_on_stale_backup` |
| LIMITED + demo data | allowed; `/ready` 200; notice `mode_notice` present, `mock_ai_active=true`, `real_filing_decisions=false`; banner rendered | `test_limited_mode_with_demo_data_is_allowed_with_visible_warning`, `App.test.tsx` |
| DEMO | allowed; `/ready` 200, `blocking=[]` | `test_demo_mode_ready_reports_mode_and_release_sha` |

### Authoritative-data tests (owner brief §6)
expired → rejected · superseded → rejected (lineage kept) · demo in full → rejected · missing authority → `409 MISSING_AUTHORITY`
(fail closed, unusable in full) · conflicting → `ConflictingDatasets` → CRITICAL `TARIFF_KNOWLEDGE_CONFLICT`, case BLOCKED ·
checksum tamper → verification refused · non-ADMIN verify → 403 · API import→verify→activate→supersede · audit events.

## Status classification
| Item | Status |
|---|---|
| B-01 real AI | **BLOCKED_OWNER** — boundaries + adapter ready; vendor, credentials, DPA, OCR decision, acceptance sample needed |
| B-02 authoritative data | **BLOCKED_OWNER** — schema, governance, workflow, fail-closed selection ready; source, licence, cadence, steward/verifier needed |
| B-06 production infra | **BLOCKED_OWNER** — options documented, recommendation B (dedicated VPS + stack-owned Caddy); host/domain/TLS model decision needed |
| B-07 demo users | **BLOCKED (operator execution pending)** — mechanism READY and tested; staging unreachable from the build session |
| Off-host backup | **READY_FOR_CONFIGURATION** — destination/credential/age key/retention approval are owner inputs |
| Monitoring | **READY_FOR_CONFIGURATION** — `/metrics` + `/ready` live; notification destination/monitor host are owner inputs |
| Production access | **READY** (design) — deploy user model documented; keys/admin are owner inputs |
| Secrets | documented (`docs/PRODUCTION_SECRETS.md`); none committed (scan clean, template placeholders asserted by tests) |

## Open bugs
Critical 0 · High 0 · Medium 0 · Low: the three G16 low hardening items remain (Content-Disposition quoting,
`nosniff` at the API layer, 500-vs-401 on a malformed signed-token payload) plus two G18 notes: the AI cost ledger
is in-process (resets on restart) and `/metrics` should be IP-restricted at the proxy once B-06 is decided.

## Known limitations (stated) — items 2, 3 and the ledger/metrics notes were closed in G18B (`docs/G18B_HARDENING.md`)
- `http-llm` does not OCR scanned documents; they fail closed to manual review until an OCR vendor is chosen.
- Evaluators look up tariff/policy by 4-digit heading; the national 8-digit depth is wired in when the
  authoritative source (and its key depth) is selected (`G18_OWNER_INPUTS.md` B-02 #6).
- Verification endpoint requires `knowledge.manage` (ADMIN); SENIOR_REVIEWER verification is permitted at the
  service level and will be exposed when the permission matrix is extended.
- Staging still runs the G15C image (`9649ec7`), which predates G18: the B-07 wrapper needs a redeploy to a
  `develop` SHA containing G18 before it can run there.

## Readiness flags
READY_FOR_REAL_AI_INTEGRATION: **YES** (configuration + staging acceptance once inputs arrive) ·
READY_FOR_AUTHORITATIVE_DATA_INGESTION: **YES** · READY_FOR_PRODUCTION_INFRA_PROVISIONING: **YES** (option B package) ·
READY_FOR_FULL_PRODUCTION: **NO** (B-01, B-02, B-06 unresolved).

## Next gate
**G18B — Owner inputs applied**: real provider enabled on staging in limited mode + acceptance sample measured;
first authoritative package imported, verified and shadow-compared on staging; production host decision recorded;
B-07 executed. Then **G19 — production provisioning (limited mode)** on the chosen host.
