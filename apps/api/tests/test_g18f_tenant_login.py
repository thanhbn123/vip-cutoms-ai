"""G18F — tenant-aware login (D-042): e-mail unique per tenant, optional tenant code, no cross-tenant oracle."""

from __future__ import annotations

from sqlalchemy import select

from app.core import ratelimit
from app.core.ratelimit import LoginLimiters, SlidingWindowLimiter
from app.core.security import hash_password
from app.db import get_sessionmaker
from app.models.audit import AuditEvent
from app.models.identity import User

PW = "correct-horse-battery"
SHARED = "shared@both.test"


def _login(client, email, password, tenant=None):
    body = {"email": email, "password": password}
    if tenant is not None:
        body["tenant"] = tenant
    return client.post("/api/v1/auth/login", json=body)


def _add_user(world, tenant: str, email: str, password: str, role="OPERATOR") -> User:
    db = get_sessionmaker()()
    try:
        u = User(tenant_id=getattr(world, f"tenant_{tenant}").id, email=email, full_name=f"{email} {tenant}", role=role,
                 password_hash=hash_password(password))
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def test_same_email_can_exist_in_two_tenants_and_tenant_code_selects_the_account(world, client):
    a = _add_user(world, "T1", SHARED, PW)
    b = _add_user(world, "T2", SHARED, PW)
    r1 = _login(client, SHARED, PW, tenant="T1")
    r2 = _login(client, SHARED, PW, tenant="t2")  # tenant code is case-insensitive
    assert r1.status_code == 200 and r1.json()["user"]["tenant_id"] == str(a.tenant_id) and r1.json()["user"]["tenant_code"] == "T1"
    assert r2.status_code == 200 and r2.json()["user"]["tenant_id"] == str(b.tenant_id) and r2.json()["user"]["tenant_code"] == "T2"
    # each token is bound to its own tenant
    me1 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r1.json()['access_token']}"}).json()
    assert me1["user"]["id"] == str(a.id) and me1["user"]["tenant_code"] == "T1"
    cases = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {r2.json()['access_token']}"})
    assert cases.status_code == 200


def test_unique_email_logs_in_without_tenant_code(world, client):
    r = _login(client, "operator@t1.test", PW)
    assert r.status_code == 200 and r.json()["user"]["tenant_code"] == "T1"
    # naming the right tenant works too; naming another tenant does not (generic 401, no hint)
    assert _login(client, "operator@t1.test", PW, tenant="T1").status_code == 200
    r = _login(client, "operator@t1.test", PW, tenant="T2")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    r = _login(client, "operator@t1.test", PW, tenant="NOPE")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_ambiguous_email_with_same_password_needs_tenant_code_but_wrong_password_stays_generic(world, client):
    _add_user(world, "T1", SHARED, PW)
    _add_user(world, "T2", SHARED, PW)
    r = _login(client, SHARED, PW)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "TENANT_REQUIRED"
    assert r.json()["detail"]["details"]["tenants"] == ["T1", "T2"]  # only disclosed to the password holder
    r = _login(client, SHARED, "wrong-password")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "INVALID_CREDENTIALS" and "tenants" not in str(r.json())


def test_ambiguous_email_with_different_passwords_resolves_by_password(world, client):
    a = _add_user(world, "T1", SHARED, "password-for-t1")
    b = _add_user(world, "T2", SHARED, "password-for-t2")
    r = _login(client, SHARED, "password-for-t1")
    assert r.status_code == 200 and r.json()["user"]["id"] == str(a.id)
    r = _login(client, SHARED, "password-for-t2")
    assert r.status_code == 200 and r.json()["user"]["id"] == str(b.id)


def test_inactive_account_does_not_count_as_candidate(world, client):
    _add_user(world, "T1", SHARED, PW)
    inactive = _add_user(world, "T2", SHARED, PW)
    db = get_sessionmaker()()
    try:
        db.get(User, inactive.id).is_active = False
        db.commit()
    finally:
        db.close()
    r = _login(client, SHARED, PW)  # only one ACTIVE account → unambiguous
    assert r.status_code == 200 and r.json()["user"]["tenant_code"] == "T1"
    assert _login(client, SHARED, PW, tenant="T2").status_code == 401


def test_admin_can_create_an_email_that_exists_in_another_tenant_and_only_sees_own_tenant(world, client):
    body = {"email": "newcomer@example.test", "full_name": "N", "role": "REVIEWER", "password": "0123456789ab"}
    r = client.post("/api/v1/users", json=body, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 201 and r.json()["tenant_code"] == "T1"
    # the T2 admin cannot learn that the address exists in T1: creation succeeds (no 409 oracle)
    r = client.post("/api/v1/users", json=body, headers=world.h("ADMIN", "T2"))
    assert r.status_code == 201 and r.json()["tenant_code"] == "T2"
    # within one tenant the e-mail is still unique
    r = client.post("/api/v1/users", json=body, headers=world.h("ADMIN", "T2"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DUPLICATE"
    emails = [u["email"] for u in client.get("/api/v1/users", headers=world.h("OPERATOR", "T1")).json()]
    assert emails.count("newcomer@example.test") == 1
    assert _login(client, "newcomer@example.test", "0123456789ab").status_code == 401  # ambiguous → tenant code needed
    assert _login(client, "newcomer@example.test", "0123456789ab", tenant="T2").status_code == 200


def test_db_constraint_is_per_tenant(world):
    _add_user(world, "T1", SHARED, PW)
    _add_user(world, "T2", SHARED, PW)
    db = get_sessionmaker()()
    try:
        db.add(User(tenant_id=world.tenant_T1.id, email=SHARED, full_name="dup", role="OPERATOR", password_hash=hash_password(PW)))
        try:
            db.commit()
            raise AssertionError("duplicate e-mail within one tenant must be rejected by the database")
        except Exception as exc:  # noqa: BLE001
            assert "uq_users_tenant_email" in str(exc)
            db.rollback()
    finally:
        db.close()


def _lims(pair=10, email=50, ip=100) -> LoginLimiters:
    return LoginLimiters(pair=SlidingWindowLimiter(pair, 300, 120), email=SlidingWindowLimiter(email, 300, 120),
                         ip=SlidingWindowLimiter(ip, 300, 120))


def test_tenant_code_does_not_grant_a_fresh_throttle_budget_and_lock_is_audited_per_candidate(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=3))
    a = _add_user(world, "T1", SHARED, PW)
    b = _add_user(world, "T2", SHARED, PW)
    assert _login(client, SHARED, "x", tenant="T1").status_code == 401
    assert _login(client, SHARED, "x", tenant="T2").status_code == 401
    assert _login(client, SHARED, "x").status_code == 429  # third failure on the same pair key regardless of tenant
    assert _login(client, SHARED, PW, tenant="T1").status_code == 429
    db = get_sessionmaker()()
    try:
        ev = db.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_locked")).scalars().all()
        assert sorted(e.entity_id for e in ev) == sorted([str(a.id), str(b.id)])
    finally:
        db.close()


def test_tenant_required_counts_as_a_failed_attempt(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", _lims(pair=2))
    _add_user(world, "T1", SHARED, PW)
    _add_user(world, "T2", SHARED, PW)
    assert _login(client, SHARED, PW).json()["detail"]["code"] == "TENANT_REQUIRED"
    assert _login(client, SHARED, PW).status_code == 429
