"""HS-code keyed lookups with longest-prefix matching (G18B, B-02 follow-up).

Demo datasets are keyed by 4-digit heading; an authoritative national schedule is keyed by 8-digit
tariff lines (sometimes 6 or 10). `lookup` tries the full code first, then successively shorter
prefixes down to the 4-digit heading, so one evaluator works with either depth and a mixed dataset
(8-digit lines plus 4-digit defaults) resolves the most specific entry. The matched key is returned so
reasoning can cite it.
"""

from __future__ import annotations

from typing import Any

MIN_PREFIX = 4


def normalise(hs_code: str | None) -> str:
    return "".join(ch for ch in (hs_code or "") if ch.isdigit())


def lookup[V](mapping: dict[str, V] | None, hs_code: str | None) -> tuple[str, V] | None:
    """Return (matched_key, value) for the longest key that prefixes `hs_code`, or None."""
    if not mapping:
        return None
    code = normalise(hs_code)
    if len(code) < MIN_PREFIX:
        return None
    for n in range(len(code), MIN_PREFIX - 1, -1):
        key = code[:n]
        if key in mapping:
            return key, mapping[key]
    return None


def lookup_value(mapping: dict[str, Any] | None, hs_code: str | None, default: Any = None) -> Any:
    hit = lookup(mapping, hs_code)
    return hit[1] if hit else default
