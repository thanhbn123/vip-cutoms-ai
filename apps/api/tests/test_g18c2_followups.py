"""G18C-2 — second-pass review of the remediation: behaviour changes that shipped without tests, and new semantics."""

from __future__ import annotations

import os

from conftest import FIXTURE_FILES, FIXTURES, upload
from sqlalchemy import select

from app.ai.base import ExtractedValue, ExtractionResult
from app.db import get_sessionmaker
from app.models.issue import Issue
from app.services.export_adapters import csv_safe


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


def test_orphan_invoice_line_is_critical_and_blocks(world, client):
    cid = _pipeline(world, client, docs=("INVOICE",))
    assert len(client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()) == 3
    v1 = open(os.path.join(FIXTURES, "invoice.txt"), encoding="utf-8").read()
    v2 = "\n".join(line for line in v1.splitlines() if not line.startswith("3 |"))  # drop invoice line 3
    assert upload(client, world.h(), cid, "INVOICE", "invoice-v2.txt", content=v2.encode()).status_code == 201
    r = client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    assert r.json()["status"] == "BLOCKED"
    orphan = [i for i in _issues(client, world, cid, "OPEN") if i["code"] == "ITEM_NOT_ON_INVOICE"]
    assert orphan and orphan[0]["severity"] == "CRITICAL" and orphan[0]["auto_resolvable"] is True
    # a Reviewer cannot resolve it; a Senior can waive with evidence
    assert client.post(f"/api/v1/cases/{cid}/issues/{orphan[0]['id']}/resolve", json={"reason": "it is fine"}, headers=world.h("REVIEWER")).status_code == 409


def test_already_open_issue_takes_the_promoted_severity(world, client):
    """Rows OPEN before a rule promotion (WARNING → CRITICAL) must adopt the new severity on the next sync."""
    cid = _pipeline(world, client)
    db = get_sessionmaker()()
    try:
        issue = db.execute(select(Issue).where(Issue.case_id == cid, Issue.status == "OPEN", Issue.severity == "CRITICAL")).scalars().first()
        issue.severity = "WARNING"  # simulate a row written by the old rule
        db.commit()
    finally:
        db.close()
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    db = get_sessionmaker()()
    try:
        assert db.get(Issue, issue.id).severity == "CRITICAL"
    finally:
        db.close()


def test_user_resolved_issue_reopens_when_condition_changes(world, client):
    cid = _pipeline(world, client, docs=("INVOICE", "PACKING_LIST"))
    conflict = next(i for i in _issues(client, world, cid, "OPEN") if i["code"] == "DOCUMENT_CONFLICT" and i["target_ref"] == "shipment.total_packages")
    assert client.post(f"/api/v1/cases/{cid}/issues/{conflict['id']}/resolve", json={"reason": "warehouse confirmed 126"},
                       headers=world.h("REVIEWER")).status_code == 200
    # same condition again → stays resolved (reviewer judgement stands)
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    assert next(i for i in _issues(client, world, cid) if i["id"] == conflict["id"])["status"] == "RESOLVED"
    # DIFFERENT conflict values (new invoice version says 130 packages) → reopened
    import re

    v1 = open(os.path.join(FIXTURES, "invoice.txt"), encoding="utf-8").read()
    v2 = "\n".join(re.sub(r"\d+", "130", line, count=1) if "packages" in line.lower() else line for line in v1.splitlines()) + "\n"
    assert v2 != v1
    assert upload(client, world.h(), cid, "INVOICE", "invoice-v2.txt", content=v2.encode()).status_code == 201
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    again = next(i for i in _issues(client, world, cid) if i["id"] == conflict["id"])
    assert again["status"] == "OPEN" and "130" in again["detail"]
    actions = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "issue.reopened" in actions


def test_unreadable_new_version_clears_previous_values(world, client):
    cid = _pipeline(world, client, docs=("INVOICE",))
    before = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}
    assert before["invoice.total_amount"]["value"]
    assert upload(client, world.h(), cid, "INVOICE", "scan.pdf", content=b"%PDF-1.4\x00\xff\xfe scanned").status_code == 201
    r = client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    assert r.json()["status"] == "BLOCKED"
    after = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}
    assert after["invoice.total_amount"]["value"] in (None, "") and after["invoice.total_amount"]["source_document_id"] is None
    actions = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "field.cleared" in actions and "document.parsed" in actions


class NoDescriptionProvider:
    name, version = "mock", "nodesc"

    def extract_document(self, doc_type, filename, content):
        res = ExtractionResult(doc_type=doc_type, provider=self.name, provider_version=self.version)
        if doc_type == "INVOICE":
            res.values = [ExtractedValue("invoice.number", "INV-1", 0.9, "line:1", "t"), ExtractedValue("items[1].quantity", "5", 0.9, "line:9", "t"),
                          ExtractedValue("items[1].amount", "500", 0.9, "line:9", "t")]
        return res

    def health(self, *, live=True):
        raise AssertionError("unused")


def test_invoice_row_without_description_blocks_instead_of_500(world, client, monkeypatch):
    monkeypatch.setattr("app.services.mapping.get_provider", lambda: NoDescriptionProvider())
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", FIXTURE_FILES["INVOICE"])
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "BLOCKED"
    assert any(i["code"] == "ITEM_DESCRIPTION_MISSING" and i["severity"] == "CRITICAL" for i in _issues(client, world, case["id"], "OPEN"))
    assert client.get(f"/api/v1/cases/{case['id']}/items", headers=world.h()).json() == []


def test_reviewer_decided_preferential_rate_wins_over_recomputation(world, client):
    cid = _pipeline(world, client)
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    assert client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"),
                       json={"decision": "APPROVE", "hs_code": "39172300", "reason": "classification ok"}).status_code == 201
    assert client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/co-decision", headers=world.h("REVIEWER"),
                       json={"decision": "APPLY", "reason": "Form E verified"}).status_code == 200
    co = next(a for a in client.get(f"/api/v1/cases/{cid}/assessments", headers=world.h()).json() if a["kind"] == "CO" and a["item_id"] == items[2]["id"])
    decided = co["reviewer_decision"]["preferential_duty_pct"]
    assert decided == 0.0
    # re-approve a heading with a DIFFERENT demo preferential rate (7304 → 5.0) while the APPLY decision is kept
    assert client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("SENIOR_REVIEWER"),
                       json={"decision": "APPROVE", "hs_code": "73041100", "reason": "senior override to steel", "evidence": ["lab-report"]}).status_code == 201
    tax = next(a for a in client.get(f"/api/v1/cases/{cid}/assessments", headers=world.h()).json() if a["kind"] == "TAX" and a["item_id"] == items[2]["id"])
    co2 = next(a for a in client.get(f"/api/v1/cases/{cid}/assessments", headers=world.h()).json() if a["kind"] == "CO" and a["item_id"] == items[2]["id"])
    if co2["reviewer_decision"] and co2["reviewer_decision"].get("decision") == "APPLY":
        assert str(tax["inputs"].get("duty_pct")) in ("0", "0.0", "0.00")  # the approved 0 %, not the recomputed 5 %
    else:
        assert tax["inputs"].get("duty_pct") not in (None, "")  # decision was reset by origin.evaluate → MFN applies; no silent reuse


def test_csv_safe_keeps_numbers_numeric():
    assert csv_safe("-150.00") == "-150.00" and csv_safe("-5") == "-5" and csv_safe(" 12.5 ") == " 12.5 "
    assert csv_safe("-5 USD") == "'-5 USD" and csv_safe("=SUM(A1)") == "'=SUM(A1)"


def test_approve_field_same_numeric_value_in_different_notation_keeps_lineage(world, client):
    cid = _pipeline(world, client, docs=("INVOICE",))
    fields = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=world.h()).json()}
    f = fields["invoice.total_amount"]
    assert f["value"] and not f.get("alternatives")
    notation = f["value"] + ".0" if "." not in f["value"] else f["value"].rstrip("0").rstrip(".")
    r = client.post(f"/api/v1/cases/{cid}/fields/invoice.total_amount/approve", json={"value": notation, "reason": "approve as shown"},
                    headers=world.h("REVIEWER"))
    assert r.status_code == 200, r.text
    assert r.json()["origin"] == "AI" and r.json()["source_document_id"] == f["source_document_id"]


def test_issue_out_exposes_auto_resolvable(world, client):
    cid = _pipeline(world, client)
    issues = _issues(client, world, cid)
    assert issues and all("auto_resolvable" in i for i in issues)
