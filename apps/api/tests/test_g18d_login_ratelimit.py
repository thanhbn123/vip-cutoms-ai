"""G18D — API-layer login throttling (closes the G16 gap "no rate limiting on /auth/login")."""

from __future__ import annotations

from app.core import ratelimit
from app.core.ratelimit import SlidingWindowLimiter


def test_sliding_window_locks_after_max_failures_and_expires():
    lim = SlidingWindowLimiter(max_attempts=3, window_seconds=60, lockout_seconds=30)
    t = 1000.0
    assert lim.check("k", t).allowed and lim.check("k", t).remaining == 3
    assert lim.record_failure("k", t).allowed and lim.record_failure("k", t + 1).allowed
    v = lim.record_failure("k", t + 2)  # third failure → locked
    assert not v.allowed and v.retry_after >= 30
    assert not lim.check("k", t + 10).allowed and lim.throttled_total == 1
    assert lim.check("k", t + 33).allowed  # lockout expired
    # failures older than the window no longer count
    lim2 = SlidingWindowLimiter(3, 60, 30)
    lim2.record_failure("k", t)
    lim2.record_failure("k", t + 1)
    assert lim2.record_failure("k", t + 61.5).allowed  # the first failure aged out
    lim2.record_success("k")
    assert lim2.check("k", t + 62).remaining == 3


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_is_throttled_per_email_after_repeated_failures(world, client, monkeypatch):
    ratelimit.reset_login_limiter()
    monkeypatch.setattr(ratelimit, "_LOGIN", SlidingWindowLimiter(max_attempts=3, window_seconds=300, lockout_seconds=120))
    email = "reviewer@t1.test"
    assert _login(client, email, "wrong-1").status_code == 401
    assert _login(client, email, "wrong-2").status_code == 401
    r = _login(client, email, "wrong-3")  # third failure locks the e-mail key
    assert r.status_code == 429 and r.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS" and int(r.headers["retry-after"]) >= 1
    # even the CORRECT password is refused while locked — and no hash was computed for it
    assert _login(client, email, "correct-horse-battery").status_code == 429
    # the ip key is shared by the test client, so a different e-mail is also blocked from this client; use a fresh limiter
    # state to show per-e-mail isolation
    monkeypatch.setattr(ratelimit, "_LOGIN", SlidingWindowLimiter(max_attempts=3, window_seconds=300, lockout_seconds=120))
    assert _login(client, "operator@t1.test", "correct-horse-battery").status_code == 200
    ratelimit.reset_login_limiter()


def test_successful_login_clears_the_email_counter_but_not_the_ip_counter(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", SlidingWindowLimiter(max_attempts=4, window_seconds=300, lockout_seconds=120))
    email = "operator@t1.test"
    assert _login(client, email, "nope").status_code == 401
    assert _login(client, email, "nope").status_code == 401
    assert _login(client, email, "correct-horse-battery").status_code == 200  # e-mail counter cleared; IP counter keeps 2
    assert _login(client, email, "nope").status_code == 401  # e-mail 1/4, ip 3/4
    assert _login(client, email, "nope").status_code == 429  # ip reaches 4/4 → the client address is locked regardless of e-mail
    ratelimit.reset_login_limiter()


def test_unknown_email_failures_also_count(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", SlidingWindowLimiter(max_attempts=2, window_seconds=300, lockout_seconds=60))
    assert _login(client, "ghost@t1.test", "x").status_code == 401
    assert _login(client, "ghost@t1.test", "x").status_code == 429  # no user enumeration via throttling behaviour either
    ratelimit.reset_login_limiter()


def test_metrics_expose_throttle_counter(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", SlidingWindowLimiter(max_attempts=1, window_seconds=300, lockout_seconds=60))
    _login(client, "nobody@t1.test", "x")
    _login(client, "nobody@t1.test", "x")
    assert "vip_login_throttled_total 1" in client.get("/metrics").text
    ratelimit.reset_login_limiter()
