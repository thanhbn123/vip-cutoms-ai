"""G18 — vendor-neutral real-provider adapter, exercised against a fake HTTP transport (no network, no credentials)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai import accounting
from app.ai.base import ProviderBudgetExceeded, ProviderInvalidOutput, ProviderTimeout, ProviderUnavailable
from app.ai.http_llm_provider import HttpLLMProvider
from app.ai.redaction import describe_payload, redact
from app.core.config import Settings


def settings(**kw) -> Settings:
    base = dict(ai_provider="http-llm", ai_provider_base_url="https://llm.example.test/v1", ai_provider_api_key="placeholder-key-not-real",
                ai_provider_model="test-model", ai_max_retries=2, ai_timeout_seconds=1.0, ai_cost_per_1k_input_tokens_usd=0.01,
                ai_cost_per_1k_output_tokens_usd=0.03)
    base.update(kw)
    return Settings(**base)


def envelope(content: dict | str, usage=(100, 50)) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content) if isinstance(content, dict) else content}}],
            "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}


def provider(handler, **kw) -> HttpLLMProvider:
    accounting.ACCOUNTANT.reset()
    return HttpLLMProvider(settings(**kw), transport=httpx.MockTransport(handler))


def test_requires_all_credentials():
    with pytest.raises(ProviderUnavailable):
        HttpLLMProvider(settings(ai_provider_api_key=None))


def test_extraction_validates_structured_output_and_accounts_cost():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        seen["corr"] = req.headers.get("x-request-id")
        body = json.loads(req.content)
        seen["format"] = body.get("response_format")
        return httpx.Response(200, json=envelope({"doc_type": "INVOICE", "values": [
            {"key": "invoice.number", "value": "INV-1", "confidence": 0.93, "source_ref": "line:3", "method": "llm.extract"},
            {"key": "invoice.total_amount", "value": "1000", "confidence": 1.4, "source_ref": "line:9"}], "warnings": []}))

    p = provider(handler)
    with pytest.raises(ProviderInvalidOutput):  # confidence 1.4 violates the schema → the WHOLE answer is rejected, nothing guessed
        p.extract_document("INVOICE", "inv.txt", b"Invoice No: INV-1")
    led = accounting.ACCOUNTANT.snapshot()
    assert led.calls == 1 and led.failures == 1 and led.input_tokens == 100 and led.output_tokens == 50
    assert led.cost_usd == pytest.approx(0.001 + 0.0015)
    assert seen["auth"].startswith("Bearer ") and seen["corr"] and seen["format"] == {"type": "json_object"}


def test_extraction_success_round_trip():
    def handler(req):
        return httpx.Response(200, json=envelope({"doc_type": "INVOICE", "values": [
            {"key": "invoice.number", "value": " INV-1 ", "confidence": 0.93, "source_ref": "line:3"}], "warnings": ["w1"]}))

    res = provider(handler).extract_document("INVOICE", "inv.txt", b"Invoice No: INV-1")
    assert res.provider == "http-llm" and [v.key for v in res.values] == ["invoice.number"] and res.values[0].value == "INV-1"
    assert res.values[0].method == "llm.extract" and any(w.startswith("correlation_id=") for w in res.warnings) and "w1" in res.warnings


def test_binary_document_without_ocr_fails_closed_with_warning():
    p = provider(lambda req: httpx.Response(500))
    res = p.extract_document("INVOICE", "scan.pdf", b"\x89PNG\x00\x01\xff\xfe")
    assert res.values == [] and any("OCR" in w for w in res.warnings)


def test_oversized_document_is_refused_not_truncated():
    p = provider(lambda req: httpx.Response(200, json=envelope({})), ai_max_document_bytes=10)
    with pytest.raises(ProviderUnavailable, match="AI_MAX_DOCUMENT_BYTES"):
        p.extract_document("INVOICE", "big.txt", b"x" * 11)


def test_retries_on_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.ai.http_llm_provider.time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=envelope({"description": "Máy bơm nước, model X", "reasoning": ["r"]}))

    desc, reasoning = provider(handler).propose_description({"description": "water pump", "model": "X"})
    assert calls["n"] == 3 and desc.startswith("Máy bơm") and any("correlation_id" in r for r in reasoning)
    assert accounting.ACCOUNTANT.snapshot().calls == 1


def test_exhausted_retries_raise_unavailable_and_are_accounted(monkeypatch):
    monkeypatch.setattr("app.ai.http_llm_provider.time.sleep", lambda s: None)
    p = provider(lambda req: httpx.Response(429))
    with pytest.raises(ProviderUnavailable):
        p.propose_description({"description": "x"})
    led = accounting.ACCOUNTANT.snapshot()
    assert led.calls == 1 and led.failures == 1


def test_timeout_raises_provider_timeout(monkeypatch):
    monkeypatch.setattr("app.ai.http_llm_provider.time.sleep", lambda s: None)

    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(ProviderTimeout):
        provider(handler, ai_max_retries=1).propose_description({"description": "x"})


def test_non_retryable_4xx_fails_immediately():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(ProviderUnavailable, match="401"):
        provider(handler).propose_description({"description": "x"})
    assert calls["n"] == 1


def test_non_json_content_is_invalid_output():
    p = provider(lambda req: httpx.Response(200, json=envelope("not json at all")))
    with pytest.raises(ProviderInvalidOutput):
        p.propose_description({"description": "x"})


def test_daily_budget_blocks_before_the_call():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=envelope({"description": "d", "reasoning": []}, usage=(100000, 100000)))

    p = provider(handler, ai_daily_budget_usd=1.0)
    p.propose_description({"description": "x"})  # spends 1.0 + 3.0 USD at the configured prices
    with pytest.raises(ProviderBudgetExceeded):
        p.propose_description({"description": "x"})
    assert calls["n"] == 1


def test_copilot_answer_always_requires_review_and_is_validated():
    def handler(req):
        return httpx.Response(200, json=envelope({"answer": "Theo hồ sơ...", "intent": "MISSING",
                                                  "sources": [{"type": "issue", "id": "abc", "label": "x"}], "reasoning": ["r"],
                                                  "confidence": 0.7, "recommended_actions": ["a"], "requires_review": False}))

    ans = provider(handler).answer_case_question("Còn thiếu gì?", {"case": {}})
    assert ans.requires_review is True and ans.sources == [{"type": "issue", "id": "abc", "label": "x"}] and ans.confidence == 0.7


def test_health_probe_and_cache():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200 if req.url.path.endswith("/models") else 404, json={"data": []})

    p = provider(handler)
    h1, h2 = p.health(), p.health()
    assert h1.healthy and h1.configured and not h1.is_mock and calls["n"] == 1 and h2 == h1  # cached


def test_health_reports_unreachable_endpoint():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    h = provider(handler).health()
    assert h.configured and not h.healthy and "probe failed" in h.detail


def test_redaction_never_leaks_keys_emails_or_long_numbers():
    s = redact("Bearer abc.def-123 key_ABCDEFGHIJKLMNOP a@b.vn tax 0123456789")
    assert "abc.def" not in s and "ABCDEFGHIJKLMNOP" not in s and "a@b.vn" not in s and "0123456789" not in s
    d = describe_payload({"document_text": "secret body"})
    assert set(d) == {"bytes", "sha256_12"} and "secret" not in json.dumps(d)
