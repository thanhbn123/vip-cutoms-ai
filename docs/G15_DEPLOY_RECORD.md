# G15 DEPLOYMENT RECORD

| | |
|---|---|
| DEPLOY_SHA | `474f7d84d2c64938ce86ca74fdb33cc0c0c7f2ae` (= `origin/develop` at G15 start, verified 2026-10-08) |
| MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` (untouched) |
| Compose project | `vip-customs-ai-staging` |
| Providers | `AI_PROVIDER=mock` (parser / HS / Copilot) — intentionally, for workflow acceptance |
| Knowledge data | DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING (`is_demo=true` only) |
| FIRST_DEPLOY | expected YES (no prior staging) — `scripts/staging/deploy.sh` records the previous image/DB baseline if one exists |
| Staging host | **NOT PROVIDED** (brief carried placeholders `<IP_OR_HOSTNAME>`, `<SSH_USER>`, `<STAGING_DOMAIN_OR_NONE>`) → G15 = BLOCKED_OWNER |

Deployment is performed only from this record: never from a floating working tree.
