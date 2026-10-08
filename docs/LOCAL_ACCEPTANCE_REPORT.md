# LOCAL ACCEPTANCE REPORT — 2026-10-08

Branch under test: `develop` (feature/g00 … g13 merged `--no-ff`). Raw outputs: `artifacts/test-results/*.txt` (trimmed real output, exit codes included).
Environment: cloud build container, Python 3.12.3, Node 22.22.0, PostgreSQL 16.15 (native). **No Docker daemon available.**

| Check | Result | Evidence |
|---|---|---|
| Backend unit + integration (pytest, PostgreSQL, schema from zero) | **PASS — 66 passed** | `backend-pytest.txt` |
| Owner 16-step acceptance via API | **PASS** (`tests/test_acceptance_mvp.py`) | included in pytest |
| Frontend unit (vitest) | **PASS — 2 files / 3 tests** | `frontend-vitest.txt` |
| Typecheck (tsc -b) | **PASS** | `typecheck.txt` |
| Lint (ruff) | **PASS** | `lint.txt` |
| Web build (vite) | **PASS** (189.82 kB js / 5.80 kB css gzip 60 kB) | `build.txt` |
| Migration from zero → head, downgrade 0010→0008 → upgrade | **PASS — single head `0010_copilot_meta`** | `migration-test.txt` |
| Browser E2E on real stack (Playwright/Chromium: login → V12 nav → item 3 BLOCKED 64% → Copilot → release gate BLOCKED → declaration) | **PASS — 1 passed** | `integration-e2e.txt` |
| API smoke (/health, /ready, login, cases, 401 unauth) | **PASS** | `api-smoke.txt` |
| Secret scan | **PASS — clean** | `secret-scan.txt` |
| Clean checkout (fresh clone of develop, fresh venv, `npm ci`, fresh DB, migrate, seed, pytest 66, tsc, vitest, build) | **PASS** | `clean-checkout.txt` |
| Docker Compose from zero | **NOT_RUN** — no daemon in this environment; compose + CI YAML parse OK, Dockerfiles present | `docker-smoke.txt` |
| GitHub Actions | **CI_EXTERNAL_UNVERIFIED** — workflow committed, not observable from the session | — |

## V12 functional parity check (manual, via the E2E and the live smoke)
Sidebar (9 entries, V12 order) · dashboard metrics/flow/critical issues · Document Center with parse % and match badges · lineage ·
Smart Declaration sections with confidence/source/status · Goods table with `8537.xx.xx · 64% · BLOCKED`, `8413 · 87% · REVIEW`, `3917 · 95%` ·
Knowledge Hub with versioned DEMO datasets · Copilot with sources/reasoning/confidence/recommended actions/requires-review · Reviewer queue, issue
resolve/waive, release gate BLOCKED with "Xuất DRAFT" enabled and "Phát hành" disabled · Historical Learning "Reference / Do not auto-copy" · Quản trị.
**Result: PASS (functional parity; not pixel-perfect by design).**

## Defects found and fixed during acceptance
- Evaluators were registered as a router import side effect → seed/script path produced no goods items (fixed: `evaluators.ensure_registered()`, regression test).
- `classification_decisions.decision` too narrow for `REQUEST_INFO` (migration 0009).
- Login labels not associated with inputs (a11y; caught by Playwright).
- vitest collected the Playwright spec (one failing file hidden behind a "Tests passed" line) → `e2e/**` excluded; evidence script now uses `pipefail`.
- `copilot_messages.meta` migration lacked a server default for existing rows (0010 fixed before merge).

## Open bugs
Critical: 0 · High: 0 · Known limitations: see `docs/STAGING_READINESS.md`.
