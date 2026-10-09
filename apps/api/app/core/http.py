"""HTTP helpers (G18B)."""

from __future__ import annotations

import re
from urllib.parse import quote

_ASCII_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """RFC 6266 / RFC 5987 Content-Disposition with a quoted ASCII fallback and a UTF-8 `filename*`.

    The previous f-string interpolation put the raw filename inside double quotes, so a name containing
    `"` or a non-ASCII character produced an invalid or truncated header. The fallback keeps only safe
    ASCII characters; the full name travels in `filename*`.
    """
    base = filename.strip().replace("\r", "").replace("\n", "") or "download"
    ascii_name = _ASCII_SAFE.sub("_", base.encode("ascii", "ignore").decode() or "download") or "download"
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(base, safe='')}"
