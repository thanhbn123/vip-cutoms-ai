# STAGING ACCEPTANCE (checklist for the owner's acceptance session)

## Smoke (≤ 10 min, after `up -d`)
- [ ] `GET /health` → `{"status":"ok"}` ; `GET /ready` → `status=ready`, `checks.migrations=0010_copilot_meta` (or newer single head), `ai_provider=mock`
- [ ] UI loads over TLS at `https://PUBLIC_HOST/`, sidebar shows the 9 V12 entries
- [ ] Login as `reviewer@demo.local` (if seeded) — wrong password → 401, UI error
- [ ] Case `VIP-HQ-261008-001` present, status BLOCKED; Document Center shows 4 parsed documents
- [ ] Hàng hóa & HS: `ABC-500 8413 87% REVIEW`, `PVC-20 3917 95%`, `CT-88 8537 64% BLOCKED`
- [ ] Knowledge Hub shows every dataset with **DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING**
- [ ] Reviewer & Release: gate BLOCKED, "Xuất DRAFT" works (watermarked), "Phát hành" disabled

## Functional (the 16-step owner flow, ~45 min)
1 create case · 2 upload Invoice/PL/B-L/Form E (fixtures in `apps/api/tests/fixtures/minh_phat`) · 3 run AI · 4 fields with confidence/source ·
5 package conflict 124/126 · 6 three items · 7 HS candidates · 8 item 3 BLOCKED · 9 Copilot "Còn thiếu gì để khai?" · 10 upload catalogue →
item 3 REVIEW · 11 reviewer approves HS ×3, C/O decision, approves fields, resolves warnings · 12 audit shows actor/before/after/reason ·
13 READY_TO_EXPORT · 14 release draft JSON + CSV (versioned, checksum) · 15 Lịch sử & Learning shows the 3 approved codes ·
16 new case with the same invoice → item 1 candidate shows history EXACT match (+0.05), still NEEDS_REVIEW.

## Security spot checks
- [ ] Operator cannot approve HS / resolve issues (403 in UI and API)
- [ ] Second tenant (if created) cannot read the demo case (404)
- [ ] Upload `.exe` rejected (422); 25 MB file rejected (413)
- [ ] `GET /api/v1/cases` without token → 401 ; `/documents/<id>/content` of another tenant → 404
- [ ] `docker compose logs` contain no secrets

## Automated evidence (run from a workstation against staging)
`E2E_BASE_URL=https://PUBLIC_HOST PW_CHROMIUM_PATH=… npx playwright test` in `apps/web` (seeded demo tenant required).

Sign-off: product owner · reviewer lead · engineering. Result recorded in `docs/G15_STAGING_ACCEPTANCE_REPORT.md` (next gate).
