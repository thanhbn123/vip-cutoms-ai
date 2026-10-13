#!/usr/bin/env bash
# Dependency vulnerability audit (G18J): API (pip-audit on the locked environment) + web (npm audit).
# Production web dependencies must be clean at any level; dev tooling and the API environment are reported at high+.
# Exit 1 when a blocking finding exists. Run locally before a release; CI runs it as the informational `deps-audit` job.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${DEPS_AUDIT_PYTHON:-$ROOT/apps/api/.venv/bin/python}"
rc=0
echo "## api — pip-audit"
if ! "$PY" -m pip_audit --version >/dev/null 2>&1; then "$PY" -m pip install -q pip-audit; fi
( cd "$ROOT/apps/api" && "$PY" -m pip_audit --skip-editable --progress-spinner off ) || rc=1
echo "## web — npm audit (production dependencies: any level blocks)"
( cd "$ROOT/apps/web" && npm audit --omit=dev ) || rc=1
echo "## web — npm audit (all dependencies incl. dev tooling: high+ blocks)"
( cd "$ROOT/apps/web" && npm audit --audit-level=high ) || rc=1
echo "DEPS_AUDIT: $([ $rc -eq 0 ] && echo CLEAN || echo FINDINGS)"
exit $rc
