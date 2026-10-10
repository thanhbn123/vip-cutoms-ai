"""G18H — tenant-level audit feed (events that belong to no case: accounts, lockouts, knowledge)."""

from __future__ import annotations


def test_tenant_audit_feed_lists_account_events_newest_first_and_is_tenant_isolated(world, client):
    op = world.users[("T1", "OPERATOR")]
    case_id = world.create_case("T1")["id"]  # case-bound events stay out of the tenant feed unless asked for
    assert client.patch(f"/api/v1/users/{op.id}", json={"role": "REVIEWER", "reason": "promoted"}, headers=world.h("ADMIN", "T1")).status_code == 200
    assert client.patch(f"/api/v1/users/{op.id}", json={"is_active": False, "reason": "left the company"}, headers=world.h("ADMIN", "T1")).status_code == 200
    r = client.get("/api/v1/audit", headers=world.h("ADMIN", "T1"))
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()]
    assert actions[:2] == ["user.deactivated", "user.updated"]  # newest first
    assert all(e["case_id"] is None for e in r.json())
    r = client.get("/api/v1/audit", params={"include_cases": "true"}, headers=world.h("ADMIN", "T1"))
    assert any(e["action"] == "case.created" and e["case_id"] == case_id for e in r.json())
    assert all("hash" in e and "actor_type" in e for e in r.json())
    # narrowing
    r = client.get("/api/v1/audit", params={"entity_type": "user"}, headers=world.h("ADMIN", "T1"))
    assert {e["entity_type"] for e in r.json()} == {"user"} and len(r.json()) == 2
    r = client.get("/api/v1/audit", params={"action_prefix": "user.de"}, headers=world.h("ADMIN", "T1"))
    assert [e["action"] for e in r.json()] == ["user.deactivated"]
    r = client.get("/api/v1/audit", params={"action_prefix": "user.%"}, headers=world.h("ADMIN", "T1"))  # wildcard is literal, not LIKE
    assert r.json() == []
    r = client.get("/api/v1/audit", params={"limit": 1}, headers=world.h("ADMIN", "T1"))
    assert len(r.json()) == 1
    assert client.get("/api/v1/audit", params={"limit": 0}, headers=world.h("ADMIN", "T1")).status_code == 422
    # another tenant sees none of it; a role without audit.read is refused
    assert client.get("/api/v1/audit", params={"entity_type": "user"}, headers=world.h("ADMIN", "T2")).json() == []
    assert client.get("/api/v1/audit", headers=world.h("OPERATOR", "T2")).json() == []  # every role may read its own tenant's audit (D-013); the query isolates
