# PRODUCTION READINESS (G16)

Reviewed commit: `develop` **c7fdafdbba139991cd537d5093b4af46d3a61052**
Code tree reviewed is byte-identical to the accepted staging SHA `9649ec79db189857628ced0b11eaeaf6635fb42c`
(see `docs/G16_PRODUCTION_REVIEW.md` for the subtree-hash proof).

## Verdict

| | |
|---|---|
| **PASS_LIMITED_MODE** | **YES** — internal drafting/demo use, mock AI provider, demo knowledge datasets, no customs filing. |
| **PASS_FULL_MODE** | **NO** — blocked on owner decisions B-01 and B-02, and on the engineering prerequisites below. |
| **READY_TO_DEPLOY_PRODUCTION** | **NO** — not a code defect. Deploying is an owner decision that has not been made, and the gaps in §2 should be closed first. |

`PASS_LIMITED_MODE` is not a weaker form of "production ready". It means: this system is
honest about what it does not know. It will produce internal drafts, mark every AI-derived
value with its source and confidence, and refuse to proceed when critical evidence is
missing. It will **not** tell you a tariff rate that is legally correct, because the only
tariff data it has is labelled demo fixture data.

## 1. What was verified for this gate

Verified fresh in a clean checkout (not inherited from the G15C staging report):

- 72 API pytest + 21 infra pytest + 3 vitest + 2 Playwright, all passing; ruff clean;
  single Alembic head `0010_copilot_meta` applied from zero; secret scan clean.
- Owner acceptance flow A–P: **17/17** against a local stack.
- Negative/security suite: **18/18**, 0 server errors.
- Fail-closed probes (§3) all behave correctly.
- Live staging read-only: `/health` 200, `/ready` 200 (`database ok`, `0010_copilot_meta`,
  provider `mock`, env `staging`), `/` 200, valid Let's Encrypt certificate, 4 containers
  with 0 restarts, host checkout clean.

## 2. Gaps between PASS_LIMITED_MODE and PASS_FULL_MODE

These are genuine gaps, not paperwork. None of them is a defect in what was built; each is
work that was explicitly out of scope until now.

### 2.1 Blocked on an owner decision

| Gap | Item | Consequence while open |
|---|---|---|
| No real OCR/LLM provider | **B-01** | Extraction quality on real scanned documents is unknown. The mock parses the fixture format deterministically; it is not an OCR engine. |
| No authoritative tariff/FTA/policy data | **B-02** | Every rate, FTA eligibility and policy requirement the system shows is demo fixture data. Legally meaningless. This is the single hardest blocker for real filing. |
| Shared-proxy dependency for TLS | **B-06** | Availability is coupled to a proxy serving unrelated projects. |
| Demo users exist on staging | **B-07** | Four known accounts on a TLS-exposed host. |

### 2.2 Engineering prerequisites (no owner decision needed, but not built)

| Gap | Why it matters in production | Mitigation available now |
|---|---|---|
| **No automated backup.** `docs/STAGING_ROLLBACK.md` documents the commands and says "nightly", but no scheduler existed anywhere in the repo. | A host loss is unbounded data loss. | **Closed by this gate:** `scripts/production/backup.sh` (hardened: `umask 077` + `chmod 600` artifacts, `0700` validated `BACKUP_DIR`, `UMask=0077` on the unit) + example systemd timer. Still needs installation (root) and an off-host copy. |
| **A live backup is not an atomic snapshot.** The dump and the uploads archive are taken sequentially seconds apart, so they are not one instant of the system. | Expect a few dangling document references around the backup window — not corruption, but not a coherent restore either. | Documented in `docs/PRODUCTION_RUNBOOK.md` §4 with the quiesced procedure for a coherent pair, a post-restore reconciliation command, and filesystem/volume snapshots as the no-outage answer (an infrastructure decision). |
| **No off-host backup replication.** | Same-host copies do not survive host loss. | Operator must replicate `BACKUP_DIR`. The script says so in its own output. |
| **No restore drill schedule.** | An untested backup is not a backup. G15C restored once, successfully. | Runbook gives the procedure; cadence is an operations decision. |
| **No monitoring, alerting or log aggregation.** `/health` and `/ready` exist and are correct; nothing watches them. | An outage is discovered by a user, not an alert. | Runbook §5 specifies exactly what to point a monitor at. Choosing the tool is an owner decision. |
| **No log rotation in the staging compose.** | json-file logs grow until the disk fills — on a host shared with 10+ other containers. | **Closed by this gate** in the production overlay (10 MiB × 5 per service). |
| **No `web` healthcheck in the staging compose.** | A dead static-file container reports "Up" and the proxy serves 502. | **Closed by this gate** in the production overlay. |
| **No rate limiting on `/auth/login`.** PBKDF2 (210k iterations) makes guessing expensive, but nothing locks an account or throttles an IP. | Online password guessing is possible. | Out of scope by prior decision. Put throttling in the edge proxy before any internet-facing production use. |
| **No OIDC / central identity.** Tokens are HMAC-signed, 8-hour TTL, no revocation list. | Logging a user out everywhere requires rotating `APP_SECRET_KEY`, which logs out everyone. | D-012 anticipates replacing the issuer. |
| **Object storage is a local directory.** | Single-host durability; no versioning or server-side encryption. | The `Storage` protocol is ready for an S3 adapter; none is implemented. |
| **Knowledge datasets are global, not tenant-scoped** (`app/models/knowledge.py`, deliberate). Any tenant Admin with `knowledge.manage` can deactivate a dataset for **every** tenant. | In a multi-tenant production this is a cross-tenant availability action. Fails closed (evaluators raise CRITICAL), so it cannot silently corrupt data. | Acceptable single-tenant; needs a decision before onboarding a second customer. |

## 3. Fail-closed behaviour (verified, not assumed)

Each probe was executed against this commit:

| Probe | Result |
|---|---|
| `APP_SECRET_KEY` absent, `APP_ENV=production` | Refuses to start: `RuntimeError: APP_SECRET_KEY is required outside development` |
| `APP_SECRET_KEY` shorter than 32 chars | Refuses to start: `RuntimeError: APP_SECRET_KEY must be at least 32 characters` |
| `AI_PROVIDER=openai` (not implemented) | `/ready` → **503** `ai_provider: error: AI provider 'openai' is not available in this build`. No silent fallback to the mock. |
| `OBJECT_STORAGE_PROVIDER=s3` (not implemented) | `RuntimeError: storage provider 's3' not available in this build` |
| `scripts/seed_demo.py` with `APP_ENV=production` | `seed_demo refuses to run outside development/test` — demo users cannot be created in production at all. |

The third row is the important one: a half-configured real provider cannot serve traffic,
because readiness fails and an orchestrator will not route to it.

## 4. Owner decision briefs

Each of these is the owner's call. Nothing below has been decided or pre-empted by this gate.

### B-01 — Real OCR/LLM provider credentials · OPEN

- **Today:** `AI_PROVIDER=mock`. `MockProvider` is deterministic and parses the fixture
  document format; it does no image OCR.
- **What a decision unlocks:** real document extraction, and with it a meaningful measurement
  of extraction accuracy.
- **Not just configuration.** `app/ai/gateway.py` raises `ProviderNotConfigured` for any name
  but `mock`. A real provider needs an implementation of the three `AIProvider` methods, plus
  secret handling, cost/rate-limit handling, timeout and retry behaviour, and a decision about
  sending customer trade documents to a third party (a data-processing question, not a
  technical one). The validation layer that treats provider output as untrusted already exists.
- **Recommendation:** keep `mock` until a provider is chosen *and* a data-processing agreement
  is in place. Do not enable a real provider and real filing in the same change.

### B-02 — Authoritative tariff / FTA / policy data source · OPEN

- **Today:** four datasets seeded `is_demo=true`, labelled `DEMO — NON-AUTHORITATIVE — NOT FOR
  CUSTOMS FILING`, surfaced as a persistent banner in the UI and in `/knowledge/notice`.
- **Why this is the hardest blocker:** the demo rates are illustrative and are not Vietnamese
  law (D-006). No amount of software quality makes a declaration drafted from them correct.
- **What a decision needs to cover:** the source, its licence, its update cadence, who verifies
  an update, and the effective-date semantics. The schema is already versioned and
  effective-dated, and evaluators fail closed when no dataset is active — so the mechanism is
  ready; the data is not.
- **Recommendation:** treat B-02 as the gate for `PASS_FULL_MODE`. B-01 without B-02 produces
  well-extracted data classified against fixture rules.

### B-06 — `hq.vipgroup.com.vn` depends on the host's shared Caddy · OPEN

- **Today, verified fresh:** two `Via: 1.1 Caddy` hops. The shared `vip-staging-caddy`
  container terminates the valid Let's Encrypt certificate and forwards to this stack's own
  proxy on `127.0.0.1:18100`/`18543`. The stack runs `TLS_MODE=off` because it cannot own ports
  80/443 — other services on the host do.
- **Consequences:** a change to the shared proxy can take this stack down, and vice versa;
  certificate lifecycle is owned by a config file outside this repository. Security headers are
  correct today (verified: HSTS, CSP, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`),
  but they are set by *this* stack's Caddyfile and would be lost if routing ever bypassed it.
- **Options:** (a) keep the shared proxy — zero work, accepts the coupling; (b) give production
  its own host or IP and set `TLS_MODE=acme` so it owns ports 80/443 and its own certificates.
- **Recommendation:** (a) is fine for staging. For production choose (b): the production
  template defaults to `TLS_MODE=acme` for that reason. Do not change the shared proxy as part
  of this gate.

### B-07 — Delete the staging demo users after sign-off · OPEN

- **Today:** `operator@demo.local`, `reviewer@demo.local`, `senior@demo.local`,
  `admin@demo.local` exist on staging with the acceptance password.
  `docs/STAGING_SECRETS.md` already says to delete them once acceptance is signed off.
- **Risk while open:** four known usernames on a TLS-exposed host with no login rate limiting.
  The data behind them is demo data, so exposure is limited, but the accounts are real.
- **Not actioned by this gate** — deleting users is a data-deleting action on a live host and
  the brief reserves it for the owner.
- **Recommendation:** after sign-off, either delete them or rotate `SEED_DEMO_PASSWORD` and
  re-seed. Production never has this problem: `seed_demo.py` refuses to run there (§3).
  Note that `User` rows are referenced by audit and decision records, so prefer setting
  `is_active = false` (which `current_user` already rejects) over a hard delete, to avoid
  breaking the audit trail's actor references.

## 5. Recommended sequence

1. Owner reviews this gate and `docs/G16_PRODUCTION_REVIEW.md`, then reviews draft PR #1
   (`release/g16-rc1` → `develop`) and merges it, so `develop` holds the G16 additions.
   Re-verify and freeze `develop` at that merge commit, and only then prepare `develop` → `main`.
   `READY_TO_MERGE_MAIN` is **NO** until those steps are done. Merging deploys nothing.
2. Resolve **B-07** (cheap, reduces exposure now).
3. Decide **B-06** for production addressing before provisioning a production host.
4. Install automated backup + a monitor on `/ready` (§2.2) — these are prerequisites for
   running anything in production, including limited mode.
5. Decide **B-01** and **B-02**. Until both are resolved and their data verified, the system
   stays in `PASS_LIMITED_MODE` and must not be used to prepare a real customs filing.
6. Any connection to a customs system remains a separate, explicitly-gated decision
   (product rule #7). No such adapter exists in this build.
