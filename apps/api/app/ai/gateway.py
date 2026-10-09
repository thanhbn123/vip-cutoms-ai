"""AI gateway. Business logic depends only on the capability protocols; provider SDKs stay behind it.

G18: each capability (document_ocr, document_ai, hs_ai, copilot) is resolved from configuration
independently. Implemented provider names:

    mock      deterministic, offline, no credentials (all four capabilities)
    http-llm  vendor-neutral JSON-over-HTTPS adapter (document_ai, hs_ai, copilot); requires
              AI_PROVIDER_BASE_URL + AI_PROVIDER_API_KEY + AI_PROVIDER_MODEL, otherwise refused

Anything else — and `http-llm` for document_ocr — raises ProviderNotConfigured. There is no
fallback from a failed or unconfigured real provider to the mock (product rule #1).
"""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache

from app.ai.base import AIProvider, ProviderHealth, ProviderUnavailable
from app.core.config import AI_CAPABILITIES, get_settings

IMPLEMENTED_PROVIDERS = {"mock": AI_CAPABILITIES, "http-llm": ("document_ai", "hs_ai", "copilot")}


class ProviderNotConfigured(RuntimeError):
    pass


@lru_cache
def get_capability(capability: str):
    if capability not in AI_CAPABILITIES:
        raise KeyError(capability)
    s = get_settings()
    name = s.provider_for(capability)
    if name == "mock":
        from app.ai.mock_provider import MockProvider

        return MockProvider(capability=capability)
    if name == "http-llm":
        if capability not in IMPLEMENTED_PROVIDERS["http-llm"]:
            raise ProviderNotConfigured(f"provider 'http-llm' does not implement {capability} (an OCR vendor is an owner input, B-01)")
        if not s.real_provider_configured():
            raise ProviderNotConfigured("provider 'http-llm' selected but AI_PROVIDER_BASE_URL/API_KEY/MODEL are not all set")
        from app.ai.http_llm_provider import HttpLLMProvider

        try:
            return HttpLLMProvider(s, capability=capability)
        except ProviderUnavailable as exc:
            raise ProviderNotConfigured(str(exc)) from exc
    # Fail closed instead of silently falling back to the mock.
    raise ProviderNotConfigured(f"AI provider '{name}' is not available in this build")


def get_provider() -> AIProvider:
    """Legacy entry point: the document-extraction provider (also HS reasoning for the mock)."""
    return get_capability("document_ai")


def provider_status(*, live: bool = True) -> dict[str, dict]:
    """Per-capability health for /ready and /metrics. Never raises; never includes credentials."""
    out: dict[str, dict] = {}
    for cap in AI_CAPABILITIES:
        try:
            p = get_capability(cap)
            h = p.health(live=live)
        except ProviderNotConfigured as exc:
            h = ProviderHealth(cap, get_settings().provider_for(cap), "-", configured=False, healthy=False, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - health must report, not raise
            h = ProviderHealth(cap, get_settings().provider_for(cap), "-", configured=True, healthy=False, detail=type(exc).__name__)
        out[cap] = asdict(h)
    return out


def reset_cache() -> None:
    get_capability.cache_clear()
