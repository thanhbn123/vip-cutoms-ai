"""Auth scaffold: PBKDF2 password hashing + HMAC-SHA256 signed bearer tokens (stdlib only).

Replaceable by an OIDC identity provider later; the rest of the app only depends on
`decode_token()` returning (user_id, tenant_id, role).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time

from app.core.config import get_settings

_ITER = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(body: str) -> str:
    key = get_settings().resolved_secret().encode()
    return _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def issue_token(user_id: str, tenant_id: str, role: str, ttl: int | None = None) -> str:
    ttl = ttl or get_settings().token_ttl_seconds
    now = int(time.time())
    payload = {"sub": user_id, "tid": tenant_id, "role": role, "iat": now, "exp": now + ttl}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body)}"


class InvalidToken(Exception):
    pass


def decode_token(token: str) -> dict:
    try:
        body, sig = token.split(".")
    except ValueError as exc:
        raise InvalidToken("malformed") from exc
    if not hmac.compare_digest(sig, _sign(body)):
        raise InvalidToken("bad signature")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:  # G18B: a signed-but-garbled body is 401, never 500
        raise InvalidToken("malformed payload") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str) or not isinstance(payload.get("tid"), str):
        raise InvalidToken("malformed payload")
    if not isinstance(payload.get("exp"), (int, float)) or payload["exp"] < time.time():
        raise InvalidToken("expired")
    return payload
