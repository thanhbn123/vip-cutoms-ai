# STATUS (live)

See `PROJECT_STATUS.md` (gate log), `docs/G16_PRODUCTION_REVIEW.md` (**current gate**),
`docs/PRODUCTION_READINESS.md` (production gap analysis + owner decision briefs),
`docs/PRODUCTION_RUNBOOK.md`, `docs/G15_STAGING_ACCEPTANCE_REPORT.md` (real staging evidence),
`docs/G15_DEPLOY_RECORD.md` (deployed SHA + rollback), `docs/STAGING_ROLLBACK.md`.

- Current gate: **G16 — production review / release-candidate freeze: PASS_LIMITED_MODE.**
  `READY_TO_MERGE_MAIN = YES` · `READY_TO_DEPLOY_PRODUCTION = NO` (owner decision + the
  prerequisites in `docs/PRODUCTION_READINESS.md` §2.2). **Nothing deployed by this gate.**
  `PASS_FULL_MODE` is blocked on B-01 and B-02 — the system's tariff/FTA/policy data is demo
  fixture data, so it must not be used to prepare a real customs filing.
- Gates passed: G00 … G14 (local + Docker scope) · G15C (real staging) · **G16 (production review)**
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
  release candidate `release/g16-rc1`
- G16 re-verified the staging-accepted code in a clean checkout: the only drift between
  `9649ec7` (accepted) and `c7fdafd` is documentation — every code subtree hash is identical,
  so staging runs exactly the reviewed code and was not redeployed
- Tests: **72 pytest** (PostgreSQL) · **51 infra pytest** (no DB/Docker; 21 → 51 in G16) ·
  3 vitest · 2 Playwright E2E · HTTP acceptance 17/17 · negative/security 18/18 ·
  `VERIFY: ALL CHECKS PASSED`
- CI: `CI_EXTERNAL_UNVERIFIED` · LOCAL_VERIFICATION = PASS (`artifacts/test-results/`)
- Local web unit tests need **Node 22** (CI's version); Node 26 breaks jsdom 25
  (`localStorage … undefined`) — toolchain mismatch, not a product defect

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive) |
| B-03 | ~~Staging host / domain / secrets~~ | **RESOLVED (G15C)** | Deployed to `160.22.170.20` / `hq.vipgroup.com.vn` |
| B-04 | Review `develop`; PR to `main` only after production review | OWNER | main unchanged; G16 production review complete → RC PR open for owner merge |
| B-05 | GitHub Actions not observable in the build session | ENV | CI unverified (real staging acceptance executed in G15C: PASS) |
| B-06 | Edge TLS for `hq.vipgroup.com.vn` is terminated by the host's **shared** Caddy, which also serves unrelated projects | OWNER | Availability coupled to a shared proxy; the stack's own `acme` mode cannot be used because it needs ports 80/443. G16 options + recommendation: `docs/PRODUCTION_READINESS.md` §4 |
| B-07 | Demo users remain on staging after acceptance | OWNER | `docs/STAGING_SECRETS.md` says to delete them once acceptance is signed off. G16 recommends deactivating (`is_active=false`) rather than deleting, to preserve audit actor references |
