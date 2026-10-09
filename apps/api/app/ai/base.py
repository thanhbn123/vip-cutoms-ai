"""Provider-neutral contracts for AI capabilities.

Everything a provider returns is *untrusted* structured input: services validate it before
anything is persisted (see docs/AI_RULES.md "Prompt/provider separation").

G18 splits the single `AIProvider` into four capabilities so each can be sourced independently:

    DocumentOcrProvider         bytes → text (scanned documents)
    DocumentExtractionProvider  text/bytes → structured fields with source refs and confidence
    HsReasoningProvider         item → proposed customs description + reasoning
    CopilotProvider             question + case context → grounded answer

A single object may implement several of them (the mock implements all four). Business logic
never imports a vendor SDK: it depends on these protocols via app.ai.gateway only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ExtractedValue:
    key: str  # e.g. "invoice.number", "items[1].description"
    value: str
    confidence: float  # 0..1
    source_ref: str  # page/line/region locator inside the source document
    method: str  # e.g. "mock.regex", "ocr.layout", "llm.extract"


@dataclass
class ExtractionResult:
    doc_type: str
    provider: str
    provider_version: str
    values: list[ExtractedValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotAnswer:
    answer: str
    intent: str
    sources: list[dict[str, Any]]
    reasoning: list[str]
    provider: str
    proposal: dict[str, Any] | None = None  # optional change proposal; always requires reviewer approval
    confidence: float = 0.0  # how well the answer is grounded in case data (deterministic for the mock)
    recommended_actions: list[str] = field(default_factory=list)
    requires_review: bool = True  # anything touching a critical decision needs a reviewer


@dataclass
class OcrResult:
    text: str
    pages: int
    provider: str
    provider_version: str
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderHealth:
    capability: str
    name: str
    version: str
    configured: bool  # credentials/endpoint present (or not needed, for the mock)
    healthy: bool  # usable right now
    detail: str = ""
    is_mock: bool = False


@dataclass
class CallMeta:
    """Accounting record for one provider call. Never contains document or prompt content."""

    correlation_id: str
    capability: str
    provider: str
    model: str | None = None
    attempts: int = 1
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    outcome: str = "ok"  # ok | invalid_output | timeout | unavailable | budget_exceeded


# --- errors (all fail closed; callers never substitute a guessed answer) -----------------------
class ProviderError(RuntimeError):
    """Base: the provider could not deliver a validated result."""


class ProviderUnavailable(ProviderError):
    """Network/HTTP failure after retries, or provider not healthy."""


class ProviderTimeout(ProviderUnavailable):
    pass


class ProviderInvalidOutput(ProviderError):
    """Provider answered, but the payload failed schema validation. Treated as NO answer."""


class ProviderBudgetExceeded(ProviderError):
    """Daily cost budget reached; calls are refused until the budget window resets."""


# --- capability protocols ----------------------------------------------------------------------
@runtime_checkable
class DocumentOcrProvider(Protocol):
    name: str
    version: str

    def ocr(self, filename: str, content: bytes, *, correlation_id: str | None = None) -> OcrResult: ...

    def health(self) -> ProviderHealth: ...


@runtime_checkable
class DocumentExtractionProvider(Protocol):
    name: str
    version: str

    def extract_document(self, doc_type: str, filename: str, content: bytes) -> ExtractionResult: ...

    def health(self) -> ProviderHealth: ...


@runtime_checkable
class HsReasoningProvider(Protocol):
    name: str
    version: str

    def propose_description(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        """Return (proposed customs description, reasoning lines). Never applied without review."""
        ...

    def health(self) -> ProviderHealth: ...


@runtime_checkable
class CopilotProvider(Protocol):
    name: str
    version: str

    def answer_case_question(self, question: str, context: dict[str, Any]) -> CopilotAnswer: ...

    def health(self) -> ProviderHealth: ...


class AIProvider(DocumentExtractionProvider, HsReasoningProvider, CopilotProvider, Protocol):
    """Legacy umbrella: one object offering extraction, HS reasoning and Copilot (kept for callers)."""
