# G16 — PRODUCTION REVIEW / RELEASE CANDIDATE FREEZE

Date: 2026-10-09 · Reviewer: local Claude Code implementation controller
Verdict: **PASS_LIMITED_MODE** · `READY_TO_MERGE_MAIN = YES` · `READY_TO_DEPLOY_PRODUCTION = NO`

Nothing was deployed by this gate. `main` was not merged or pushed. No production host exists.

## 1. SHAs

| Ref | SHA |
|---|---|
| Baseline (`develop` at gate start) | `c7fdafdbba139991cd537d5093b4af46d3a61052` |
| `origin/develop` | `c7fdafdbba139991cd537d5093b4af46d3a61052` (identical — local and remote in sync) |
| `main` / `origin/main` | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (unchanged) |
| Accepted staging SHA (G15C) | `9649ec79db189857628ced0b11eaeaf6635fb42c` |
| Deployed on the VPS right now | `9649ec79db189857628ced0b11eaeaf6635fb42c`, working tree clean |

### Drift from the accepted staging SHA: documentation only

`git diff 9649ec7 c7fdafd` touches 5 files: `PROJECT_STATUS.md`, `docs/STATUS.md`,
`docs/G15_DEPLOY_RECORD.md`, `docs/G15_STAGING_ACCEPTANCE_REPORT.md` and the new evidence file
`artifacts/test-results/staging-acceptance.txt`. Verified by comparing git subtree hashes
rather than trusting the diff summary — every code-bearing path is byte-identical:

```
apps         674275d07df1a92e801ff486ba3f9e8677d6d01c   IDENTICAL
packages     8fcf67fc4e811f2ffba10adf5e3c4c060929a724   IDENTICAL
infra        3b009ee0b05dcf8837b934de0244e93fd85a7323   IDENTICAL
scripts      eb4b0fb98def21109883d12e53adad4c45c8b308   IDENTICAL
tests        f45b39fa0f64a9694f0579a52066c52394abff4e   IDENTICAL
prototype    155efd92c7c278d06ae66dc9e9d612daff9cc60f   IDENTICAL
.github      4dd7e219736963eee201f6de8b1371df2b9f2ed1   IDENTICAL
Makefile     dc19d605892d2449db939d39550b09a407cb39de   IDENTICAL
.env.example 1d450f41c5523059c322bbcc40d1d08582abdf17   IDENTICAL
```

**Consequence:** the code running on staging *is* the code under review. Staging did not need
to be redeployed for this gate, and was not.

Independent corroboration: `vite build` in the clean checkout emitted
`dist/assets/index-CVvKd8IQ.js` and `index-BeesP8vI.css` — the same content-hashed filenames
staging serves in its `/` HTML. The deployed frontend bundle is a reproducible build of this
source.

## 2. Fresh G16 evidence (not inherited from G15C)

All of the following was executed during this gate. Where a number matches the G15C report,
it was re-measured, not copied.

### Regression, clean checkout at `c7fdafd`

Isolated clone under a work directory, its own virtualenv (Python 3.13.16), its own
`npm ci` (Node **22.23.3** per project docs — Node 26 breaks jsdom 25), and a dedicated
PostgreSQL 16.15 database `vip_customs_g16`. The live staging database was never touched.

| Check | Result |
|---|---|
| `ruff check app tests` | All checks passed |
| `alembic heads` | `0010_copilot_meta` — exactly one head |
| Schema from zero | `0001` → `0010` applied cleanly |
| `pytest` (apps/api) | **72 passed** |
| `pytest tests` (infra) | **21 passed** (45 after this gate's additions — see §4) |
| `tsc -b` | clean |
| `vitest run` | **3 passed** (2 files) |
| `vite build` | success |
| `scripts/secret_scan.sh` | SECRET SCAN: clean |
| Playwright on the real stack | **2 passed** |
| Owner acceptance flow A–P | **17/17 PASS** |
| Negative / security suite | **18/18 PASS**, 0 server errors in the API log |

The A–P and negative suites were run against a **local** stack, deliberately. Both create
cases and upload documents, and `scripts/staging/acceptance.sh` additionally runs
`compose restart`, `compose down`/`up`, and creates and drops a `restore_test` database. After
inspecting those effects, running them against live staging was rejected: this is a review
gate, the code is identical to what G15C already accepted that way, and a brief staging outage
bought nothing.

### Live staging, read-only

| Check | Result |
|---|---|
| `GET /health` | 200 `{"status":"ok","service":"vip-customs-api","version":"0.1.0"}` |
| `GET /ready` | 200 — `database: ok`, `migrations: 0010_copilot_meta`, `ai_provider: mock`, `environment: staging` |
| `GET /` | 200 (SPA shell) |
| `GET /api/health` | 404 — confirms `/health`, not `/api/health`, is the endpoint |
| TLS | valid Let's Encrypt for `CN=hq.vipgroup.com.vn`, `notAfter=2027-01-07` |
| Security headers | HSTS, CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` |
| Unauthenticated API call | 401 `UNAUTHENTICATED` |
| Containers | 4 up, **0 restarts** each; only `127.0.0.1:18100`/`18543` published |
| Host checkout | `9649ec7`, clean, branch `develop` |
| `sudo -n true` | denied, as expected |
| Disk / memory | 17% of 89G used · 5.6G available |

Read-only throughout: `git` was invoked with per-command `-c safe.directory=...` (no persisted
exception), and no service on the shared host was started, stopped or reconfigured.

### Fail-closed probes

| Probe | Result |
|---|---|
| `APP_SECRET_KEY` absent, `APP_ENV=production` | refuses to start — `APP_SECRET_KEY is required outside development` |
| `APP_SECRET_KEY` < 32 chars | refuses to start — `must be at least 32 characters` |
| `AI_PROVIDER=openai` | `/ready` → **503**, `ai_provider: error: AI provider 'openai' is not available in this build` |
| `OBJECT_STORAGE_PROVIDER=s3` | `RuntimeError: storage provider 's3' not available in this build` |
| `seed_demo.py` with `APP_ENV=production` | `seed_demo refuses to run outside development/test` |

No silent fallback to the mock provider in any case. A half-configured provider cannot serve
traffic, because readiness fails.

## 3. Security / auth / RBAC / tenant isolation / uploads / secrets review

Read every route in `app/api/` plus `core/security.py`, `core/rbac.py`, `api/deps.py`,
`storage/base.py` and `services/documents.py`.

**Authentication.** HMAC-SHA256 signed tokens, PBKDF2-SHA256 (210k iterations) passwords with
`compare_digest` verification, 8-hour TTL. `current_user` re-loads the user from the database
on every request and authorises on `user.role`, not on the token's role claim — so a role
change or deactivation takes effect immediately rather than at token expiry. Login failures do
not distinguish unknown user from wrong password.

**RBAC.** A single server-side permission matrix over 4 roles and 23 permissions. Every route
except `/health`, `/ready` and `/auth/login` carries an auth dependency — verified by
enumerating all of them. Separation of duties holds: Admin has `knowledge.manage` and
`user.manage` but no customs-decision permission (asserted by a test), critical waivers require
Senior Reviewer, and a user cannot approve their own proposal.

**Tenant isolation** is enforced in SQL, not in the UI. Every by-id loader filters on
`tenant_id` — cases, documents, drafts, issues, goods items, memory — and unknown ids return
404 rather than 403, so ids cannot be enumerated. 10 cross-tenant assertions across 5 test
files use two real tenants.

**Uploads.** Document type and extension allow-lists, a bounded read (`max_upload_bytes + 1`,
so an oversize body is rejected at 413 without being buffered whole), empty-file rejection,
server-generated storage keys (`tenant/case/uuid.ext`), SHA-256 duplicate detection, and path
containment in `LocalFileStorage._path` (a `../` or absolute key raises `ValueError`).
Downloads are tenant-scoped and served `attachment` with `Cache-Control: private, no-store`.
`safe_filename` strips path separators and non-printable characters, so CR/LF cannot reach a
response header.

**Secrets.** No secret in the repository (`secret_scan.sh` clean, runs in `make verify` and
CI); `.env*` git-ignored except `*.env.example`; `APP_SECRET_KEY` mandatory outside
development; database never published outside the compose network.

### Findings

No high or critical finding. Three low-severity hardening items, none exploitable as shipped:

1. **`Content-Disposition` filename is not quote-escaped** (`app/api/documents.py`, and the
   same pattern for drafts). A filename containing `"` corrupts the header's parameter
   parsing. Not a header-injection risk, because `safe_filename` removes non-printable
   characters so CR/LF cannot survive; the effect is a mangled download filename. Fix:
   strip `"` and `\` in `safe_filename`.
2. **Download responses echo the client-supplied `content_type`** stored at upload. Mitigated
   by `attachment` disposition and by the proxy's `X-Content-Type-Options: nosniff`, but the
   API does not set `nosniff` itself, so the protection depends on the proxy staying in the
   request path.
3. **`current_user` parses `payload["sub"]` outside its `try`.** A malformed `sub` would raise
   `ValueError` → 500 instead of 401. Not reachable by an attacker, since the token is
   HMAC-verified first and only the server mints payloads.

Two observations rather than defects:

- **No login rate limiting.** PBKDF2 at 210k iterations makes guessing expensive, but nothing
  throttles or locks out. Out of scope by prior decision; must be added at the edge before
  internet-facing production use.
- **Knowledge datasets are global, not tenant-scoped** (deliberate, documented in the model).
  A tenant Admin can deactivate a dataset for all tenants. Fails closed, so no data
  corruption; needs a decision before a second customer is onboarded.

Test-coverage gap: cross-tenant isolation is tested for cases, documents, copilot, memory,
review queue and dashboard, but not for drafts, issues, assessments or goods items. The code
filters `tenant_id` in all of those paths (confirmed by reading); the assertions are simply
absent.

## 4. Backup and monitoring readiness

**Before this gate:** backup was documented as commands plus the word "nightly", with no
scheduler anywhere in the repository; monitoring did not exist beyond the two endpoints.

**Closed by this gate** (prepared, not installed — installing a systemd unit needs root, which
the deploy user deliberately lacks):

- `scripts/production/backup.sh` — `pg_dump -Fc` **and** the uploads volume (the database alone
  restores cases whose documents 404), SHA-256 per artifact, append-only `MANIFEST.txt`
  recording sizes/checksums/deployed SHA, integer-validated retention pruning, non-zero exit on
  an empty dump, and no path that prints the env file.
- `infra/production/vip-customs-backup.service` / `.timer` — nightly 02:30 UTC,
  `Persistent=true` so a missed run still happens. Both pass `systemd-analyze verify` on the
  real host (checked in a temp directory, nothing installed).
- `infra/production/docker-compose.production.yml` — log rotation (10 MiB × 5) on every
  service, a `web` healthcheck staging lacks, memory limits, `restart: always`, and a distinct
  compose project name so a production stack can never reuse staging volumes.
- `docs/PRODUCTION_RUNBOOK.md` §5 — the exact monitoring signals and alert thresholds,
  including "alert on `/ready`, not `/health`" and treating `chain_valid: false` as a security
  incident.

**Still open** (operator/owner actions, stated plainly in `docs/PRODUCTION_READINESS.md` §2.2):
off-host backup replication, a restore-drill cadence, and choosing a monitoring tool.

The production compose overlay was validated with real `docker compose config` on the VPS in a
temporary directory, then removed — merged output confirmed correct restart policies, logging,
limits, the `web` healthcheck, `migrate` keeping `restart: "no"`, and only the proxy publishing
ports. It was also confirmed that the overlay **alone** is rejected
(`service "postgres" has neither an image nor a build context specified`), which is why the
runbook always passes both files. No compose project was created and no container was started.

**30 new contract tests** (`tests/test_production_infra.py`) lock these invariants down: no
filled secret in the template, only implemented provider names, no key implying a
customs integration, no `IMAGE_TAG=latest`, overlay service names matching the staging compose,
`migrate` never given a restart policy, log bounds on every long-running service, every
artifact actually tracked by git, and the backup script failing loudly without config.
Root infra suite: **21 → 51 tests**.

One of those tests immediately earned its place. The first final-verify run in the clean
checkout failed 7 tests because `infra/production/.env.production.example` **was not in the
commit at all**: `.gitignore` line 2 (`.env.*`) matched it, and the existing negation
`!*.env.example` does not — `.env.production.example` does not end in `.env.example`. The
template was present locally, so every test passed in the working tree; only a clean checkout
revealed it. Fixed by adding `!.env.production.example` to `.gitignore`, and guarded by
`test_production_artifacts_are_tracked_by_git`, which uses `git check-ignore --no-index`
because git skips exclusion rules for files already in the index (without `--no-index` the
assertion would vacuously pass on any tracked file). Verified to fail when the negation is
removed and to pass when it is restored.

## 5. Owner decisions — all four remain OPEN

B-01 real OCR/LLM provider · B-02 authoritative tariff/FTA/policy data · B-06 shared-Caddy
dependency · B-07 staging demo users. Reviewed in depth with options and a recommendation
each in `docs/PRODUCTION_READINESS.md` §4. None was decided or pre-empted here; no provider
was chosen, no data source selected, no demo user deleted, and the shared proxy was not
touched.

B-02 is the binding constraint on `PASS_FULL_MODE`: every tariff rate, FTA eligibility and
policy requirement in the system is demo fixture data, labelled
`DEMO — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING`.

## 6. Mode definitions as applied here

- **PASS_LIMITED_MODE (achieved).** Internal demo/drafting use with the mock provider and demo
  knowledge data. Produces versioned, watermarked internal drafts. **Not** for preparing or
  submitting a real customs filing.
- **PASS_FULL_MODE (not achieved).** Requires B-01 and B-02 resolved with verified data, plus
  the §2.2 engineering prerequisites (automated and off-host backup, monitoring, login rate
  limiting, and a durability decision for document storage).

## 7. Known limitations

Mock AI provider · demo knowledge datasets · local-directory object storage · token auth
without OIDC or revocation · no login rate limiting · no monitoring or alerting installed ·
backup automation prepared but not installed · no off-host backup · staging TLS depends on a
shared proxy (B-06) · demo users still present on staging (B-07) · no customs-system adapter of
any kind, by design (product rule #7) · CI remains `CI_EXTERNAL_UNVERIFIED` (GitHub Actions is
not observable from this session; full local verification is the evidence).

## 8. Next step

Owner reviews this report and `docs/PRODUCTION_READINESS.md`, then merges the release-candidate
PR `release/g16-rc1` → `develop` → `main`. Merging freezes the release candidate; it deploys
nothing. Production deployment and any customs-system integration remain separate, explicitly
gated decisions.
