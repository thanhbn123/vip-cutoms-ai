"""In-process sliding-window rate limiter for credential endpoints (G18D).

Closes the G16 gap "no rate limiting on /auth/login" at the API layer, independent of the proxy decision
(B-06). Scope and limits, stated plainly:

* in-process (one `api` container today); a second replica would get its own counters. A shared store is
  the follow-up if the deployment ever scales out, and the proxy can add a second layer.
* counts FAILED attempts per key (client IP and lower-cased e-mail). A successful login clears the e-mail key.
* when a key reaches `max_attempts` inside `window_seconds`, further attempts are refused with 429 and a
  `Retry-After` for `lockout_seconds`. The refusal happens BEFORE the password hash is checked, so a locked
  key costs no PBKDF2 work.
* keys are never logged with the password; only the count and the key are exposed through metrics as totals.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    retry_after: int = 0
    remaining: int = 0


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: float, lockout_seconds: float):
        self.max_attempts = max(1, int(max_attempts))
        self.window = float(window_seconds)
        self.lockout = float(lockout_seconds)
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self.throttled_total = 0

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            self._failures.pop(key, None)
        return q

    def check(self, key: str, now: float | None = None) -> Verdict:
        now = time.monotonic() if now is None else now
        with self._lock:
            until = self._locked_until.get(key)
            if until is not None:
                if now < until:
                    self.throttled_total += 1
                    return Verdict(False, retry_after=max(1, int(until - now) + 1))
                self._locked_until.pop(key, None)
            q = self._prune(key, now)
            return Verdict(True, remaining=max(0, self.max_attempts - len(q)))

    def record_failure(self, key: str, now: float | None = None) -> Verdict:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._prune(key, now)
            q.append(now)
            self._failures[key] = q
            if len(q) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout
                return Verdict(False, retry_after=int(self.lockout) + 1)
            return Verdict(True, remaining=self.max_attempts - len(q))

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:  # tests only
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()
            self.throttled_total = 0


_LOGIN: SlidingWindowLimiter | None = None


def login_limiter() -> SlidingWindowLimiter:
    """Process-wide limiter built from settings on first use (tests rebuild it via reset_login_limiter)."""
    global _LOGIN
    if _LOGIN is None:
        from app.core.config import get_settings

        s = get_settings()
        _LOGIN = SlidingWindowLimiter(s.login_max_attempts, s.login_window_seconds, s.login_lockout_seconds)
    return _LOGIN


def reset_login_limiter() -> None:
    global _LOGIN
    _LOGIN = None
