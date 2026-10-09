"""Logging/redaction policy for AI provider traffic (G18, see docs/G18_AI_PROVIDER_SECURITY.md).

Rule: provider request and response BODIES are never written to logs, audit evidence or
metrics. Only shape and accounting data are (lengths, counts, latency, status, correlation id).
`describe_payload` is the one helper that turns a body into something loggable.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Patterns that must never survive into a log line even when a caller passes free text.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"\b\d{8,}\b")  # tax codes, invoice/BL numbers, phone numbers, account numbers
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
_API_KEY_LIKE = re.compile(r"\b(sk|key|token)[-_][A-Za-z0-9]{12,}\b")


def redact(text: str) -> str:
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _API_KEY_LIKE.sub("[REDACTED_KEY]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    return _LONG_DIGITS.sub("[NUMBER]", text)


def describe_payload(payload: bytes | str | dict[str, Any] | None) -> dict[str, Any]:
    """Loggable description of a body: size and a fingerprint, never the content."""
    if payload is None:
        return {"bytes": 0, "sha256_12": None}
    if isinstance(payload, dict):
        import json

        payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    data = payload.encode("utf-8", "replace") if isinstance(payload, str) else payload
    return {"bytes": len(data), "sha256_12": hashlib.sha256(data).hexdigest()[:12]}
