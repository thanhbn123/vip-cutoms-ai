from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import get_settings
from app.db import get_db
from app.services import readiness

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness: process is up. No dependencies checked."""
    s = get_settings()
    return {"status": "ok", "service": "vip-customs-api", "version": "0.1.0", "mode": s.app_mode, "release_sha": s.release_sha}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: mode-aware (G18). Full mode fails closed when any production dependency is missing."""
    r = readiness.evaluate(db)
    return JSONResponse(status_code=200 if r.ok else 503, content=r.body())


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint(db: Session = Depends(get_db)):
    """Prometheus text exposition. Counters only; no tenant/user/case identifiers, no secrets."""
    return PlainTextResponse(metrics.render(readiness.metrics_lines(db)), media_type="text/plain; version=0.0.4")
