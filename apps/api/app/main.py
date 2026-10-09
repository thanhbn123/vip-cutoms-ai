from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.router import api_router
from app.core import metrics, modes
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.resolved_secret()  # fail fast if the secret is missing outside development
    modes.enforce_startup(settings)  # APP_MODE=full refuses to start with mock providers / missing production config
    app = FastAPI(
        title="VIP Customs AI API",
        version="0.1.0",
        description="Fail-closed customs declaration drafting. Produces internal DRAFTS only — never submits to customs.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def _count_requests(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            metrics.observe_http(request.method, 500)
            raise
        metrics.observe_http(request.method, response.status_code)
        return response

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
