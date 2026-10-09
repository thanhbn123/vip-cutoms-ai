"""G18C — remediation of the code-review findings on the G18 diff (fail-closed gaps, lineage, data integrity)."""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from conftest import FIXTURE_FILES, upload
from sqlalchemy import select

from app.core.errors import DomainError
from app.core.security import _b64, _sign
from app.db import get_sessionmaker
from app.models.identity import User
from app.models.issue import Issue
from app.services import customs_data as cd
from app.services.export_adapters import InternalCsvAdapter, csv_safe


def _pipeline(world, client, docs=("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO")):
    case = world.create_case()
    for d in docs:
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    return case["id"]


def _issues(client, world, cid, status=None):
    q = f"?status={status}" if status else ""
    return client.get(f"/api/v1/cases/{cid}/issues{q}", headers=world.h()).json()


# F1 — system critical issues cannot be "resolved" by a reviewer; system auto-resolve reopens when the condition returns
def test_reviewer_cannot_resolve_system_detected_critical_issue(world, client):
    cid = _pipeline(world, client)
    crit = next(i for i in _issues(client, world, cid, "OPEN") if i["severity"] == "CRITICAL" and i["code"] == "HS_LOW_CONFIDENCE")
    r = client.post(f"/api/v1/cases/{cid}/issues/{crit['id']}/resolve", json={"reason": "ok fine"}, headers=world.h("REVIEWER"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SYSTEM_ISSUE_NOT_RESOLVABLE"
    # a Senior may still waive it, with evidence (unchanged rule)
    w = client.post(f"/api/v1/cases/{cid}/issues/{crit['id']}/waive", json={"reason": "manual classification attached", "evidence": ["memo-1"]},
                    headers=world.h("SENIOR_REVIEWER"))
    assert w.status_code == 200 and w.json()["status"] == "WAIVED"


def test_auto_resolved_issue_reopens_when_condition_reappears(world, client):
    cid = _pipeline(world, client)
    db = get_sessionmaker()()
    try:
        admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
        # deactivate the demo TARIFF → TARIFF_KNOWLEDGE_UNAVAILABLE appears; reactivate → auto-resolved; deactivate again → must REOPEN
        ds = client.get("/api/v1/knowledge/datasets", headers=world.h()).json()
        tariff = next(d for d in ds if d["kind"] == "TARIFF")
        assert admin is not None
    finally:
        db.close()
    client.patch(f"/api/v1/knowledge/datasets/{tariff['id']}", json={"is_active": False, "reason": "test off"}, headers=world.h("ADMIN"))
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    assert any(i["code"] == "TARIFF_KNOWLEDGE_UNAVAILABLE" for i in _issues(client, world, cid, "OPEN"))
    client.patch(f"/api/v1/knowledge/datasets/{tariff['id']}", json={"is_active": True, "reason": "test on"}, headers=world.h("ADMIN"))
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    assert not any(i["code"] == "TARIFF_KNOWLEDGE_UNAVAILABLE" for i in _issues(client, world, cid, "OPEN"))
    client.patch(f"/api/v1/knowledge/datasets/{tariff['id']}", json={"is_active": False, "reason": "test off again"}, headers=world.h("ADMIN"))
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    reopened = [i for i in _issues(client, world, cid) if i["code"] == "TARIFF_KNOWLEDGE_UNAVAILABLE"]
    assert len(reopened) == 1 and reopened[0]["status"] == "OPEN"  # same issue row, reopened — not a duplicate, not hidden
    client.patch(f"/api/v1/knowledge/datasets/{tariff['id']}", json={"is_active": True, "reason": "restore"}, headers=world.h("ADMIN"))


# F7 — unreadable document blocks the case
def test_unreadable_document_raises_critical_issue_and_blocks(world, client):
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", "scan.pdf", content=b"%PDF-1.4\x00\xff\xfe binary scan")
    upload(client, world.h(), case["id"], "PACKING_LIST", FIXTURE_FILES["PACKING_LIST"])
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200 and r.json()["status"] == "BLOCKED"
    codes = {i["code"] for i in _issues(client, world, case["id"], "OPEN")}
    assert "DOCUMENT_UNREADABLE" in codes


# F3 — approving the AI value as-is keeps lineage
def test_approve_field_with_same_value_keeps_ai_lineage(world, client):
    cid = _pipeline(world, client)
    fields = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}
    f = next(v for v in fields.values() if v["is_critical"] and v["value"] and v["review_status"] == "NEEDS_REVIEW" and v["source_document_id"]
             and not v.get("alternatives"))
    r = client.post(f"/api/v1/cases/{cid}/fields/{f['key']}/approve", json={"value": f["value"], "reason": "approve as shown"}, headers=world.h("REVIEWER"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["review_status"] == "APPROVED" and out["origin"] == "AI" and out["source_document_id"] == f["source_document_id"]
    # a DIFFERENT value is still a manual entry
    r2 = client.post(f"/api/v1/cases/{cid}/fields/{f['key']}/approve", json={"value": f["value"] + "X", "reason": "corrected"}, headers=world.h("REVIEWER"))
    assert r2.status_code == 200 and r2.json()["origin"] in ("MANUAL", "REVIEWER")


# F4 — decisions after export reopen the case
def test_hs_decision_after_export_reopens_case(world, client):
    from test_review_release import api, drive_to_reviewed, setup

    cid = setup(world, client)
    drive_to_reviewed(client, world, cid)
    assert api(client, world, "post", f"/cases/{cid}/mark-ready", role="REVIEWER", json={"reason": "all checks passed"}).status_code == 200
    assert api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE", "reason": "release draft"}).status_code == 201
    assert client.get(f"/api/v1/cases/{cid}", headers=world.h()).json()["status"] == "DRAFT_EXPORTED"
    it = next(i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json() if i["hs_status"] == "APPROVED")
    r = client.post(f"/api/v1/cases/{cid}/items/{it['id']}/hs-decision", headers=world.h("REVIEWER"),
                    json={"decision": "REJECT", "reason": "reclassify after export"})
    assert r.status_code == 201, r.text
    status = client.get(f"/api/v1/cases/{cid}", headers=world.h()).json()["status"]
    assert status in ("REVIEW_REQUIRED", "BLOCKED"), status  # never silently stays DRAFT_EXPORTED
    audit_actions = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "case.status_changed" in audit_actions


# F16 — REJECT clears the code
def test_reject_clears_hs_code(world, client):
    cid = _pipeline(world, client)
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    r = client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"),
                    json={"decision": "APPROVE", "hs_code": "39172300", "reason": "ok verified"})
    assert r.status_code == 201, r.text
    client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"), json={"decision": "REJECT", "reason": "wrong code"})
    it = next(i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json() if i["line_no"] == 2)
    assert it["hs_code"] is None and it["hs_status"] in ("NEEDS_REVIEW", "BLOCKED")


# F9 — candidate/heading mismatch refused
def test_hs_decision_rejects_candidate_heading_mismatch(world, client):
    cid = _pipeline(world, client)
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    cands = items[2]["candidates"]
    other = next((c for c in cands if c["heading"] != "3917"), None)
    if other is None:
        pytest.skip("fixture produced a single heading candidate")
    r = client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"),
                    json={"decision": "APPROVE", "hs_code": "39172300", "candidate_id": other["id"], "reason": "mismatch"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "INVALID_CANDIDATE"


# F12 — CSV formula injection
def test_csv_cells_neutralise_formulas():
    assert csv_safe('=HYPERLINK("http://evil")') == "'=HYPERLINK(\"http://evil\")" and csv_safe("+1") == "'+1" and csv_safe("-5") == "'-5"
    assert csv_safe("@cmd") == "'@cmd" and csv_safe("plain") == "plain" and csv_safe(None) == "" and csv_safe(12) == "12"
    payload = {"meta": {"watermark": "W", "version": 1, "schema_version": "s", "legal_notice": None}, "case": {"case_no": "C"},
               "items": [{"line_no": 1, "description": "=1+1", "hs": {"code": None, "status": "X"}, "origin": {}, "tax": {}}]}
    rows = list(csv.reader(io.StringIO(InternalCsvAdapter().render(payload).decode("utf-8-sig"))))
    assert rows[2][1] == "'=1+1"


# F6 — package validation at import
@pytest.mark.parametrize("kind,payload,needle", [
    ("TARIFF", {"rates": {"8413": {"duty_pct": 10}}}, "mfn_duty_pct"),
    ("TARIFF", {"rates": {"84": {"mfn_duty_pct": 1, "vat_pct": 1}}}, ">= 4 digits"),
    ("FTA", {"forms": {"E": {"agreement": "x", "allowed_criteria": [], "checks": [], "preferential_duty_pct": {}}}}, "origin_countries"),
    ("FTA", {"forms": {"E": {"agreement": "x", "origin_countries": [], "allowed_criteria": [], "checks": [], "preferential_duty_pct": {"8413": "0"}}}}, "numeric rate"),
    ("POLICY", {"requirements": {"8413": [{"code": "X"}]}}, "title"),
    ("HS_RULES", {"rules": [{"heading": "84ab", "title": "t", "keywords": [], "base_confidence": 0.5}]}, "digits"),
])
def test_invalid_packages_are_refused_at_import(kind, payload, needle):
    with pytest.raises(DomainError) as e:
        cd.validate_payload(kind, payload)
    assert e.value.status_code == 422 and any(needle in p for p in e.value.detail["details"]["problems"])


def test_valid_packages_pass_validation():
    cd.validate_payload("TARIFF", {"rates": {"84131100": {"mfn_duty_pct": 0.0, "vat_pct": 8}}})
    cd.validate_payload("POLICY", {"requirements": {}})
    cd.validate_payload("FTA", {"forms": {"D": {"agreement": "ATIGA", "origin_countries": ["TH"], "allowed_criteria": ["WO"], "checks": [],
                                                 "preferential_duty_pct": {"8413": 0}}}})


# F14 — supersede guards
def test_supersede_guards(world):
    db = get_sessionmaker()()
    try:
        admin = db.execute(select(User).where(User.id == world.users[("T1", "ADMIN")].id)).scalar_one()
        mk = lambda v, ef: cd.register(db, cd.DatasetPackage(kind="TARIFF", version=v, label=v, effective_from=ef, source_authority="A",  # noqa: E731
                                                              source_document="D", source_reference="R",
                                                              payload={"rates": {"8413": {"mfn_duty_pct": 1, "vat_pct": 1}}}), admin, reason="t")
        a, b, c = mk("a", date(2026, 1, 1)), mk("b", date(2026, 2, 1)), mk("c", date(2026, 3, 1))
        with pytest.raises(DomainError):
            cd.supersede(db, a, a, admin, reason="self")
        cd.supersede(db, a, b, admin, reason="ok")
        with pytest.raises(DomainError):
            cd.supersede(db, a, c, admin, reason="already superseded")
        with pytest.raises(DomainError):
            cd.supersede(db, c, a, admin, reason="new is superseded")
    finally:
        db.close()


# F15 — non-UUID subject in a signed token → 401
def test_signed_token_with_non_uuid_subject_is_401(world, client):
    body = _b64(b'{"sub": "demo-user", "tid": "x", "exp": 9999999999}')
    r = client.get("/api/v1/cases", headers={"Authorization": f"Bearer {body}.{_sign(body)}"})
    assert r.status_code == 401


# F18 — docs hidden outside development (API) and never proxied
def test_openapi_docs_disabled_outside_development(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_SECRET_KEY", "s" * 40)
    config.get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        config.get_settings.cache_clear()


# F2 — stale AI value cleared when the current document version no longer yields it
def test_stale_ai_field_is_cleared_when_new_document_version_lacks_it(world, client):
    cid = _pipeline(world, client, docs=("INVOICE",))
    fields = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}
    assert fields["invoice.total_amount"]["value"]
    # v2 of the invoice without the total line
    v1 = open(f"{__import__('conftest').FIXTURES}/invoice.txt", encoding="utf-8").read()
    v2 = "\n".join(line for line in v1.splitlines() if "total" not in line.lower())
    r = upload(client, world.h(), cid, "INVOICE", "invoice-v2.txt", content=v2.encode())
    assert r.status_code == 201, r.text
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    f2 = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}["invoice.total_amount"]
    assert f2["value"] in (None, "") and f2["review_status"] == "NEEDS_REVIEW" and f2["source_document_id"] is None
    db = get_sessionmaker()()
    try:
        assert db.execute(select(Issue).where(Issue.case_id == cid, Issue.code == "FIELD_MISSING", Issue.status == "OPEN")).scalars().first()
    finally:
        db.close()
