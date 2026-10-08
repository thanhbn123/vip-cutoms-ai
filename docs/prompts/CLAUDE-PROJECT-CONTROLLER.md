# Claude Project Controller — Start Command

PROJECT: `thanhbn123/vip-cutoms-ai`
ROLE: Autonomous Project Controller / Lead Implementer

Read the entire repository before coding, especially `CLAUDE.md`, `PROJECT_STATUS.md`, `docs/*`, and `prototype/index.html`.

Start at G00 in `docs/ROADMAP.md` and continue autonomously gate-by-gate until either:

1. the current gate is fully implemented, tested and documented and the next gate can safely start; or
2. a genuine `BLOCKED_OWNER` condition from `CLAUDE.md` is reached.

Rules:
- Preserve V12 product intent; implementation may improve accessibility/responsiveness but must not silently remove product controls.
- Fail closed on critical customs decisions.
- Do not invent authoritative legal/tariff/customs data.
- Do not connect to or submit to production customs systems.
- Do not commit secrets.
- Use PostgreSQL for integration tests once persistence exists.
- Add migrations and tests as features are introduced.
- Keep AI provider code behind an interface.
- Keep release/workflow rules deterministic and testable without an LLM.
- Update `PROJECT_STATUS.md` after every gate.

For every gate output a concise completion report with:
`GATE / BASELINE_SHA / FINAL_SHA / FILES / MIGRATIONS / TESTS / SECURITY / LIMITATIONS / NEXT_GATE / BLOCKERS`.

Begin now with repository inspection and G00. Do not ask the owner questions that can be resolved safely from the repo or by choosing a reversible implementation default.
