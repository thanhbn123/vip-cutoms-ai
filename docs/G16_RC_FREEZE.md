# G16 — RELEASE CANDIDATE FREEZE · 2026-10-09

## Verdict
**RC frozen for owner review of `develop → main` (PR #2). PASS_LIMITED_MODE only. `main` not merged. Production not deployed.**

| | |
|---|---|
| **RC SHA** | **`origin/develop` after this freeze commit — the exact 40-char SHA is printed in the G16 final report and in PR #2.** A document cannot contain its own commit hash; verify with `git rev-parse origin/develop` and `git log -1 --format=%H -- docs/G16_RC_FREEZE.md` (they match). |
| Code-verified SHA | `d21fd7756a9a148a96dd92711d97966e4e505b86` — merge of PR #1 into `develop`. The freeze commit changes **documentation only**; runtime subtrees (`apps`, `packages`, `infra`, `.github`, `Makefile`, `.env.example`, `prototype`) are byte-identical to `d21fd77`; the only code delta is the clean-clone fix to `scripts/e2e.sh` + its test (`ed7a4f1`, see below). |
| PR #1 | `release/g16-rc1` → `develop`, head `4591b6285b585bb93122ac332f99a99b7e417ee4` (verified head `52d8fe17…` + one evidence-only commit), **merged** `--no-ff` as `d21fd77` |
| PRE-DEVELOP SHA | `c7fdafdbba139991cd537d5093b4af46d3a61052` |
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` — unchanged |
| Staging-accepted SHA (G15C) | `9649ec79db189857628ced0b11eaeaf6635fb42c`, deployed on `160.22.170.20` / `https://hq.vipgroup.com.vn` |
| Staging redeploy for this RC | **NOT NEEDED** — `apps/`, `infra/staging/`, `scripts/staging/`, `Makefile`, `.env.example` identical between `9649ec7` and the RC; PR #1 added `infra/production/*`, `scripts/production/backup.sh`, root tests, docs and the `infra` CI job only (no runtime code or staging config). G15C acceptance (17/17 · 18/18 · Playwright 2/2 · restart · backup/restore · TLS valid) therefore remains valid for the RC's runtime. |

## PR #1 review (G16 scope)
15 files (+ my CI commit + evidence): `infra/production/{.env.production.example, docker-compose.production.yml (overlay), vip-customs-backup.{service,timer}}`,
`scripts/production/backup.sh` (umask 077, private artifacts, one-off reader, fail-closed), `tests/test_production_infra.py` (49 tests → root suite 70),
`docs/{G16_PRODUCTION_REVIEW, PRODUCTION_READINESS, PRODUCTION_RUNBOOK, RUNBOOK, STATUS, DECISIONS}.md`, `PROJECT_STATUS.md`, `.gitignore` (negation for the
production env template). Scope confirmed G16-only; no `apps/` change; no secrets (env template holds placeholders and generation commands only).
Gap closed in this gate: the root `tests/` suite was not run by CI → added job `infra` (`pip install pytest && python -m pytest tests -q`).

## Verification on the exact PR head `52d8fe1` (this gate, fresh execution)
| Check | Result |
|---|---|
| GitHub Actions | **4/4 success** — `api`, `web`, `infra` (70 tests), `secrets` (run 37906023466) |
| backend pytest (PostgreSQL, schema from zero) | **72 passed** |
| infra pytest (root `tests/`) | **70 passed** |
| vitest (Node 22.22.0) | **3 passed / 2 files** |
| Playwright (native stack) | **2 passed** |
| Playwright (Docker stack) | **2 passed** |
| tsc · ruff · vite build · secret scan | PASS |
| migration from zero → `0010_copilot_meta`, single head, downgrade/upgrade | PASS |
| Docker acceptance dry-run | A–P **17/17** · negative **18/18** · restart + down/up persistence (cases 17→17, uploads 53) · backup 342,640 B + restore (cases 17, audit 998) · logs 0 errors / 0 secrets |

## Clean checkout of `d21fd77` from zero
Fresh `git clone` of `origin/develop` at `d21fd7756a9a148a96dd92711d97966e4e505b86` into an empty directory, Node v22.22.0, Python 3.12, empty PostgreSQL database `vip_customs_rc`. Everything below was executed from the clone, not from the working checkout; evidence in the clone's `artifacts/test-results/clean-checkout.txt`, `docker-smoke.txt`, `docker-acceptance.txt`.

| Step | Result |
|---|---|
| `pip install` (api) | OK |
| `alembic upgrade head` from empty DB | `0010_copilot_meta (head)`, heads=1 |
| seed demo tenant + demo case | tenant DEMO, 4 datasets (HS_RULES, TARIFF, FTA, POLICY), case `VIP-HQ-261008-001` → 4 docs parsed, status **BLOCKED** (fail-closed) |
| ruff | OK |
| backend pytest | **72 passed** |
| infra pytest (root `tests/`) | **70 passed** |
| `npm ci` | 194 packages |
| tsc | OK |
| vitest | **3 passed** (2 files) |
| vite build | OK |
| Playwright, native stack | **2 passed** — *after* the clean-clone fix below; the unfixed `scripts/e2e.sh` aborted silently before Playwright in a fresh clone |
| Docker from clean clone: build, boot from zero, `/health`, `/ready` | 200 / 200 (`database ok`, migrations `0010_copilot_meta`, `ai_provider mock`), web 200, 21 tables on fresh volume, 0 secret leaks in logs, 0 restarts |
| Docker acceptance A–P | **17/17 PASS**, 0 restarts after flow, 11 uploaded documents in volume |
| Playwright, Docker stack | **2 passed** |

### Clean-clone finding and fix (only code delta after `d21fd77`)
`scripts/e2e.sh` redirected API/web logs into the gitignored `local-data/` directory, which does not exist in a fresh clone; under `set -e` the script exited right after seeding and Playwright never ran. Fix: `mkdir -p "$ROOT/local-data"` before the first redirection, plus contract test `test_e2e_script_creates_its_log_directory_before_use` (root infra suite → **71 tests**). Commit `9446db2` on `feature/g16-e2e-clean-clone-fix`, merged `--no-ff` into `develop` as `ed7a4f17dace81b69ecf83a33fbac60788ea1bba`. `git diff d21fd77 ed7a4f1 -- apps infra packages Makefile .env.example .github` is **empty**: no runtime, image, migration or deployment change, so every runtime result above and the staging status below still apply.

## Staging status (read-only, this session)
Egress from the build session cannot reach `hq.vipgroup.com.vn` (CONNECT via the environment proxy returns no response → `000`), so live health was **not re-probed from here**. Deployed SHA on the VPS per G15C record: `9649ec7` (containers healthy, 0 restarts, Let's Encrypt cert valid to 2027-01-07, behind the host's shared Caddy, `AI_PROVIDER=mock`). Runtime of the RC is identical to that SHA (see table above). An operator can re-check in seconds: `curl -fsS https://hq.vipgroup.com.vn/health && curl -fsS https://hq.vipgroup.com.vn/ready`.

## Migration
Head `0010_copilot_meta`, single head; applied from an empty database in CI, in the clean checkout and in Docker; downgrade paths exist for every revision.

## Security status
Secret scan clean (repo + PR tree); no `.env`/key/dump tracked; RBAC/tenant/upload/traversal tests in the suites (negative suite 18/18); fail-closed boot without `APP_SECRET_KEY`; unknown AI/storage providers refuse. Low (non-blocking) findings recorded in `docs/G16_PRODUCTION_REVIEW.md` §3: Content-Disposition quoting, `nosniff` at the API layer, 500-vs-401 on a malformed signed token payload; no login rate limiting. None is a critical or high bug.

## Rollback status
Staging: `docs/STAGING_ROLLBACK.md` (images recorded by `deploy.sh`, pre-deploy `pg_dump`). Production (prepared, not deployed): `docs/PRODUCTION_RUNBOOK.md` §3–4 — pinned `IMAGE_TAG` rollback, `scripts/production/backup.sh` (DB + uploads, checksums, manifest, private perms), quiesced procedure for a coherent pair, restore-to-temporary-DB verification. Rollback is documented and structurally tested (19 execution tests); it has not been drilled on a production host because none exists.

## Production limitations (binding)
- **B-01 — Real OCR/LLM not integrated.** `AI_PROVIDER=mock` is the only implemented provider (parser, HS reasoning, Copilot). Any other value fails closed (`/ready` 503). Real-document extraction quality is unknown.
- **B-02 — Tariff / FTA / policy datasets are demo and NON-AUTHORITATIVE.** Every rate, FTA eligibility and policy requirement shown is fixture data labelled "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING". **If the system is intended for real customs filings, B-01 and B-02 are hard blockers for FULL PRODUCTION.**
- **B-06 — Production host / domain / shared-proxy decision is owner-controlled.** Staging sits behind a shared Caddy on a VPS with unrelated services; production addressing/TLS termination has not been decided.
- **B-07 — Staging demo users must be disabled/deleted after acceptance** (`operator|reviewer|senior|admin@demo.local` exist on the TLS-exposed staging host).

## Production operations requirements (not yet in place)
- **Off-host backup**: `backup.sh` writes to `BACKUP_DIR` on the host only; copies must be shipped off-host (encrypted) with retention ≥ 14 days — owner to provide the target.
- **Restore drill**: restore into a temporary database was exercised on staging and in Docker; a full drill on the production host (DB + uploads volume, quiesced pair) must be run before go-live and after every schema change.
- **Monitoring / alerting**: no monitoring exists. Minimum: `/ready` probe with alerting, container restart-count alert, disk-usage alert for `BACKUP_DIR`/volumes, log shipping (signals listed in `docs/PRODUCTION_RUNBOOK.md` §5).
- **Production deploy permissions**: deploy user without sudo (systemd units need root once); who may run `deploy.sh`/`backup.sh`, where `infra/production/.env` is held, and who approves `develop → main` are owner decisions.

## Production mode classification
**PASS_LIMITED_MODE** — internal drafting/demo use with mock providers and demo knowledge. **PASS_FULL_MODE = NO** until B-01 and B-02 are resolved and verified.
