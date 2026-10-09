"""G18B — hardening follow-ups that need no owner input (G16 low findings + G18 known limitations)."""

from __future__ import annotations

import base64
import json
import time
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.ai import accounting
from app.ai.base import ProviderBudgetExceeded
from app.ai.http_llm_provider import HttpLLMProvider
from app.core.config import Settings
from app.core.http import content_disposition
from app.core.security import _b64, _sign, issue_token
from app.db import get_sessionmaker
from app.models.ai_usage import AiUsageEvent
from app.models.identity import User
from app.services import customs_data as cd
from app.services.hs_lookup import lookup, lookup_value


# --- 500-vs-401 on a malformed signed payload ---------------------------------------------------------
@pytest.mark.parametrize("body", [b"not json", b"[1,2]", b'{"sub": 1, "tid": "x", "exp": 9999999999}', b'{"sub": "a", "tid": "b"}'])
def test_signed_but_malformed_token_is_401_not_500(world, client, body):
    b = _b64(body)
    tok = f"{b}.{_sign(b)}"  # correctly signed by this process → reaches the payload parser
    r = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_expired_and_valid_tokens_still_behave(world, client):
    u = world.users[("T1", "OPERATOR")]
    expired = issue_token(str(u.id), str(u.tenant_id), "OPERATOR", ttl=-10)
    assert client.get("/api/v1/cases", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    assert client.get("/api/v1/cases", headers=world.h()).status_code == 200
    payload = json.loads(base64.urlsafe_b64decode(world.tokens[("T1", "OPERATOR")].split(".")[0] + "==").decode())
    assert payload["exp"] > time.time()


# --- security headers at the API layer -----------------------------------------------------------------
def test_api_responses_carry_security_headers(world, client):
    r = client.get("/api/v1/cases", headers=world.h())
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "private, no-store"
    h = client.get("/health")
    assert h.headers["x-content-type-options"] == "nosniff" and "cache-control" not in h.headers


# --- Content-Disposition quoting -----------------------------------------------------------------------
def test_content_disposition_quotes_and_encodes():
    cd_ = content_disposition('hóa đơn "A" 2026.pdf')
    fallback, star = cd_.split("; filename*=")
    assert fallback.startswith('attachment; filename="') and fallback.endswith('"')
    inner = fallback[len('attachment; filename="'):-1]
    assert inner.isascii() and '"' not in inner and " " not in inner and inner.endswith(".pdf")  # safe quoted ASCII fallback
    assert star == "UTF-8''h%C3%B3a%20%C4%91%C6%A1n%20%22A%22%202026.pdf"  # full name, RFC 5987 encoded
    assert "\n" not in content_disposition("evil\r\nX-Injected: 1.txt")
    assert content_disposition("").startswith('attachment; filename="download"')


def test_document_download_uses_safe_header(world, client):
    from conftest import FIXTURE_FILES, upload

    case = world.create_case()
    r = upload(client, world.h(), case["id"], "INVOICE", FIXTURE_FILES["INVOICE"])
    doc = r.json()
    dl = client.get(f"/api/v1/documents/{doc['id']}/content", headers=world.h())
    assert dl.status_code == 200 and "filename*=UTF-8''" in dl.headers["content-disposition"] and '"' in dl.headers["content-disposition"]


# --- longest-prefix HS lookups -------------------------------------------------------------------------
def test_lookup_prefers_the_most_specific_key():
    rates = {"8413": {"mfn_duty_pct": 10.0}, "841370": {"mfn_duty_pct": 5.0}, "84137010": {"mfn_duty_pct": 0.0}}
    assert lookup(rates, "84137010") == ("84137010", {"mfn_duty_pct": 0.0})
    assert lookup(rates, "84137099") == ("841370", {"mfn_duty_pct": 5.0})
    assert lookup(rates, "8413.11.00") == ("8413", {"mfn_duty_pct": 10.0})
    assert lookup(rates, "8414") is None and lookup(rates, "841") is None and lookup({}, "8413") is None and lookup(None, "8413") is None
    assert lookup_value(rates, "99999999", default="none") == "none"


def test_valuation_uses_eight_digit_line_when_authoritative_schedule_has_one(world, client):
    """End to end: an authoritative tariff keyed by 8-digit lines + heading default → the line wins and is cited."""
    from conftest import FIXTURE_FILES, upload

    db = get_sessionmaker()()
    admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
    payload = {"rates": {"3917": {"mfn_duty_pct": 9.0, "vat_pct": 10.0}, "39172300": {"mfn_duty_pct": 2.5, "vat_pct": 8.0}}}
    pkg = cd.DatasetPackage(kind="TARIFF", version="auth-8digit-2026", label="8-digit tariff (test)", effective_from=date(2026, 1, 1),
                            source_authority="Test Authority", source_document="Decision 2/2026/TEST",
                            source_reference="https://example.test/2", payload=payload)
    ds = cd.register(db, pkg, admin, reason="t")
    cd.verify(db, ds, admin, reason="t")
    ds.is_active = True
    db.commit()
    db.close()
    case = world.create_case()
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{case['id']}/items", headers=world.h()).json()}
    r = client.post(f"/api/v1/cases/{case['id']}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"),
                    json={"decision": "APPROVE", "hs_code": "39172300", "reason": "verified 8-digit line"})
    assert r.status_code == 201, r.text
    tax = next(a for a in client.get(f"/api/v1/cases/{case['id']}/assessments", headers=world.h()).json()
               if a["kind"] == "TAX" and a["item_id"] == items[2]["id"])
    assert tax["dataset_version"] == "auth-8digit-2026" and tax["dataset_is_demo"] is False
    assert str(tax["result"].get("duty_pct", tax["result"].get("mfn_duty_pct", ""))).startswith("2.5") or any("39172300" in s for s in tax["reasoning"])
    assert any("dòng 39172300" in s for s in tax["reasoning"])


# --- SENIOR_REVIEWER may verify via the API -------------------------------------------------------------
def test_senior_reviewer_can_verify_but_not_import(world, client):
    body = {"kind": "POLICY", "version": "auth-pol-2026", "label": "Policy via API", "effective_from": "2026-01-01",
            "source_authority": "Test Authority", "source_document": "Circular 3/2026/TEST", "source_reference": "https://example.test/3",
            "payload": {"requirements": {}}, "reason": "owner package"}
    assert client.post("/api/v1/knowledge/datasets/import", json=body, headers=world.h("SENIOR_REVIEWER")).status_code == 403
    ds = client.post("/api/v1/knowledge/datasets/import", json=body, headers=world.h("ADMIN")).json()
    assert client.post(f"/api/v1/knowledge/datasets/{ds['id']}/verify", json={"reason": "checked"}, headers=world.h("REVIEWER")).status_code == 403
    v = client.post(f"/api/v1/knowledge/datasets/{ds['id']}/verify", json={"reason": "checked"}, headers=world.h("SENIOR_REVIEWER"))
    assert v.status_code == 200 and v.json()["is_authoritative"] is True
    me = client.get("/api/v1/auth/me", headers=world.h("SENIOR_REVIEWER")).json()
    assert "knowledge.verify" in me["permissions"] and "knowledge.manage" not in me["permissions"]


# --- persistent AI ledger ------------------------------------------------------------------------------
def _settings(**kw) -> Settings:
    base = dict(ai_provider="http-llm", ai_provider_base_url="https://llm.example.test/v1", ai_provider_api_key="placeholder-key-not-real",
                ai_provider_model="m", ai_max_retries=0, ai_timeout_seconds=1.0, ai_cost_per_1k_input_tokens_usd=1.0,
                ai_cost_per_1k_output_tokens_usd=1.0)
    base.update(kw)
    return Settings(**base)


def _envelope(content: dict, usage=(500, 500)) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content)}}], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}


def test_ledger_rows_are_persisted_and_budget_survives_a_restart(migrated_db):
    accounting.ACCOUNTANT.reset()
    p = HttpLLMProvider(_settings(ai_daily_budget_usd=1.5),
                        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=_envelope({"description": "d", "reasoning": []}))))
    p.propose_description({"description": "x"})  # 1000 tokens → 1.0 USD
    with get_sessionmaker()() as db:
        rows = db.execute(select(AiUsageEvent)).scalars().all()
    assert len(rows) == 1 and rows[0].cost_usd == pytest.approx(1.0) and rows[0].capability == "hs_ai" and rows[0].outcome == "ok"
    assert rows[0].correlation_id and rows[0].model == "m"
    # simulate a process restart: in-memory ledger is empty, the persisted spend still counts toward the budget
    accounting.ACCOUNTANT.reset()
    assert accounting.ACCOUNTANT.snapshot().cost_usd == 0.0
    assert accounting.ACCOUNTANT.persisted_spend_today() == pytest.approx(1.0)
    p2 = HttpLLMProvider(_settings(ai_daily_budget_usd=1.5),
                         transport=httpx.MockTransport(lambda req: httpx.Response(200, json=_envelope({"description": "d", "reasoning": []}))))
    p2.propose_description({"description": "x"})  # total 2.0 ≥ 1.5 → next call refused
    with pytest.raises(ProviderBudgetExceeded):
        p2.propose_description({"description": "x"})
    with get_sessionmaker()() as db:
        assert db.execute(select(AiUsageEvent)).scalars().all().__len__() == 2  # the refused call wrote no row
