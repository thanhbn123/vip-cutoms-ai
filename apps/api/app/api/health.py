from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.gateway import get_provider
from app.core.config import get_settings
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness: process is up. No dependencies checked."""
    return {"status": "ok", "service": "vip-customs-api", "version": "0.1.0"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: database reachable, migrations applied, AI provider configured."""
    checks: dict[str, str] = {}
    ok = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["migrations"] = rev or "missing"
        ok = ok and bool(rev)
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        checks["database"] = f"error: {type(exc).__name__}"
        ok = False
    try:
        checks["ai_provider"] = get_provider().name
    except Exception as exc:  # noqa: BLE001
        checks["ai_provider"] = f"error: {exc}"
        ok = False
    checks["environment"] = get_settings().app_env
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", "checks": checks})
