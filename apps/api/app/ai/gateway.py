"""AI gateway. Business logic depends only on the `AIProvider` protocol; provider SDKs stay behind it."""

from __future__ import annotations

from functools import lru_cache

from app.ai.base import AIProvider
from app.core.config import get_settings


class ProviderNotConfigured(RuntimeError):
    pass


@lru_cache
def get_provider() -> AIProvider:
    name = get_settings().ai_provider.lower()
    if name == "mock":
        from app.ai.mock_provider import MockProvider

        return MockProvider()
    # Real providers (OCR/LLM) require owner-supplied credentials (BLOCKED_OWNER B-01).
    # Fail closed instead of silently falling back to the mock.
    raise ProviderNotConfigured(f"AI provider '{name}' is not available in this build")
