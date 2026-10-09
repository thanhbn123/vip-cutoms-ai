import pytest
from sqlalchemy import text

from app.db import get_engine


def test_login_and_me(world, client):
    r = client.post("/api/v1/auth/login", json={"email": "reviewer@t1.test", "password": "correct-horse-battery"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["user"]["role"] == "REVIEWER"
    assert "hs.decide" in me["permissions"]


def test_login_wrong_password_rejected(world, client):
    r = client.post("/api/v1/auth/login", json={"email": "reviewer@t1.test", "password": "nope"})
    assert r.status_code == 401


def test_unauthenticated_and_tampered_token_rejected(world, client):
    assert client.get("/api/v1/cases").status_code == 401
    tok = world.tokens[("T1", "OPERATOR")]
    body, sig = tok.split(".")
    # Flip the first signature character to one that is guaranteed to differ. A fixed
    # replacement ("x") made the "tampered" token identical to the real one whenever the
    # signature already started with "x" (1/64 of runs) and the assertion failed by chance.
    flipped = "y" if sig[0] == "x" else "x"
    tampered = f"{body}.{flipped}{sig[1:]}"
    assert tampered != tok
    assert client.get("/api/v1/cases", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401
    # The full signature is verified, so the same holds for a flipped last character.
    last = "y" if sig[-1] == "x" else "x"
    assert client.get("/api/v1/cases", headers={"Authorization": f"Bearer {body}.{sig[:-1]}{last}"}).status_code == 401


def test_create_case_assigns_number_status_owner_and_audits(world, client):
    case = world.create_case()
    assert case["status"] == "NEW"
    assert case["case_no"].startswith("VIP-HQ-")
    assert case["owner_id"] == str(world.users[("T1", "OPERATOR")].id)
    events = client.get(f"/api/v1/cases/{case['id']}/audit", headers=world.h()).json()
    assert [e["action"] for e in events] == ["case.created"]
    assert events[0]["actor_type"] == "USER" and events[0]["after"]["declaration_type"] == "A11"


def test_admin_cannot_create_case_rbac(world, client):
    body = {"customer_id": str(world.customer_T1.id), "declaration_type": "A11"}
    r = client.post("/api/v1/cases", json=body, headers=world.h("ADMIN"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FORBIDDEN"


def test_operator_cannot_create_user_rbac(world, client):
    r = client.post("/api/v1/users", json={"email": "x@t1.test", "full_name": "X", "role": "ADMIN", "password": "0123456789ab"},
                    headers=world.h("OPERATOR"))
    assert r.status_code == 403
    r = client.post("/api/v1/users", json={"email": "x@t1.test", "full_name": "X", "role": "REVIEWER", "password": "0123456789ab"},
                    headers=world.h("ADMIN"))
    assert r.status_code == 201


def test_cross_tenant_case_read_forbidden(world, client):
    case = world.create_case(tenant="T1")
    r = client.get(f"/api/v1/cases/{case['id']}", headers=world.h("SENIOR_REVIEWER", "T2"))
    assert r.status_code == 404
    assert client.get("/api/v1/cases", headers=world.h("OPERATOR", "T2")).json() == []
    r = client.get(f"/api/v1/cases/{case['id']}/audit", headers=world.h("OPERATOR", "T2"))
    assert r.status_code == 404


def test_cross_tenant_customer_reference_rejected(world, client):
    body = {"customer_id": str(world.customer_T2.id), "declaration_type": "A11"}
    r = client.post("/api/v1/cases", json=body, headers=world.h("OPERATOR", "T1"))
    assert r.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"declaration_type": "A11"},  # missing customer
        {"customer_id": "not-a-uuid", "declaration_type": "A11"},
        {"customer_id": "00000000-0000-0000-0000-000000000000", "declaration_type": "ZZZ"},
        {"customer_id": "00000000-0000-0000-0000-000000000000", "declaration_type": "A11", "direction": "SIDEWAYS"},
    ],
)
def test_case_api_validation(world, client, body):
    r = client.post("/api/v1/cases", json=body, headers=world.h())
    assert r.status_code == 422


def test_audit_is_append_only_and_hash_chained(world, client):
    world.create_case()
    world.create_case()
    assert client.get("/api/v1/audit/verify", headers=world.h()).json()["chain_valid"] is True
    with pytest.raises(Exception, match="append-only"):
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE audit_events SET reason = 'tampered'"))
    with pytest.raises(Exception, match="append-only"):
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM audit_events"))


def test_reviewer_assignment_must_be_reviewer(world, client):
    case = world.create_case()
    r = client.patch(f"/api/v1/cases/{case['id']}", json={"reviewer_id": str(world.users[("T1", "OPERATOR")].id)}, headers=world.h())
    assert r.status_code == 422
    r = client.patch(f"/api/v1/cases/{case['id']}", json={"reviewer_id": str(world.users[("T1", "REVIEWER")].id)}, headers=world.h())
    assert r.status_code == 200


@pytest.mark.parametrize("session_tz", ["UTC", "Asia/Ho_Chi_Minh", "America/Los_Angeles"])
def test_audit_chain_verifies_regardless_of_database_session_timezone(world, client, session_tz):
    """`created_at` is a timestamptz returned in the session's TimeZone.

    Hashing its raw isoformat() made the chain verify only in a UTC session and report
    tampering in any other, so the digest normalises the timestamp to UTC instead.
    """
    from sqlalchemy.orm import Session

    from app.services import audit

    world.create_case()
    tenant_id = world.users[("T1", "OPERATOR")].tenant_id
    with Session(get_engine()) as db:
        db.execute(text(f"SET TIME ZONE '{session_tz}'"))
        assert audit.verify_chain(db, tenant_id) is True, f"chain must verify with session TimeZone={session_tz}"
