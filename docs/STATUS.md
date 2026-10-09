# STATUS (live)

See `PROJECT_STATUS.md` (gate log), `docs/G16_PRODUCTION_REVIEW.md` (**current gate**),
`docs/PRODUCTION_READINESS.md` (production gap analysis + owner decision briefs),
`docs/PRODUCTION_RUNBOOK.md`, `docs/G15_STAGING_ACCEPTANCE_REPORT.md` (real staging evidence),
`docs/G15_DEPLOY_RECORD.md` (deployed SHA + rollback), `docs/STAGING_ROLLBACK.md`.

- Current gate: **G18E — hardening of G18D after review (throttle dimensions pair/e-mail/ip with bounded memory, lock-time counting, audited lockouts; fail-closed Knowledge badge; admin panel notes) + clean-checkout verification of `f2989b1` from zero. Preceded by G18D — API-layer login throttling (429 + Retry-After, metric) and the Knowledge Hub steward UI (provenance, verify, supersede, JSON import) — `docs/G18D_LOGIN_THROTTLING_AND_KNOWLEDGE_UI.md`. Preceded by G18C — code-review remediation (`docs/G18C_REVIEW_REMEDIATION.md`): 20 findings on the G18 diff disposed, plus a second-pass review of the remediation (14 follow-ups closed: unreadable new versions clear old values, promoted severities apply to open issues, human-closed issues reopen when the condition changes, field clearing audited, numeric CSV, UI hides resolve on system criticals, compare-aware approval) — reviewers can no longer resolve system-detected CRITICAL issues (Senior waive with evidence only) and such issues reopen when the condition returns; stale AI fields cleared on re-upload; as-is approvals keep AI lineage; decisions after export reopen the case; unreadable documents block; imported packages validated; preferential rate from the reviewer's decision; candidate/heading check; REJECT clears the code; CSV formula-safe; `/metrics` closed by default (`METRICS_ALLOW_FROM`); `/docs` hidden outside development; non-UUID token → 401; N+1 removed; web client tolerant of proxy HTML. 1 documented limitation (cross-tenant e-mail oracle, D-012). Preceded by G18B — hardening follow-ups closed (`docs/G18B_HARDENING.md`: 401 on malformed signed tokens, API-layer security headers, RFC 5987 download headers, longest-prefix 8-digit tariff/policy lookups, `knowledge.verify` for SENIOR_REVIEWER, persistent AI cost ledger `0012_ai_usage_events`, `/metrics` private-only + api health routing in Caddy). Preceded by G18A — full-production preparation (`docs/G18A_REPORT.md`): explicit runtime modes `APP_MODE=demo|limited|full` with fail-closed FULL startup/readiness, four AI capability boundaries + vendor-neutral `http-llm` adapter, authoritative-data governance (migration `0011_dataset_provenance`, verify/supersede/conflict → reviewer), B-07 deactivation tooling, off-host backup + monitoring + access + secrets designs, exact owner inputs (`docs/G18_OWNER_INPUTS.md`). `main` = `4a2acb9` unchanged; production NOT deployed. B-01/B-02/B-06 BLOCKED_OWNER; B-07 mechanism READY, staging execution pending operator.**
  `READY_TO_MERGE_MAIN = NO` · `READY_TO_DEPLOY_PRODUCTION = NO`. Merging to `main` waits on the
  G16 additions being reviewed into `develop` (draft PR #1) and `develop` being verified and
  frozen; the owner's limited-mode review is also open. **Nothing deployed by this gate.**
  `PASS_FULL_MODE` is blocked on B-01 and B-02 — the system's tariff/FTA/policy data is demo
  fixture data, so it must not be used to prepare a real customs filing.
- Gates passed: G00 … G14 (local + Docker scope) · G15C (real staging) · **G16 (production review + RC closeout)**
- Staging: deploy SHA `9649ec79db189857628ced0b11eaeaf6635fb42c` (code-identical to
  `origin/develop` `c7fdafd`; the newer commits are documentation only) · migration head
  `0010_copilot_meta` (single) · containers healthy, 0 restarts · TLS valid (Let's Encrypt,
  to 2027-01-07) · `AI_PROVIDER=mock` · demo knowledge only
- Staging acceptance (**G15C evidence**): **17/17** HTTP flow A–P · **18/18** negative/security ·
  **2/2** remote Playwright · restart + down/up persistence · backup + restore-to-temp-DB ·
  logs clean (0 5xx, 0 secret hits)
- G16 re-ran A–P **17/17**, negative/security **18/18** and Playwright **2/2** fresh against a
  local stack on an isolated database; live staging was checked read-only only
- Branches: `main` = baseline `2afdf6b` (**unchanged, never pushed**) · `develop` = `c7fdafd` ·
  release candidate `release/g16-rc1` (draft PR #1 → `develop`, not merged)
- G16 re-verified the staging-accepted code in a clean checkout: the only drift between
  `9649ec7` (accepted) and `c7fdafd` is documentation — every code subtree hash is identical,
  so staging runs exactly the reviewed code and was not redeployed
- Tests (RC, fresh execution 2026-10-09 on PR head `52d8fe1` and clean checkout of `d21fd77`): **72 api pytest** · **71 infra pytest** (now also in CI job `infra`) ·
  3 vitest · 2 Playwright E2E · HTTP acceptance 17/17 · negative/security 18/18 ·
  `VERIFY: ALL CHECKS PASSED`
- CI: **green 4/4** (`api`, `web`, `infra`, `secrets`) — GitHub Actions run `37906023466` on PR #1 head `52d8fe1`; re-run on `develop` after merge.
  jobs `api`/`web`/`secrets` all success (this supersedes the old `CI_EXTERNAL_UNVERIFIED`;
  D-004 no longer holds). Caveat: `ci.yml`'s `api` job runs only `apps/api/tests`, so the root
  `tests/` infra suite is not covered by CI · LOCAL_VERIFICATION = PASS (`artifacts/test-results/`)
- Local web unit tests need **Node 22** (CI's version); Node 26 breaks jsdom 25
  (`localStorage … undefined`) — toolchain mismatch, not a product defect

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only. **G18A:** provider boundaries + `http-llm` adapter ready; vendor/credentials/DPA/acceptance sample are owner inputs (`docs/G18_OWNER_INPUTS.md`) |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive). **G18A:** provenance schema, import/verify/supersede workflow, full-mode authoritative-only selection, conflict → reviewer; source selection is an owner input |
| B-03 | ~~Staging host / domain / secrets~~ | **RESOLVED (G15C)** | Deployed to `160.22.170.20` / `hq.vipgroup.com.vn` |
| B-04 | ~~Review `develop`; PR to `main` only after production review~~ | **RESOLVED (G17)** | Owner approved PR #2; `main` = `4a2acb9` (limited mode) |
| B-05 | GitHub Actions not observable in the build session | ENV | CI unverified (real staging acceptance executed in G15C: PASS) |
| B-06 | Edge TLS for `hq.vipgroup.com.vn` is terminated by the host's **shared** Caddy, which also serves unrelated projects | OWNER | Availability coupled to a shared proxy; the stack's own `acme` mode cannot be used because it needs ports 80/443. G16 options + recommendation: `docs/PRODUCTION_READINESS.md` §4. **G18A:** decision package `docs/G18_PRODUCTION_INFRA_OPTIONS.md` — recommended option B (dedicated production VPS, stack-owned Caddy) |
| B-07 | Demo users remain on staging after acceptance | **BLOCKED (operator execution pending)** | `docs/STAGING_SECRETS.md` says to delete them once acceptance is signed off. G16 recommends deactivating (`is_active=false`) rather than deleting, to preserve audit actor references. **G18A:** deactivation script + wrapper implemented and tested (`docs/G18_B07_DEMO_USERS.md`); staging unreachable from the build session, run the runbook with the deploy key |
