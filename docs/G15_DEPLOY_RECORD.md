# G15 DEPLOYMENT RECORD (updated by G15A — merge of the staging tooling)

| | |
|---|---|
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (untouched) |
| PREVIOUS DEVELOP (G14 candidate, superseded) | `474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae` |
| G15 FEATURE HEAD merged | `a95aa83066d48328d9689411092f1bf17f1c2f91` (`feature/g15-staging-acceptance`) |
| MERGE COMMIT | `030933f09304253ddbd96e44998b4b6fc023df20` — "merge: G15 staging deployment and acceptance tooling" |
| **STAGING_CANDIDATE_SHA** | **`origin/develop` after G15A** — the exact 40-char SHA is printed in the G15A final report and must be passed verbatim as `DEPLOY_SHA`. A record cannot contain its own commit hash; verify with `git rev-parse origin/develop` and `git log -1 --format=%H -- docs/G15_DEPLOY_RECORD.md` (they match). Tags cannot be pushed from the build session (remote returns 403), so no tag is used. |
| Compose project | `vip-customs-ai-staging` |
| Providers | `AI_PROVIDER=mock` (parser / HS / Copilot) — intentionally, for workflow acceptance |
| Knowledge data | DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING (`is_demo=true` only) |
| FIRST_DEPLOY | expected YES — `scripts/staging/deploy.sh` records any previous image/DB baseline |
| Staging host | still NOT PROVIDED → deployment remains BLOCKED_OWNER (B-03) |

What the candidate adds over `474f7d8`: staging deploy/acceptance automation and docs, negative-test driver, demo-password rotation on
re-seed, staging compose `env_file` optional for validation, ignore rules for backups/raw logs. No domain or API behaviour change.

Deploy only this SHA: `DEPLOY_SHA=$(git rev-parse origin/develop) bash scripts/staging/deploy.sh` after confirming it equals the SHA in the G15A report (on the host, after
`infra/staging/.env` is filled — see `docs/STAGING_SECRETS.md`).
