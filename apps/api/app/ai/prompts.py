"""Prompt templates for the real LLM adapter. Kept apart from business rules on purpose
(CLAUDE.md: "Keep business rules separate from LLM prompts/providers").

Every prompt demands STRICT JSON matching a schema that app.ai.http_llm_provider validates. The
model is told what it must NOT do (invent values, fill gaps, answer outside the context). The
business layer re-validates everything anyway: unknown keys, out-of-range confidence and empty
values are rejected in app.services.mapping / app.services.copilot.
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_EXTRACT = (
    "You are a customs-document extraction engine. You receive the text of ONE trade document. "
    "Return STRICT JSON only, no prose. Extract only values literally present in the text; never infer, "
    "never fill a missing field, never normalise currencies or dates beyond trimming whitespace. "
    "Each value must carry the exact line reference where it appears and a confidence between 0 and 1. "
    "If the document is unreadable or not of the stated type, return an empty values list and a warning."
)

SYSTEM_DESCRIBE = (
    "You draft customs goods descriptions in Vietnamese for a human reviewer. Use ONLY the item data given. "
    "Return STRICT JSON {\"description\": string, \"reasoning\": [string]}. Do not add technical attributes that are "
    "not in the input. Mark every assumption explicitly in reasoning; the reviewer decides."
)

SYSTEM_COPILOT = (
    "You are the Customs Copilot for a brokerage reviewer. Answer in Vietnamese using ONLY the structured case "
    "context provided. Cite sources by their ids from the context. If the context does not contain the answer, say "
    "so explicitly. Never state a tariff rate, HS code or legal requirement that is not in the context. Return STRICT "
    "JSON {\"answer\": string, \"intent\": string, \"sources\": [{\"type\": string, \"id\": string, \"label\": string}], "
    "\"reasoning\": [string], \"confidence\": number, \"recommended_actions\": [string], \"requires_review\": boolean}."
)

EXTRACT_SCHEMA_HINT = {
    "doc_type": "string (echo the stated type)",
    "values": [{"key": "dotted key, e.g. invoice.number or items[1].description", "value": "string", "confidence": "0..1",
                "source_ref": "e.g. line:12", "method": "llm.extract"}],
    "warnings": ["string"],
}


def extract_messages(doc_type: str, filename: str, text: str, allowed_keys: list[str]) -> list[dict[str, str]]:
    user = {"doc_type": doc_type, "filename": filename, "allowed_keys": allowed_keys, "output_schema": EXTRACT_SCHEMA_HINT,
            "document_text": text}
    return [{"role": "system", "content": SYSTEM_EXTRACT}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]


def describe_messages(item: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_DESCRIBE}, {"role": "user", "content": json.dumps({"item": item}, ensure_ascii=False)}]


def copilot_messages(question: str, context: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_COPILOT},
            {"role": "user", "content": json.dumps({"question": question, "context": context}, ensure_ascii=False)}]
