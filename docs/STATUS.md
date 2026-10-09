# STATUS (live)

See `PROJECT_STATUS.md` (gate log), `docs/G15_STAGING_ACCEPTANCE_REPORT.md` (**real staging
evidence**), `docs/G15_DEPLOY_RECORD.md` (deployed SHA + rollback),
`docs/LOCAL_ACCEPTANCE_REPORT.md`, `docs/STAGING_ROLLBACK.md`.

- Current gate: **G15C — REAL staging deployment and acceptance: PASS.** Deployed to
  `160.22.170.20` at `https://hq.vipgroup.com.vn`, behind the host's shared Caddy proxy.
  `READY_FOR_PRODUCTION_REVIEW = YES`. **Production not deployed; `main` not merged.**
- Gates passed: G00 … G14 (local + Docker scope) · **G15C (real staging)**
- Staging: deploy SHA `9649ec79db189857628ced0b11eaeaf6635fb42c` (= `origin/develop`) ·
  migration head `0010_copilot_meta` (single) · containers healthy, 0 restarts ·
  TLS valid (Let's Encrypt, to 2027-01-07) · `AI_PROVIDER=mock` · demo knowledge only
- Staging acceptance: **17/17** HTTP flow A–P · **18/18** negative/security ·
  **2/2** remote Playwright · restart + down/up persistence · backup + restore-to-temp-DB ·
  logs clean (0 5xx, 0 secret hits)
- Branches: `main` = baseline `2afdf6b` (**unchanged**) · `develop` = `9649ec7` (staging-accepted)
- Tests: **72 pytest** (PostgreSQL) · **21 infra pytest** (no DB/Docker) · 3 vitest ·
  2 Playwright E2E · HTTP acceptance 17/17 · `VERIFY: ALL CHECKS PASSED`
- CI: `CI_EXTERNAL_UNVERIFIED` · LOCAL_VERIFICATION = PASS (`artifacts/test-results/`)
- Local web unit tests need **Node 22** (CI's version); Node 26 breaks jsdom 25
  (`localStorage … undefined`) — toolchain mismatch, not a product defect

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive) |
| B-03 | ~~Staging host / domain / secrets~~ | **RESOLVED (G15C)** | Deployed to `160.22.170.20` / `hq.vipgroup.com.vn` |
| B-04 | Review `develop`; PR to `main` only after production review | OWNER | main unchanged; staging acceptance now PASS |
| B-05 | GitHub Actions not observable in the build session | ENV | CI unverified (real staging acceptance executed in G15C: PASS) |
| B-06 | Edge TLS for `hq.vipgroup.com.vn` is terminated by the host's **shared** Caddy, which also serves unrelated projects | OWNER | Availability coupled to a shared proxy; the stack's own `acme` mode cannot be used because it needs ports 80/443 |
| B-07 | Demo users remain on staging after acceptance | OWNER | `docs/STAGING_SECRETS.md` says to delete them once acceptance is signed off |
