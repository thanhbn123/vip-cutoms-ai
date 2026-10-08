"""Provider-neutral contracts for AI capabilities.

Everything a provider returns is *untrusted* structured input: services validate it before
anything is persisted (see docs/AI_RULES.md "Prompt/provider separation").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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


class AIProvider(Protocol):
    name: str
    version: str

    def extract_document(self, doc_type: str, filename: str, content: bytes) -> ExtractionResult: ...

    def propose_description(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        """Return (proposed customs description, reasoning lines). Never applied without review."""
        ...

    def answer_case_question(self, question: str, context: dict[str, Any]) -> CopilotAnswer: ...
