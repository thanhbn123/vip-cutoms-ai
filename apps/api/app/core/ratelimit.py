"""In-process sliding-window rate limiter for credential endpoints (G18D, hardened in G18E).

Closes the G16 gap "no rate limiting on /auth/login" at the API layer, independent of the proxy decision
(B-06). Three dimensions, each with its own threshold, applied in `POST /auth/login`:

    pair   ip+e-mail   LOGIN_MAX_ATTEMPTS (10)        the ordinary brute-force brake; locks only that client for that account
    email  e-mail      LOGIN_EMAIL_MAX_ATTEMPTS (50)  distributed brute force against one account (many IPs)
    ip     client IP   LOGIN_IP_MAX_ATTEMPTS (100)    one client spraying many accounts; 0 disables (shared NAT / upstream proxy)

Scope and limits, stated plainly:

* in-process (one `api` container today); a second replica would get its own counters. A shared store is the
  follow-up if the deployment ever scales out, and the proxy can add a second layer.
* counts FAILED attempts only. A successful login clears the pair and e-mail keys for that account. The IP key
  is not cleared by a success.
* a locked key is refused BEFORE the password hash is checked, so a locked key costs no PBKDF2 work.
* account-lockout DoS: an attacker who knows an e-mail can keep it locked only by sustaining
  LOGIN_EMAIL_MAX_ATTEMPTS failures per window from rotating addresses (the pair key alone never locks the
  victim's own client). That residual risk is documented; the stronger mitigations (CAPTCHA, proxy-layer
  limits, SSO) belong to the owner's production decisions (B-06, D-012).
* memory is bounded: at most LOGIN_MAX_TRACKED_KEYS (20 000) keys are kept; stale keys are swept and, if still
  over the cap, the oldest keys are evicted — unique random e-mails cannot grow the process without bound.
* the key text is never logged with the password; the audit trail records lockouts of known accounts.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    retry_after: int = 0
    remaining: int = 0
    locked_now: bool = False  # True on the failure that tripped the lock


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: float, lockout_seconds: float, *, max_keys: int = 20_000):
        self.max_attempts = int(max_attempts)  # 0 → this dimension is disabled
        self.window = float(window_seconds)
        self.lockout = float(lockout_seconds)
        self.max_keys = max(100, int(max_keys))
        self._lock = threading.Lock()
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()  # insertion/touch order → cheap oldest-eviction
        self._locked_until: dict[str, float] = {}
        self.throttled_total = 0
        self.locks_total = 0
        self.evicted_total = 0

    @property
    def enabled(self) -> bool:
        return self.max_attempts > 0

    # ------------------------------------------------------------------ housekeeping
    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures.get(key)
        if q is None:
            q = deque()
        while q and now - q[0] > self.window:
            q.popleft()
        if q:
            self._failures[key] = q
            self._failures.move_to_end(key)
        else:
            self._failures.pop(key, None)
        return q

    def _sweep(self, now: float) -> None:
        """Drop expired lockouts and stale failure keys; if still over the cap, evict the oldest-touched keys."""
        for k in [k for k, u in self._locked_until.items() if now >= u]:
            self._locked_until.pop(k, None)
        for k in [k for k, q in self._failures.items() if not q or now - q[-1] > self.window]:
            self._failures.pop(k, None)
        while len(self._failures) > self.max_keys:
            self._failures.popitem(last=False)
            self.evicted_total += 1

    # ------------------------------------------------------------------ API
    def check(self, key: str, now: float | None = None) -> Verdict:
        if not self.enabled:
            return Verdict(True, remaining=0)
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
        if not self.enabled:
            return Verdict(True, remaining=0)
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._failures) >= self.max_keys:
                self._sweep(now)
            q = self._prune(key, now)
            q.append(now)
            self._failures[key] = q
            self._failures.move_to_end(key)
            while len(self._failures) > self.max_keys:  # hard cap AFTER insertion: the newest key is never the one evicted
                self._failures.popitem(last=False)
                self.evicted_total += 1
            if len(q) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout
                self.locks_total += 1
                self.throttled_total += 1  # the refusal returned for this very attempt counts too (G18E)
                return Verdict(False, retry_after=int(self.lockout) + 1, locked_now=True)
            return Verdict(True, remaining=self.max_attempts - len(q))

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._failures)

    def reset(self) -> None:  # tests only
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()
            self.throttled_total = self.locks_total = self.evicted_total = 0


@dataclass
class LoginLimiters:
    pair: SlidingWindowLimiter
    email: SlidingWindowLimiter
    ip: SlidingWindowLimiter

    @property
    def throttled_total(self) -> int:
        return self.pair.throttled_total + self.email.throttled_total + self.ip.throttled_total

    @property
    def locks_total(self) -> int:
        return self.pair.locks_total + self.email.locks_total + self.ip.locks_total

    def reset(self) -> None:
        for lim in (self.pair, self.email, self.ip):
            lim.reset()


_LOGIN: LoginLimiters | None = None


def login_limiters() -> LoginLimiters:
    """Process-wide limiters built from settings on first use (tests rebuild them via reset_login_limiter)."""
    global _LOGIN
    if _LOGIN is None:
        from app.core.config import get_settings

        s = get_settings()
        _LOGIN = LoginLimiters(
            pair=SlidingWindowLimiter(s.login_max_attempts, s.login_window_seconds, s.login_lockout_seconds, max_keys=s.login_max_tracked_keys),
            email=SlidingWindowLimiter(s.login_email_max_attempts, s.login_window_seconds, s.login_lockout_seconds, max_keys=s.login_max_tracked_keys),
            ip=SlidingWindowLimiter(s.login_ip_max_attempts, s.login_window_seconds, s.login_lockout_seconds, max_keys=s.login_max_tracked_keys),
        )
    return _LOGIN


def reset_login_limiter() -> None:
    global _LOGIN
    _LOGIN = None
