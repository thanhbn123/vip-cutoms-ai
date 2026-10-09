"""Runtime configuration. All values come from environment variables; no secrets in code.

G18 adds an explicit runtime mode (APP_MODE) and per-capability AI provider selection. The
default of every setting is the *safest* value: demo mode, mock providers, no credentials.
"""

import secrets
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_MODES = ("demo", "limited", "full")
AI_CAPABILITIES = ("document_ocr", "document_ai", "hs_ai", "copilot")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development")
    # demo    → mock AI + demo knowledge data allowed (development, acceptance, training)
    # limited → real users, DRAFT workflow only, demo limitations prominently visible, no customs filing
    # full    → real providers healthy + authoritative customs datasets active + production controls; refuses otherwise
    app_mode: str = Field(default="demo")
    # Git SHA of the deployed build (IMAGE_TAG in compose). Reported by /ready; never secret.
    release_sha: str | None = Field(default=None)
    database_url: str = Field(default="postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs")
    # Required outside development. In development an ephemeral random key is generated
    # (tokens are invalidated on restart) so that no default secret ever exists in the repo.
    app_secret_key: str | None = Field(default=None)
    token_ttl_seconds: int = Field(default=8 * 3600)

    # --- AI providers -------------------------------------------------------------------------
    # AI_PROVIDER is the default for every capability; the four specific variables override it.
    # Implemented names: "mock" (deterministic, offline) and "http-llm" (vendor-neutral JSON-over-
    # HTTPS adapter, see app/ai/http_llm_provider.py). Anything else fails closed.
    ai_provider: str = Field(default="mock")
    document_ocr_provider: str | None = Field(default=None)
    document_ai_provider: str | None = Field(default=None)
    hs_ai_provider: str | None = Field(default=None)
    copilot_provider: str | None = Field(default=None)
    # Credentials/endpoint for the real adapter. Absent → the adapter is NOT constructed (fail closed).
    ai_provider_base_url: str | None = Field(default=None)
    ai_provider_api_key: str | None = Field(default=None)
    ai_provider_model: str | None = Field(default=None)
    ai_timeout_seconds: float = Field(default=30.0)
    ai_max_retries: int = Field(default=2)
    # Cost control (USD). 0 → unknown price, accounting records tokens only; budget None → unlimited (not recommended).
    ai_cost_per_1k_input_tokens_usd: float = Field(default=0.0)
    ai_cost_per_1k_output_tokens_usd: float = Field(default=0.0)
    ai_daily_budget_usd: float | None = Field(default=None)
    ai_max_document_bytes: int = Field(default=5 * 1024 * 1024)

    # --- storage / web ------------------------------------------------------------------------
    object_storage_provider: str = Field(default="local")
    local_storage_dir: str = Field(default="./local-data/uploads")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024)
    cors_origins: str = Field(default="http://localhost:5173")

    # --- production operations --------------------------------------------------------------
    # JSON written by scripts/production/backup_offsite.sh ({"last_success_at": ISO8601, ...}). Read-only here.
    backup_status_file: str | None = Field(default=None)
    backup_max_age_hours: float = Field(default=26.0)

    @field_validator("app_mode")
    @classmethod
    def _mode_known(cls, v: str) -> str:
        v = (v or "demo").strip().lower()
        if v not in APP_MODES:
            raise ValueError(f"APP_MODE must be one of {APP_MODES}, got {v!r}")
        return v

    @property
    def is_development(self) -> bool:
        return self.app_env in {"development", "test"}

    @property
    def is_full_mode(self) -> bool:
        return self.app_mode == "full"

    def provider_for(self, capability: str) -> str:
        """Provider name for one AI capability (specific variable, else AI_PROVIDER)."""
        if capability not in AI_CAPABILITIES:
            raise KeyError(capability)
        specific = getattr(self, f"{capability}_provider")
        return (specific or self.ai_provider).strip().lower()

    def real_provider_configured(self) -> bool:
        return bool(self.ai_provider_base_url and self.ai_provider_api_key and self.ai_provider_model)

    def resolved_secret(self) -> str:
        if self.app_secret_key:
            if len(self.app_secret_key) < 32:
                raise RuntimeError("APP_SECRET_KEY must be at least 32 characters")
            return self.app_secret_key
        if not self.is_development:
            raise RuntimeError("APP_SECRET_KEY is required outside development")
        return _ephemeral_secret()


@lru_cache
def _ephemeral_secret() -> str:
    return secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
