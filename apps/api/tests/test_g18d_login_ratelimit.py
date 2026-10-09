"""G18D/G18E — API-layer login throttling (closes the G16 gap "no rate limiting on /auth/login")."""

from __future__ import annotations

from sqlalchemy import select

from app.core import ratelimit
from app.core.ratelimit import LoginLimiters, SlidingWindowLimiter
from app.db import get_sessionmaker
from app.models.audit import AuditEvent


def test_sliding_window_locks_after_max_failures_and_expires():
    lim = SlidingWindowLimiter(max_attempts=3, window_seconds=60, lockout_seconds=30)
    t = 1000.0
    assert lim.check("k", t).allowed and lim.check("k", t).remaining == 3
    assert lim.record_failure("k", t).allowed and lim.record_failure("k", t + 1).allowed
    v = lim.record_failure("k", t + 2)  # third failure → locked, and that refusal is counted
    assert not v.allowed and v.locked_now and v.retry_after >= 30 and lim.throttled_total == 1 and lim.locks_total == 1
    assert not lim.check("k", t + 10).allowed and lim.throttled_total == 2
    assert lim.check("k", t + 33).allowed  # lockout expired
    lim2 = SlidingWindowLimiter(3, 60, 30)
    lim2.record_failure("k", t)
    lim2.record_failure("k", t + 1)
    assert lim2.record_failure("k", t + 61.5).allowed  # the first failure aged out
    lim2.record_success("k")
    assert lim2.check("k", t + 62).remaining == 3


def test_disabled_dimension_never_blocks():
    lim = SlidingWindowLimiter(max_attempts=0, window_seconds=60, lockout_seconds=30)
    for _ in range(50):
        assert lim.record_failure("k").allowed
    assert lim.check("k").allowed and lim.tracked_keys() == 0


def test_key_store_is_bounded_and_evicts_oldest():
    lim = SlidingWindowLimiter(max_attempts=5, window_seconds=600, lockout_seconds=60, max_keys=100)
    t = 1000.0
    for i in range(1000):
        lim.record_failure(f"email:random-{i}@evil.test", t + i * 0.001)
    assert lim.tracked_keys() <= 100 and lim.evicted_total >= 900
    assert lim.check("email:random-0@evil.test", t + 2).remaining == 5  # oldest key evicted → no stale state kept forever


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _lims(pair=10, email=50, ip=100, window=300, lockout=120) -> LoginLimiters:
    return LoginLimiters(pair=SlidingWindowLimiter(pair, window, lockout), email=SlidingWindowLimiter(email, window, lockout),
                         ip=SlidingWindowLimiter(ip, window, lockout))


def test_pair_dimension_locks_after_repeated_failures_and_refuses_even_the_correct_password(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=3))
    email = "reviewer@t1.test"
    assert _login(client, email, "wrong-1").status_code == 401
    assert _login(client, email, "wrong-2").status_code == 401
    r = _login(client, email, "wrong-3")  # third failure locks the (ip, e-mail) pair; this refusal is a 429
    assert r.status_code == 429 and r.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS" and int(r.headers["retry-after"]) >= 1
    assert _login(client, email, "correct-horse-battery").status_code == 429  # no hash work, no bypass
    # another account from the same client is NOT affected by the pair lock (the ip dimension has a much higher threshold)
    assert _login(client, "operator@t1.test", "correct-horse-battery").status_code == 200


def test_successful_login_clears_pair_and_email_counters_but_not_ip(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=4, email=50, ip=4))
    email = "operator@t1.test"
    assert _login(client, email, "nope").status_code == 401
    assert _login(client, email, "nope").status_code == 401
    assert _login(client, email, "correct-horse-battery").status_code == 200  # pair + e-mail cleared; ip keeps 2
    assert _login(client, email, "nope").status_code == 401  # pair 1/4, ip 3/4
    assert _login(client, email, "nope").status_code == 429  # ip reaches 4/4 → the client address is locked


def test_email_dimension_stops_distributed_brute_force(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=100, email=2, ip=0))  # ip disabled (shared NAT), pair effectively off
    assert _login(client, "senior@t1.test", "x").status_code == 401
    assert _login(client, "senior@t1.test", "x").status_code == 429  # e-mail dimension trips
    assert _login(client, "operator@t1.test", "correct-horse-battery").status_code == 200  # other accounts unaffected


def test_unknown_email_failures_also_count(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=2))
    assert _login(client, "ghost@t1.test", "x").status_code == 401
    assert _login(client, "ghost@t1.test", "x").status_code == 429  # no user enumeration via throttling behaviour either


def test_lockout_of_a_known_account_is_audited(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=2))
    _login(client, "reviewer@t1.test", "x")
    _login(client, "reviewer@t1.test", "x")
    db = get_sessionmaker()()
    try:
        ev = db.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_locked")).scalars().all()
        assert len(ev) == 1 and ev[0].actor_type == "SYSTEM" and ev[0].entity_id == str(world.users[("T1", "REVIEWER")].id)
        assert "pair" in ev[0].after["dimensions"]
    finally:
        db.close()


def test_metrics_expose_throttle_counters(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=1))
    _login(client, "nobody@t1.test", "x")  # locks at once → counted
    _login(client, "nobody@t1.test", "x")  # refused → counted
    body = client.get("/metrics").text
    assert "vip_login_throttled_total 2" in body and "vip_login_locks_total 1" in body and 'vip_login_tracked_keys{dimension="pair"}' in body
