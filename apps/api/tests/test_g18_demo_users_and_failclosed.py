"""G18 — B-07 demo-user deactivation and fail-closed behaviour when a real provider fails."""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import select

from app.ai.base import ExtractionResult, ProviderUnavailable
from app.db import get_sessionmaker
from app.models.audit import AuditEvent
from app.models.identity import User

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)


@pytest.fixture
def seeded(monkeypatch, client):
    import seed_demo

    monkeypatch.setenv("SEED_DEMO_PASSWORD", "demo-acceptance-2026")
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])
    seed_demo.main()
    # a NON-demo admin in the same tenant, as production would have
    db = get_sessionmaker()()
    demo_admin = db.execute(select(User).where(User.email == "admin@demo.local")).scalar_one()
    from app.core.security import hash_password

    db.add(User(tenant_id=demo_admin.tenant_id, email="ops.admin@vipgroup.example", full_name="Ops Admin", role="ADMIN",
                password_hash=hash_password("ops-admin-password-2026")))
    db.commit()
    db.close()
    return client


def login(client, email, pw):
    return client.post("/api/v1/auth/login", json={"email": email, "password": pw}).status_code


def test_demo_email_filter_is_exact():
    import deactivate_demo_users as d

    assert d.is_demo_email("reviewer@demo.local") and d.is_demo_email("Admin@DEMO.LOCAL")
    assert not d.is_demo_email("reviewer@demo.local.evil.com") and not d.is_demo_email("x@notdemo.local") and not d.is_demo_email("a@demo.localhost")


def test_inventory_is_read_only(seeded, capsys):
    import deactivate_demo_users as d

    assert d.main([]) == 0
    assert "demo users: 4" in capsys.readouterr().out
    assert login(seeded, "reviewer@demo.local", "demo-acceptance-2026") == 200  # nothing changed


def test_execute_requires_confirmation_token(seeded, monkeypatch):
    import deactivate_demo_users as d

    monkeypatch.delenv("DEACTIVATE_CONFIRM", raising=False)
    assert d.main(["--execute"]) == 2
    assert login(seeded, "reviewer@demo.local", "demo-acceptance-2026") == 200


def test_deactivation_blocks_login_keeps_history_and_is_idempotent(seeded, monkeypatch):
    import deactivate_demo_users as d

    monkeypatch.setenv("DEACTIVATE_CONFIRM", "demo.local")
    assert d.main(["--execute", "--reason", "G18 test"]) == 0
    for email in ("operator", "reviewer", "senior", "admin"):
        assert login(seeded, f"{email}@demo.local", "demo-acceptance-2026") == 401
    assert login(seeded, "ops.admin@vipgroup.example", "ops-admin-password-2026") == 200  # non-demo admin unaffected
    db = get_sessionmaker()()
    try:
        users = db.execute(select(User).where(User.email.like("%@demo.local"))).scalars().all()
        assert len(users) == 4 and all(not u.is_active for u in users)  # rows kept, not deleted → audit actor refs stay valid
        events = db.execute(select(AuditEvent).where(AuditEvent.action == "user.deactivated")).scalars().all()
        assert len(events) == 4 and all(e.actor_type == "SYSTEM" and e.reason == "G18 test" and e.after["is_active"] is False for e in events)
        # idempotent: second run deactivates nothing and writes no new audit events
        assert d.main(["--execute"]) == 0
        assert db.execute(select(AuditEvent).where(AuditEvent.action == "user.deactivated")).scalars().all().__len__() == 4
        assert d.main(["--verify"]) == 0
    finally:
        db.close()


def test_verify_fails_while_demo_users_are_active(seeded):
    import deactivate_demo_users as d

    assert d.main(["--verify"]) == 1


def test_seed_refuses_outside_development(monkeypatch):
    """Production seed never creates demo users: the seed refuses unless APP_ENV is development/test."""
    import seed_demo

    from app.core import config

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET_KEY", "z" * 40)
    monkeypatch.setenv("SEED_DEMO_PASSWORD", "demo-acceptance-2026")
    config.get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit, match="refuses"):
            seed_demo.main()
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        config.get_settings.cache_clear()


# --- fail-closed when the (real) provider fails ----------------------------------------------------
class FailingProvider:
    name, version = "http-llm", "test"

    def extract_document(self, doc_type, filename, content) -> ExtractionResult:
        raise ProviderUnavailable("HTTP 503 (attempt 3)")

    def health(self, *, live=True):
        raise AssertionError("not used")


def test_provider_failure_yields_no_values_critical_issue_and_blocked_case(world, client, monkeypatch):
    from conftest import FIXTURE_FILES, upload

    monkeypatch.setattr("app.services.mapping.get_provider", lambda: FailingProvider())
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", FIXTURE_FILES["INVOICE"])
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "BLOCKED"
    docs = client.get(f"/api/v1/cases/{case['id']}/documents", headers=world.h()).json()
    assert docs[0]["status"] == "PARSE_FAILED" and any("provider failure" in w for w in docs[0]["parse_warnings"])
    assert client.get(f"/api/v1/cases/{case['id']}/extractions", headers=world.h()).json() == []  # nothing guessed
    issues = client.get(f"/api/v1/cases/{case['id']}/issues", headers=world.h()).json()
    assert any(i["code"] == "AI_PROVIDER_FAILED" and i["severity"] == "CRITICAL" for i in issues)
    fields = client.get(f"/api/v1/cases/{case['id']}/fields", headers=world.h()).json()
    assert all(f["value"] in (None, "") for f in fields if f["is_critical"])


def test_copilot_provider_failure_returns_503_not_a_guess(world, client, monkeypatch):
    from app.ai.base import CopilotAnswer

    class Failing:
        name, version = "http-llm", "test"

        def answer_case_question(self, q, ctx) -> CopilotAnswer:
            raise ProviderUnavailable("timeout")

    monkeypatch.setattr("app.services.copilot.get_capability", lambda cap: Failing())
    case = world.create_case()
    r = client.post(f"/api/v1/cases/{case['id']}/copilot/ask", json={"question": "Còn thiếu gì?"}, headers=world.h("REVIEWER"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "AI_PROVIDER_UNAVAILABLE"
