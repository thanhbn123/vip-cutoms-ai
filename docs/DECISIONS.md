# DECISIONS LOG

Format: ID · date · decision · rationale · reversible?

- **D-001 · 2026-10-08 · Stack**: FastAPI + SQLAlchemy 2 + Alembic + psycopg3 (Python 3.12), PostgreSQL 16, React + TypeScript + Vite, pytest + vitest. Matches README "Recommended implementation stack". Reversible: n/a (repo decision).
- **D-002 · Gate numbering**: The owner's session brief (G00 assessment … G13 staging readiness) supersedes `docs/ROADMAP.md` numbering. ROADMAP content is preserved; mapping recorded in `docs/GATES.md`.
- **D-003 · Branching**: This cloud session may only push to `claude/busy-davinci-9u8bye`. No `develop` branch is created and nothing is merged to `main`. Each gate is a separate, labelled commit (`[G0x]`) on that branch. Owner can create `develop` from it and open a PR. No force push.
- **D-004 · CI**: GitHub Actions workflow is added but cannot be observed from this session; status recorded as `CI_EXTERNAL_UNVERIFIED`. Full local verification is the evidence.
- **D-005 · AI provider**: No credentials available → deterministic `MockProvider` (regex/structured-text parser, rule-based HS candidates, template Copilot). `AI_PROVIDER` env selects provider; unknown/unconfigured providers fail closed at startup.
- **D-006 · Demo data**: All tariff/FTA/policy/HS-rule datasets are seeded as `is_demo=true`, label `DEMO — NON-AUTHORITATIVE`, source `fixture`. HS candidates are heading-level only (`8413.xx.xx`); the reviewer must enter the full 8-digit code. Rates in demo tariff are illustrative and are not Vietnamese law.
- **D-007 · Prototype invoice total**: V5 fixture shows total 17,900 USD while lines sum to 1,980 USD. Fixtures use consistent totals (1,980.00); a line-sum vs total validation exists and raises a WARNING if they diverge.
- **D-008 · HS release rule**: HS is a critical field. Every goods item needs an APPROVED reviewer classification decision with an 8-digit code before release, regardless of AI confidence. Confidence < 0.70 or missing required attributes → CRITICAL issue (BLOCKED). 0.70–0.90 → WARNING (NEEDS_REVIEW). ≥ 0.90 → no issue but still pending approval.
- **D-009 · Warnings block release**: Fail-closed: release gate requires zero OPEN issues of any severity. Warnings may be resolved (Reviewer) or waived with reason; critical issues may only be resolved by Reviewer or waived by Senior Reviewer.
- **D-010 · Internal DRAFT preview vs release draft**: As in V12 ("Cho phép: xuất bản nháp nội bộ có watermark DRAFT"), a watermarked preview draft can be generated at any state (`release_eligible=false`, no state change). A release-eligible draft is only produced from `READY_TO_EXPORT` and moves the case to `DRAFT_EXPORTED`. Neither is a customs submission.
- **D-011 · Separation of duties**: Admin manages configuration/datasets/users but has no customs-decision permissions. A user cannot approve a proposal they authored.
- **D-012 · Auth scaffold**: Signed bearer tokens (HMAC-SHA256, `itsdangerous`-free stdlib implementation) with `APP_SECRET_KEY` from env; PBKDF2 password hashing. Dev-only demo users are created by the seed script, never by migrations. A real IdP (OIDC) can replace the token issuer later.
- **D-013 · Audit immutability**: `audit_events` is append-only: PostgreSQL trigger rejects UPDATE/DELETE, and each row stores `prev_hash`/`hash` (SHA-256 chain per tenant) for tamper evidence.
- **D-014 · Package count conflict severity**: V12 labels it WARNING; kept as WARNING (still blocks release per D-009).
- **D-015 · Policy dependency**: An item whose HS is not approved and whose top candidate confidence < 0.70 gets a CRITICAL `POLICY_UNDETERMINED` issue; it must be resolved by a reviewer after HS approval (no auto-clear of critical issues by the system).
- **D-016 · Learning**: Memory rows are created only from APPROVED classification decisions. Rows with outcome CONSULTATION/DISPUTE are `reusable=false` and never boost confidence ("Do not auto-copy").
- **D-017 · Docker**: Docker daemon not available in this session; compose files are written and validated statically; local verification uses a native PostgreSQL 16.
- **D-018 · Frontend**: Single-page app reusing V12 CSS tokens/classes and sidebar order; data comes from the API. Demo login screen lists dev users only when `APP_ENV=development`.
