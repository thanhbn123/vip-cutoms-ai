# G17 — MAIN RELEASE FREEZE · 2026-10-09

## Verdict
**`develop` merged into `main` with owner approval. Release frozen at `main` = `4a2acb9`. PASS_LIMITED_MODE only. Production deployment NOT AUTHORIZED.**

The owner's G17 decision authorized exactly three things: merge `develop → main` (PR #2), freeze the accepted RC in `main`, and update release documentation. It did **not** authorize production deployment, real customs filing, VNACCS submission, replacing demo customs data with unverified sources, or enabling unverified AI providers. None of those was done.

## Git record
| | |
|---|---|
| PR | [thanhbn123/vip-cutoms-ai#2](https://github.com/thanhbn123/vip-cutoms-ai/pull/2) `develop → main`, merged with a **merge commit** (repo policy D-003: history preserved, no squash, no force push) |
| PR HEAD SHA = RC SHA | `54a00e7063e1cb1009bd7d2dd57b2d0fa34471e6` (unchanged between owner review and merge; verified with `expectedHeadSha`) |
| PRE-MAIN SHA | `2afdf6b49112f5db3f2962fcc3345c4c5b9055a0` |
| MAIN MERGE SHA = FINAL MAIN SHA | `4a2acb9130afb47b30350ed7b52197e28717847a` (parents `2afdf6b`, `54a00e7`) |
| DEVELOP SHA after merge | `54a00e7063e1cb1009bd7d2dd57b2d0fa34471e6` — intact; `main` and `develop` have the **identical tree** `bf683ae9…` |
| Staging accepted SHA | `9649ec7` on `hq.vipgroup.com.vn` (G15C). Runtime subtrees identical to the RC → staging stays as the accepted environment, no redeploy |
| Release tag | **TAG_EXTERNAL_BLOCKED** — `v0.1.0-rc1` created locally at `4a2acb9`, push refused by the session's GitHub credential (tag refs), 4 attempts; see "Release tag" below |

Pre-merge re-verification (all PASS): PR open, base `main`, head `develop`, head SHA as expected, `mergeable_state=clean`, 8/8 check runs green on `54a00e7` (push run 69 + PR run 70: api, web, infra, secrets), `origin/main` and `origin/develop` at the expected SHAs, `main` an ancestor of `develop`, working tree clean.

## Evidence at the RC SHA (no drift)
| Check | Result |
|---|---|
| Backend pytest | **72 passed** |
| Infra pytest (root `tests/`) | **71 passed** (re-run at RC SHA) |
| Vitest | **3 passed** |
| Playwright (native / Docker) | **2/2 · 2/2** |
| Docker acceptance A–P | **17/17** |
| Negative / security suite | **18/18** |
| Migration | `0010_copilot_meta`, **single head** (re-run `alembic heads` at RC SHA) |
| CI | **GREEN** on `54a00e7` |
| Secret scan | **clean** (re-run at RC SHA) |
| Critical / high bugs | **0 / 0** (low findings in `docs/G16_PRODUCTION_REVIEW.md` §3) |

Large suites were not re-executed for G17: CI and the G16 evidence are on the exact RC SHA, and the only post-`d21fd77` commits are test/tooling/docs (`git diff d21fd77 54a00e7 -- apps/api/app apps/web/src infra packages Makefile .env.example .github` is empty).

## Limited-mode warnings (confirmed present in docs and code)
- AI provider = **mock** only; any other `AI_PROVIDER` fails closed (`/ready` 503).
- Tariff / FTA / policy knowledge = **demo, NON-AUTHORITATIVE**, labelled "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING" (`apps/api/app/services/demo_fixtures.py`, `declaration.py`, exports).
- **NOT FOR CUSTOMS FILING**; **no VNACCS/ECUS connection or submission** (README, product rules).
- Reviewer approval is **mandatory** for critical fields; AI only proposes.
- Release gate remains **fail-closed** (`NEEDS_REVIEW` / `BLOCKED` on missing evidence; demo case seeds as BLOCKED).

## Blockers (canonical IDs, `docs/STATUS.md`)
| ID | Status | Meaning |
|---|---|---|
| B-01 | OPEN — BLOCKED_OWNER | Real OCR/LLM provider not integrated (mock only) |
| B-02 | OPEN — BLOCKED_OWNER | Authoritative tariff / FTA / policy data source not selected (demo data only) |
| B-06 | OPEN — OWNER | Production host / domain / TLS termination undecided; staging behind a shared Caddy |
| B-07 | OPEN — OWNER | Staging demo users `*@demo.local` must be deactivated after acceptance |

**If the system is intended for real customs filings, B-01 and B-02 remain hard blockers for FULL PRODUCTION.**

## Production
- PRODUCTION MODE: **PASS_LIMITED_MODE**
- PRODUCTION DEPLOYMENT: **NOT AUTHORIZED** — no SSH to any host, no production compose run, staging untouched, `hq.vipgroup.com.vn` unchanged in G17.
- READY_FOR_FULL_PRODUCTION: **NO**

## Release tag
Annotated tag `v0.1.0-rc1` → `4a2acb9130afb47b30350ed7b52197e28717847a`, message "VIP Customs AI — G17 limited-mode release freeze", created locally. Push: **TAG_EXTERNAL_BLOCKED** — the session's GitHub credential does not accept tag refs (`refs/tags/*` push rejected on 4 attempts; branch pushes work). Not a G17 failure per the owner brief. An operator with tag permission recreates it with:
```bash
git fetch origin main
git tag -a v0.1.0-rc1 4a2acb9130afb47b30350ed7b52197e28717847a -m "VIP Customs AI — G17 limited-mode release freeze"
git push origin refs/tags/v0.1.0-rc1
```

## Documentation placement
Per D-003 this G17 record is committed to `develop` (`docs/g17-main-release-freeze` merged `--no-ff`). `main` is frozen at `4a2acb9` and is **not** advanced for documentation; the record reaches `main` with the next owner-approved `develop → main` merge.

## Next gate
**G18 — Real Provider + Authoritative Customs Data + Production Infrastructure.** Requires owner inputs: real AI provider credentials (B-01), authoritative customs data source selection (B-02), production host/domain/TLS decision (B-06), staging demo-user deactivation (B-07). Until then the system runs in limited mode only.
