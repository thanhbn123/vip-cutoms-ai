"""Vendor-neutral real LLM adapter: JSON over HTTPS to a chat-completions style endpoint (G18, B-01).

Implements DocumentExtractionProvider, HsReasoningProvider and CopilotProvider. It is constructed
ONLY when AI_PROVIDER_BASE_URL, AI_PROVIDER_API_KEY and AI_PROVIDER_MODEL are all set; otherwise
app.ai.gateway refuses (ProviderNotConfigured) and nothing falls back to the mock.

Production requirements implemented here (docs/G18_AI_PROVIDER_REQUIREMENTS.md):
  * timeouts on connect/read/write/pool                      (AI_TIMEOUT_SECONDS)
  * bounded retries with exponential backoff on 408/429/5xx and transport errors (AI_MAX_RETRIES)
  * structured-output validation with pydantic; invalid → ProviderInvalidOutput, never a guess
  * token/cost accounting + daily budget (app.ai.accounting), refused BEFORE the call when exhausted
  * request correlation id (X-Request-ID header, logged, returned in CallMeta)
  * no silent fallback: every failure raises a ProviderError subclass
  * redaction: bodies are never logged; only sizes/fingerprints (app.ai.redaction)
  * health(): configuration check + cached live probe (GET {base_url}/models)
  * document size cap (AI_MAX_DOCUMENT_BYTES) so one upload cannot blow the budget

The wire format is the widely implemented "chat completions" JSON shape
(POST {base_url}/chat/completions with `messages`, `model`, `response_format`), which many
vendors and self-hosted gateways accept. The chosen vendor is an OWNER input (B-01); this module
contains no vendor name and no vendor-specific behaviour.

OCR of scanned images is NOT provided by this adapter: the extraction path requires text. A
separate DocumentOcrProvider (vendor to be selected by the owner) must run first for binary
documents; until then binary documents are reported as unreadable (fail closed, as the mock does).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.ai import prompts
from app.ai.accounting import ACCOUNTANT, estimate_cost
from app.ai.base import (
    CallMeta,
    CopilotAnswer,
    ExtractedValue,
    ExtractionResult,
    ProviderHealth,
    ProviderInvalidOutput,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.ai.redaction import describe_payload
from app.core.config import Settings, get_settings

log = logging.getLogger("vip.ai.http_llm")

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
HEALTH_CACHE_SECONDS = 30.0


# --- structured output schemas (what we accept from the model) ---------------------------------
class _ExtractedValueOut(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str = Field(min_length=1, max_length=120)
    method: str = Field(default="llm.extract", max_length=40)


class _ExtractionOut(BaseModel):
    doc_type: str
    values: list[_ExtractedValueOut] = []
    warnings: list[str] = []


class _DescribeOut(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    reasoning: list[str] = []


class _SourceOut(BaseModel):
    type: str
    id: str
    label: str = ""


class _CopilotOut(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    intent: str = Field(default="GENERAL", max_length=40)
    sources: list[_SourceOut] = []
    reasoning: list[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    recommended_actions: list[str] = []
    requires_review: bool = True


class HttpLLMProvider:
    name = "http-llm"
    version = "http-llm-1.0.0"

    def __init__(self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None, capability: str = "document_ai"):
        s = settings or get_settings()
        if not s.real_provider_configured():
            raise ProviderUnavailable("http-llm requires AI_PROVIDER_BASE_URL, AI_PROVIDER_API_KEY and AI_PROVIDER_MODEL")
        self.settings = s
        self.capability = capability
        self.base_url = s.ai_provider_base_url.rstrip("/")
        self.model = s.ai_provider_model
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(s.ai_timeout_seconds, connect=min(10.0, s.ai_timeout_seconds)),
            headers={"Authorization": f"Bearer {s.ai_provider_api_key}", "Content-Type": "application/json",
                     "User-Agent": "vip-customs-ai/http-llm"},
            transport=transport,
        )
        self._health_cache: tuple[float, ProviderHealth] | None = None

    # ------------------------------------------------------------------ transport
    def _complete(self, messages: list[dict[str, str]], capability: str) -> tuple[dict[str, Any], CallMeta]:
        """One logical call: budget check → bounded retries → JSON body. Raises ProviderError subclasses.

        Accounting: exactly ONE ledger record per logical call. Failures are recorded here; a successful
        transport call is recorded by `_validate` once the payload has passed (or failed) schema validation.
        """
        s = self.settings
        meta = CallMeta(correlation_id=str(uuid.uuid4()), capability=capability, provider=self.name, model=self.model)
        ACCOUNTANT.check_budget(s.ai_daily_budget_usd, capability)
        body = {"model": self.model, "messages": messages, "temperature": 0, "response_format": {"type": "json_object"}}
        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, s.ai_max_retries + 2):
            meta.attempts = attempt
            try:
                resp = self._client.post("/chat/completions", json=body, headers={"X-Request-ID": meta.correlation_id})
            except httpx.TimeoutException as exc:
                last_error = ProviderTimeout(f"timeout after {s.ai_timeout_seconds}s (attempt {attempt})")
                log.warning("ai_timeout correlation_id=%s attempt=%d", meta.correlation_id, attempt)
                last_error.__cause__ = exc
            except httpx.HTTPError as exc:
                last_error = ProviderUnavailable(f"transport error {type(exc).__name__} (attempt {attempt})")
                last_error.__cause__ = exc
            else:
                if resp.status_code in RETRY_STATUS:
                    last_error = ProviderUnavailable(f"HTTP {resp.status_code} (attempt {attempt})")
                elif resp.status_code >= 400:
                    meta.outcome = "unavailable"
                    self._finish(meta, started, record=True)
                    raise ProviderUnavailable(f"HTTP {resp.status_code} from provider (not retryable)")
                else:
                    try:
                        payload = self._parse_envelope(resp, meta)
                    except ProviderInvalidOutput:
                        self._finish(meta, started, record=True)
                        raise
                    self._finish(meta, started, record=False)
                    return payload, meta
            if attempt <= s.ai_max_retries:
                time.sleep(min(2.0 ** (attempt - 1) * 0.5, 4.0))
        meta.outcome = "timeout" if isinstance(last_error, ProviderTimeout) else "unavailable"
        self._finish(meta, started, record=True)
        raise last_error or ProviderUnavailable("provider call failed")

    def _parse_envelope(self, resp: httpx.Response, meta: CallMeta) -> dict[str, Any]:
        try:
            env = resp.json()
            usage = env.get("usage") or {}
            meta.input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            meta.output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            meta.cost_usd = estimate_cost(meta.input_tokens, meta.output_tokens, self.settings.ai_cost_per_1k_input_tokens_usd,
                                          self.settings.ai_cost_per_1k_output_tokens_usd)
            content = env["choices"][0]["message"]["content"]
            data = json.loads(content) if isinstance(content, str) else content
            if not isinstance(data, dict):
                raise TypeError("content is not a JSON object")
            return data
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            meta.outcome = "invalid_output"
            log.warning("ai_invalid_envelope correlation_id=%s detail=%s body=%s", meta.correlation_id, type(exc).__name__,
                        describe_payload(resp.content))
            raise ProviderInvalidOutput(f"provider response is not a JSON object: {type(exc).__name__}") from exc

    def _finish(self, meta: CallMeta, started: float, *, record: bool) -> None:
        meta.latency_ms = int((time.monotonic() - started) * 1000)
        if record:
            ACCOUNTANT.record(meta)

    @staticmethod
    def _validate(model: type[BaseModel], data: dict[str, Any], meta: CallMeta):
        try:
            out = model.model_validate(data)
        except ValidationError as exc:
            meta.outcome = "invalid_output"
            ACCOUNTANT.record(meta)
            raise ProviderInvalidOutput(f"provider output failed schema validation: {exc.error_count()} error(s)") from exc
        ACCOUNTANT.record(meta)
        return out

    # ------------------------------------------------------------------ capabilities
    def extract_document(self, doc_type: str, filename: str, content: bytes) -> ExtractionResult:
        result = ExtractionResult(doc_type=doc_type, provider=self.name, provider_version=self.version)
        if len(content) > self.settings.ai_max_document_bytes:
            raise ProviderUnavailable(f"document exceeds AI_MAX_DOCUMENT_BYTES ({len(content)} bytes); refused, not truncated")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            result.warnings.append("Binary/scanned document: no OCR provider configured; manual review required")
            return result
        from app.services.mapping import KNOWN_SOURCE_KEYS

        data, meta = self._complete(prompts.extract_messages(doc_type, filename, text, sorted(KNOWN_SOURCE_KEYS)), "document_ai")
        out = self._validate(_ExtractionOut, data, meta)
        result.values = [ExtractedValue(v.key, v.value.strip(), round(v.confidence, 3), v.source_ref, v.method or "llm.extract")
                         for v in out.values]
        result.warnings = list(out.warnings) + [f"correlation_id={meta.correlation_id}"]
        return result

    def propose_description(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        data, meta = self._complete(prompts.describe_messages(item), "hs_ai")
        out = self._validate(_DescribeOut, data, meta)
        return out.description.strip(), list(out.reasoning) + [f"[http-llm correlation_id={meta.correlation_id}]"]

    def answer_case_question(self, question: str, context: dict[str, Any]) -> CopilotAnswer:
        data, meta = self._complete(prompts.copilot_messages(question, context), "copilot")
        out = self._validate(_CopilotOut, data, meta)
        return CopilotAnswer(answer=out.answer.strip(), intent=out.intent, sources=[s.model_dump() for s in out.sources],
                             reasoning=list(out.reasoning) + [f"[http-llm correlation_id={meta.correlation_id}]"], provider=self.name,
                             confidence=out.confidence, recommended_actions=list(out.recommended_actions),
                             requires_review=True)  # a real model never bypasses review, whatever it claims

    # ------------------------------------------------------------------ health
    def health(self, *, live: bool = True) -> ProviderHealth:
        now = time.monotonic()
        if self._health_cache and now - self._health_cache[0] < HEALTH_CACHE_SECONDS:
            return self._health_cache[1]
        if not live:
            return ProviderHealth(self.capability, self.name, self.version, configured=True, healthy=True, detail="configured (not probed)")
        try:
            resp = self._client.get("/models", timeout=httpx.Timeout(5.0))
            healthy = resp.status_code < 400
            detail = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            healthy, detail = False, f"probe failed: {type(exc).__name__}"
        h = ProviderHealth(self.capability, self.name, self.version, configured=True, healthy=healthy, detail=detail)
        self._health_cache = (now, h)
        return h
