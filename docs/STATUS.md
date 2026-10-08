# STATUS (live)

See `PROJECT_STATUS.md` for the gate log and `docs/STAGING_READINESS.md` for the G13 matrix.

- Current gate: **G13 — Staging readiness (PREPARED; execution BLOCKED_OWNER)**
- Gates passed: G00, G01, G02, G03, G04, G05, G06, G07, G08, G09, G10, G11, G12
- Branch: `claude/busy-davinci-9u8bye` · baseline main: `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0`
- Tests: 64 pytest (PostgreSQL) + 3 vitest · migration head `0008_copilot_memory`
- CI: `CI_EXTERNAL_UNVERIFIED` (workflow committed; not observable from the build session; full local verification via `scripts/verify.sh`)

## Blockers

| ID | Blocker | Type | Impact |
|---|---|---|---|
| B-01 | Real OCR/LLM provider credentials | BLOCKED_OWNER | Mock provider only |
| B-02 | Authoritative tariff / FTA / policy data source | BLOCKED_OWNER | Demo datasets only (labelled, fail-closed when inactive) |
| B-03 | Staging host / domain / secrets | BLOCKED_OWNER | No deployment |
| B-04 | `develop` branch + PR review/merge | OWNER | Session could push only to `claude/busy-davinci-9u8bye` |
| B-05 | Docker daemon + GitHub Actions not observable in session | ENV | Compose YAML validated, not executed; CI unverified |
