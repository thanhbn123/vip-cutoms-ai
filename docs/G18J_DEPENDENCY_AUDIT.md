# G18J — Dependency vulnerability audit (API + web) and its CI job

First known-vulnerability audit of the repository's dependencies, done without any owner input.

## Findings and disposition

| Scope | Before | After |
|---|---|---|
| web **production** dependencies (`npm audit --omit=dev`) | 0 | 0 |
| web **dev tooling** (`npm audit`) | 8 (2 critical, 3 high, 3 moderate): vitest/tinypool RCE gadgets, vite dev-server request/`?raw` fs.deny bypass and optimized-deps `.map` traversal, esbuild dev-server, Playwright browser download without TLS verification | **0** — `vite 6.0.7 → 8.3.4`, `vitest 2.1.8 → 5.0.4`, `@vitejs/plugin-react 4.3.4 → 6.1.2`, `@playwright/test 1.49.1 → 1.64.0` (all pinned exactly) |
| API environment (`pip-audit`) | only `pip 24.0` of the local venv (5 advisories) — not an application dependency; the Docker image already runs `pip install --upgrade pip` at build | venv pip upgraded; **No known vulnerabilities found** |

None of the dev-tooling findings reaches a deployed stack (the web image serves a static build through nginx; the API
image has no npm at all), but they do reach every developer machine and CI runner, so they were fixed rather than accepted.

## Verification after the major upgrades
`tsc -b` clean · vitest 16/16 · `vite build` OK · isolated Playwright 3/3 against the Vite 8 dev server · Docker smoke
(web image rebuilt with Vite 8 on `node:22-alpine`), acceptance A–R 19/19 + Playwright 3/3, negative 20/20.

## Repeatable
- `scripts/deps_audit.sh` — pip-audit on the API environment (editable package skipped), `npm audit --omit=dev` (any
  level blocks), `npm audit --audit-level=high` (dev tooling, high+ blocks); prints `DEPS_AUDIT: CLEAN|FINDINGS`.
- CI job `deps-audit` runs it on every push with `continue-on-error: true` and writes the result into the job summary:
  a CVE published overnight must not block an unrelated merge, but it is never invisible. Before a release the script
  must be CLEAN (added to the release checklist in `docs/ACCEPTANCE.md`).
