# STATUS (live)

See `PROJECT_STATUS.md` (gate log), `docs/LOCAL_ACCEPTANCE_REPORT.md` (evidence), `docs/STAGING_READINESS.md` (G13 matrix), `docs/NEXT_SESSION_STAGING.md`.

- Current gate: **G15B — real staging deployment BLOCKED_ENV: host/domain now known (160.22.170.20 / hq.vipgroup.com.vn, DNS OK) but the build session cannot open SSH (tcp/22 blocked by egress policy) and has no SSH credential → nothing deployed. Operator runbook: `docs/G15B_OPERATOR_RUNBOOK.md`. Candidate SHA `bfc82cb45cf40453a14208a43fef4660fcc1f067`.**
- Gates passed: G00 … G14 (local + Docker scope); G15 prepared, awaiting owner inputs
- Branches: `main` = baseline `2afdf6b` (unchanged) · `develop` = release candidate (feature/g00…g13 merged `--no-ff`) · `claude/busy-davinci-9u8bye` = mirror of develop
- Tests: 68 pytest (PostgreSQL) · 3 vitest · 1 Playwright E2E (native + Docker) · HTTP acceptance 17/17 vs Docker · migration head `0010_copilot_meta`
- CI: `CI_EXTERNAL_UNVERIFIED` · LOCAL_VERIFICATION = PASS (`artifacts/test-results/`)

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive) |
| B-03 | SSH path to 160.22.170.20 from the deploying machine (egress policy + credential) | ENV / OWNER | No deployment from the build session; runbook ready for an operator with SSH |
| B-04 | Review `develop`; PR to `main` only after staging acceptance | OWNER | main unchanged |
| B-05 | GitHub Actions not observable in the build session | ENV | CI unverified (Docker smoke executed in G14: PASS) |
