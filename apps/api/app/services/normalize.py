import re
import unicodedata
from decimal import Decimal, InvalidOperation


def strip_accents(s: str) -> str:
    s = s.replace("Đ", "D").replace("đ", "d")
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = strip_accents(s).upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).upper()


def parse_decimal(s: str | None) -> Decimal | None:
    if s is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", s.replace(",", ""))
    if cleaned in {"", "-", "."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
