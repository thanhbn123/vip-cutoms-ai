# STATUS (live)

See `PROJECT_STATUS.md` (gate log), `docs/LOCAL_ACCEPTANCE_REPORT.md` (evidence), `docs/STAGING_READINESS.md` (G13 matrix), `docs/NEXT_SESSION_STAGING.md`.

- Current gate: **G14 — Docker/staging preflight PASS (Docker boot + acceptance from zero); staging deployment awaits owner inputs (B-03/B-04) — DO NOT DEPLOY until approved**
- Gates passed: G00 … G14 (local + Docker scope)
- Branches: `main` = baseline `2afdf6b` (unchanged) · `develop` = release candidate (feature/g00…g13 merged `--no-ff`) · `claude/busy-davinci-9u8bye` = mirror of develop
- Tests: 68 pytest (PostgreSQL) · 3 vitest · 1 Playwright E2E (native + Docker) · HTTP acceptance 17/17 vs Docker · migration head `0010_copilot_meta`
- CI: `CI_EXTERNAL_UNVERIFIED` · LOCAL_VERIFICATION = PASS (`artifacts/test-results/`)

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive) |
| B-03 | Staging host / domain / secrets | BLOCKED_OWNER | No deployment |
| B-04 | Review `develop`; PR to `main` only after staging acceptance | OWNER | main unchanged |
| B-05 | GitHub Actions not observable in the build session | ENV | CI unverified (Docker smoke executed in G14: PASS) |
