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
        # Interactive docs only in development: the schema enumerates every role-gated endpoint (G18C).
        docs_url="/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_development else None,
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
        # G18B: defence in depth — set at the API layer too, so a proxy misconfiguration cannot drop them.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "private, no-store")
        return response

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
