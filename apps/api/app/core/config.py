"""Runtime configuration. All values come from environment variables; no secrets in code."""

import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="development")
    database_url: str = Field(default="postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs")
    # Required outside development. In development an ephemeral random key is generated
    # (tokens are invalidated on restart) so that no default secret ever exists in the repo.
    app_secret_key: str | None = Field(default=None)
    token_ttl_seconds: int = Field(default=8 * 3600)
    ai_provider: str = Field(default="mock")
    object_storage_provider: str = Field(default="local")
    local_storage_dir: str = Field(default="./local-data/uploads")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024)
    cors_origins: str = Field(default="http://localhost:5173")

    @property
    def is_development(self) -> bool:
        return self.app_env in {"development", "test"}

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
