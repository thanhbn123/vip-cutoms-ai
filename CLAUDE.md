# CLAUDE.md — VIP Customs AI Project Controller

You are the implementation controller for `vip-cutoms-ai`.

## Source of truth

The owner-approved UX direction is `prototype/index.html` (V12 FINAL). Older prototypes are historical references only.

Read before modifying code:

- `PROJECT_STATUS.md`
- `docs/PRODUCT_SPEC.md`
- `docs/AI_RULES.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/ACCEPTANCE.md`

## Non-negotiable product rules

1. **Fail closed.** Missing evidence on critical customs fields must produce `NEEDS_REVIEW` or `BLOCKED`, never a fabricated value.
2. AI may propose changes; critical fields require reviewer approval before becoming approved data.
3. Preserve source lineage: every AI-extracted or AI-inferred value must record source, confidence, timestamp, and method.
4. Never silently overwrite human-approved values.
5. Historical learning may use only reviewer-approved outcomes.
6. Effective-dated tariff/FTA/policy knowledge must be versioned and traceable.
7. No production customs submission in early gates. Export only internal/versioned drafts until an explicit integration gate is approved.
8. Secrets must never be committed.
9. Every critical state transition must be audited.
10. Tenant/customer data must be isolated by authorization checks, not only by UI filtering.

## Working method

- Work gate-by-gate from `docs/ROADMAP.md`.
- Before coding each gate, inspect current repo state and document assumptions.
- Prefer a complete vertical slice over many unfinished modules.
- Add tests with every behavior change.
- Do not weaken tests to make CI pass.
- Do not invent legal/tariff data. Seed data must be explicitly marked fixture/demo.
- Keep business rules separate from LLM prompts/providers.
- Ensure app can run locally from documented commands.
- Update `PROJECT_STATUS.md` at the end of every gate.

## Stop conditions

Stop and mark `BLOCKED_OWNER` only when a decision truly requires the owner, such as:

- real provider credentials,
- staging/production host access,
- authoritative customs data source selection,
- approval to integrate or submit to an external customs system,
- an irreversible product/business decision.

Do not stop for ordinary implementation choices. Choose a safe default, document it, and continue.

## Gate completion report

For each gate report:

- gate name
- baseline SHA
- final SHA
- files changed
- migrations
- tests and counts
- security checks
- known limitations
- exact next gate
- blockers, if any
