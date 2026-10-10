"""G18G — user lifecycle: ADMIN edits/deactivates/resets inside its tenant; self-service password change; token voiding."""

from __future__ import annotations

import time

from sqlalchemy import select

from app.core import ratelimit
from app.core.ratelimit import LoginLimiters, SlidingWindowLimiter
from app.core.security import issue_token
from app.db import get_sessionmaker
from app.models.audit import AuditEvent

PW = "correct-horse-battery"


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _audit(action):
    db = get_sessionmaker()()
    try:
        return db.execute(select(AuditEvent).where(AuditEvent.action == action)).scalars().all()
    finally:
        db.close()


def test_admin_renames_rerolls_deactivates_and_reactivates_a_colleague_with_audit(world, client):
    op = world.users[("T1", "OPERATOR")]
    r = client.patch(f"/api/v1/users/{op.id}", json={"full_name": "Nguyễn Văn A", "role": "REVIEWER", "reason": "promoted after training"},
                     headers=world.h("ADMIN", "T1"))
    assert r.status_code == 200 and r.json()["role"] == "REVIEWER" and r.json()["full_name"] == "Nguyễn Văn A" and r.json()["is_active"] is True
    # the role change applies to the existing token at once (permissions come from the DB row, not the token)
    assert "hs.decide" in client.get("/api/v1/auth/me", headers=world.h("OPERATOR", "T1")).json()["permissions"]
    r = client.patch(f"/api/v1/users/{op.id}", json={"is_active": False, "reason": "left the company"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=world.h("OPERATOR", "T1")).status_code == 401  # existing token dead
    assert _login(client, "operator@t1.test", PW).status_code == 401  # cannot log in
    r = client.patch(f"/api/v1/users/{op.id}", json={"is_active": True, "reason": "returned"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 200 and r.json()["is_active"] is True
    assert _login(client, "operator@t1.test", PW).status_code == 200
    ev = {e.action: e for e in _audit("user.updated") + _audit("user.deactivated") + _audit("user.reactivated")}
    assert set(ev) == {"user.updated", "user.deactivated", "user.reactivated"}
    assert ev["user.updated"].before["role"] == "OPERATOR" and ev["user.updated"].after["role"] == "REVIEWER" and ev["user.updated"].reason == "promoted after training"
    assert ev["user.deactivated"].actor_type == "USER" and ev["user.deactivated"].entity_id == str(op.id)


def test_guards_self_change_no_change_and_cross_tenant(world, client):
    adm = world.users[("T1", "ADMIN")]
    r = client.patch(f"/api/v1/users/{adm.id}", json={"is_active": False, "reason": "oops"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SELF_CHANGE_FORBIDDEN"
    r = client.patch(f"/api/v1/users/{adm.id}", json={"role": "OPERATOR", "reason": "oops"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SELF_CHANGE_FORBIDDEN"
    assert client.patch(f"/api/v1/users/{adm.id}", json={"full_name": "Admin One", "reason": "typo"}, headers=world.h("ADMIN", "T1")).status_code == 200
    op = world.users[("T1", "OPERATOR")]
    r = client.patch(f"/api/v1/users/{op.id}", json={"role": "OPERATOR", "reason": "same role"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NO_CHANGE"
    assert client.patch(f"/api/v1/users/{op.id}", json={"reason": "nothing"}, headers=world.h("ADMIN", "T1")).status_code == 422
    assert client.patch(f"/api/v1/users/{op.id}", json={"is_active": False, "reason": "x"}, headers=world.h("ADMIN", "T1")).status_code == 422  # reason too short
    # cross-tenant: the T2 admin sees T1 users as non-existent (no leak), and non-admins lack user.manage
    r = client.patch(f"/api/v1/users/{op.id}", json={"is_active": False, "reason": "cross"}, headers=world.h("ADMIN", "T2"))
    assert r.status_code == 404
    assert client.post(f"/api/v1/users/{op.id}/reset-password", json={"password": "0123456789zz", "reason": "cross"}, headers=world.h("ADMIN", "T2")).status_code == 404
    assert client.patch(f"/api/v1/users/{op.id}", json={"is_active": False, "reason": "senior"}, headers=world.h("SENIOR_REVIEWER", "T1")).status_code == 403
    assert _audit("user.deactivated") == []


def test_two_admins_can_rotate_and_the_last_active_admin_guard_is_wired(world, client):
    adm = world.users[("T1", "ADMIN")]
    r = client.post("/api/v1/users", json={"email": "admin2@t1.test", "full_name": "A2", "role": "ADMIN", "password": "0123456789ab"}, headers=world.h("ADMIN", "T1"))
    a2 = r.json()["id"]
    tok2 = {"Authorization": f"Bearer {_login(client, 'admin2@t1.test', '0123456789ab').json()['access_token']}"}
    # admin2 deactivates admin1 → allowed because admin2 remains an active ADMIN
    assert client.patch(f"/api/v1/users/{adm.id}", json={"is_active": False, "reason": "rotation"}, headers=tok2).status_code == 200
    assert client.get("/api/v1/auth/me", headers=world.h("ADMIN", "T1")).status_code == 401
    # admin2 is now the only active ADMIN. The API cannot remove it (self-change is refused) and the LAST_ADMIN guard backs that up:
    from app.api.auth import _other_active_admins
    from app.models.identity import User
    db = get_sessionmaker()()
    try:
        assert _other_active_admins(db, db.get(User, a2)) == 0
        assert _other_active_admins(db, db.get(User, adm.id)) == 1
    finally:
        db.close()
    r = client.patch(f"/api/v1/users/{a2}", json={"role": "REVIEWER", "reason": "demote self"}, headers=tok2)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SELF_CHANGE_FORBIDDEN"
    # bringing admin1 back as a REVIEWER keeps exactly one admin; audit trail has both transitions
    assert client.patch(f"/api/v1/users/{adm.id}", json={"is_active": True, "role": "REVIEWER", "reason": "back as reviewer"}, headers=tok2).status_code == 200
    assert len(_audit("user.deactivated")) == 1 and len(_audit("user.reactivated")) == 1


def test_admin_password_reset_voids_old_tokens_and_is_audited_without_the_password(world, client):
    rv = world.users[("T1", "REVIEWER")]
    old = world.h("REVIEWER", "T1")
    assert client.get("/api/v1/auth/me", headers=old).status_code == 200
    time.sleep(1.1)  # the fixture token was issued in this second; the void check is second-granular
    r = client.post(f"/api/v1/users/{rv.id}/reset-password", json={"password": "new-secret-pass-1", "reason": "forgot password"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401  # old token void
    assert _login(client, "reviewer@t1.test", PW).status_code == 401
    r = _login(client, "reviewer@t1.test", "new-secret-pass-1")
    assert r.status_code == 200 and client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
    ev = _audit("user.password_reset")
    assert len(ev) == 1 and "new-secret-pass-1" not in str(ev[0].after) and ev[0].reason == "forgot password" and ev[0].entity_id == str(rv.id)
    # an admin cannot reset their own password this way
    adm = world.users[("T1", "ADMIN")]
    r = client.post(f"/api/v1/users/{adm.id}/reset-password", json={"password": "new-secret-pass-2", "reason": "self reset"}, headers=world.h("ADMIN", "T1"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SELF_CHANGE_FORBIDDEN"


def test_self_service_password_change_requires_current_password_and_returns_a_fresh_token(world, client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_LOGIN", LoginLimiters(pair=SlidingWindowLimiter(3, 300, 120), email=SlidingWindowLimiter(50, 300, 120),
                                                           ip=SlidingWindowLimiter(100, 300, 120)))
    h = world.h("OPERATOR", "T1")
    time.sleep(1.1)
    r = client.post("/api/v1/auth/change-password", json={"current_password": "wrong", "new_password": "brand-new-secret"}, headers=h)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    r = client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": PW}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "SAME_PASSWORD"
    r = client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": "brand-new-secret"}, headers=h)
    assert r.status_code == 200 and r.json()["user"]["email"] == "operator@t1.test"
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200  # the token issued with the change works
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401  # the old one is void
    assert _login(client, "operator@t1.test", PW).status_code == 401 and _login(client, "operator@t1.test", "brand-new-secret").status_code == 200
    assert len(_audit("auth.password_changed")) == 1
    # wrong current-password guesses count against the login throttle (pair dimension) → 429 before more hashing
    for _ in range(3):
        client.post("/api/v1/auth/change-password", json={"current_password": "wrong", "new_password": "brand-new-secret-2"}, headers=fresh)
    r = client.post("/api/v1/auth/change-password", json={"current_password": "brand-new-secret", "new_password": "brand-new-secret-2"}, headers=fresh)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "TOO_MANY_ATTEMPTS"


def test_tokens_without_iat_are_void_once_the_password_changed_but_fine_before(world, client):
    op = world.users[("T1", "OPERATOR")]
    import json

    from app.core.security import _b64, _sign

    body = _b64(json.dumps({"sub": str(op.id), "tid": str(op.tenant_id), "role": op.role, "exp": int(time.time()) + 600}).encode())
    legacy = {"Authorization": f"Bearer {body}.{_sign(body)}"}
    assert client.get("/api/v1/auth/me", headers=legacy).status_code == 200
    time.sleep(1.1)
    assert client.post("/api/v1/auth/change-password", json={"current_password": PW, "new_password": "brand-new-secret"}, headers=world.h("OPERATOR", "T1")).status_code == 200
    r = client.get("/api/v1/auth/me", headers=legacy)
    assert r.status_code == 401 and "predates" in r.json()["detail"]["message"]
    # and a brand-new token issued now is fine
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {issue_token(str(op.id), str(op.tenant_id), op.role)}"}).status_code == 200
