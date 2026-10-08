from conftest import FIXTURE_FILES, upload


def run(world, client, docs=("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"), extra=()):
    case = world.create_case()
    for d in docs:
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    for d, fn, content in extra:
        upload(client, world.h(), case["id"], d, fn, content=content)
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    return case


def items(client, world, cid):
    return {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}


def assess(client, world, cid, kind, item_id=None):
    rows = client.get(f"/api/v1/cases/{cid}/assessments", headers=world.h()).json()
    return next(a for a in rows if a["kind"] == kind and a["item_id"] == item_id)


def open_codes(client, world, cid):
    return {(i["code"], i["target_ref"]) for i in client.get(f"/api/v1/cases/{cid}/issues?status=OPEN", headers=world.h()).json()}


def approve_hs(client, world, cid, item, code):
    r = client.post(f"/api/v1/cases/{cid}/items/{item['id']}/hs-decision",
                    json={"decision": "APPROVE", "hs_code": code, "reason": "verified against catalogue"}, headers=world.h("REVIEWER"))
    assert r.status_code == 201, r.text


def test_tax_only_after_approved_hs_and_complete_valuation_inputs(world, client):
    case = run(world, client)
    cid = case["id"]
    its = items(client, world, cid)
    assert assess(client, world, cid, "TAX", its[2]["id"])["status"] == "AWAITING_HS"
    val = assess(client, world, cid, "VALUATION")
    assert val["status"] == "INPUT_MISSING" and "bảo hiểm" in " ".join(val["reasoning"])  # FOB, insurance missing
    approve_hs(client, world, cid, its[2], "39172300")
    assert assess(client, world, cid, "TAX", its[2]["id"])["status"] == "INPUT_MISSING"
    r = client.put(f"/api/v1/cases/{cid}/fields/valuation.insurance", json={"value": "100", "reason": "insurance invoice received"},
                   headers=world.h("REVIEWER"))
    assert r.status_code == 200 and r.json()["review_status"] == "APPROVED"
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    val = assess(client, world, cid, "VALUATION")
    assert val["status"] == "COMPUTED" and val["result"]["customs_value"] == "2500.00"  # 1980 + 420 freight + 100 insurance
    tax = assess(client, world, cid, "TAX", its[2]["id"])
    assert tax["status"] == "COMPUTED" and tax["dataset_is_demo"] is True and "NON-AUTHORITATIVE" in tax["result"]["label"]
    assert tax["inputs"]["duty_pct"] == "5.0" and tax["result"]["import_duty"] == "37.88"  # 600/1980*2500=757.58 × 5%
    assert tax["result"]["vat"] == "79.55"


def test_co_assessment_states_and_reviewer_decision_fail_closed(world, client):
    case = run(world, client)
    cid = case["id"]
    its = items(client, world, cid)
    a1, a2, a3 = (assess(client, world, cid, "CO", its[n]["id"]) for n in (1, 2, 3))
    assert a1["status"] == "NEEDS_REVIEW"  # Form E item 1 missing model
    assert a2["status"] == "ELIGIBLE_PENDING_REVIEW" and a2["result"]["preferential_duty_pct"] == 0.0
    assert a3["status"] == "NOT_COVERED"
    assert ("CO_DECISION_PENDING", "item:2") in open_codes(client, world, cid)
    url = f"/api/v1/cases/{cid}/items/{{}}/co-decision"
    body = {"decision": "APPLY", "reason": "Form E verified on issuing portal"}
    assert client.post(url.format(its[2]["id"]), json=body, headers=world.h("OPERATOR")).status_code == 403
    r = client.post(url.format(its[1]["id"]), json=body, headers=world.h("REVIEWER"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CO_NOT_ELIGIBLE"
    r = client.post(url.format(its[2]["id"]), json=body, headers=world.h("REVIEWER"))
    assert r.status_code == 200 and r.json()["reviewer_decision"]["decision"] == "APPLY"
    assert ("CO_DECISION_PENDING", "item:2") not in open_codes(client, world, cid)
    # preferential rate flows into tax once HS approved and valuation complete
    approve_hs(client, world, cid, its[2], "39172300")
    client.put(f"/api/v1/cases/{cid}/fields/valuation.insurance", json={"value": "100", "reason": "insurance invoice received"}, headers=world.h("REVIEWER"))
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h())
    tax = assess(client, world, cid, "TAX", its[2]["id"])
    assert tax["inputs"]["fta_applied"] is True and tax["result"]["import_duty"] == "0.00"
    acts = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "co.apply" in acts


def test_policy_undetermined_until_hs_approved_then_requirements(world, client):
    case = run(world, client)
    cid = case["id"]
    its = items(client, world, cid)
    assert ("POLICY_UNDETERMINED", "item:3") in open_codes(client, world, cid)
    assert assess(client, world, cid, "POLICY", its[3]["id"])["status"] == "UNDETERMINED"
    assert ("POLICY_PENDING_HS", "item:1") in open_codes(client, world, cid)
    approve_hs(client, world, cid, its[3], "85371099")
    codes = open_codes(client, world, cid)
    assert ("POLICY_UNDETERMINED", "item:3") not in codes
    assert ("POLICY_REQUIREMENT", "item:3") in codes
    pol = assess(client, world, cid, "POLICY", its[3]["id"])
    assert pol["status"] == "REQUIREMENTS_PENDING_REVIEW"
    assert pol["result"]["requirements"][0]["code"] == "QC-ELEC" and pol["result"]["requirements"][0]["evidence_present"] is False


def test_knowledge_datasets_are_labelled_demo_versioned_and_fail_closed_when_inactive(world, client):
    ds = client.get("/api/v1/knowledge/datasets", headers=world.h()).json()
    assert {d["kind"] for d in ds} == {"HS_RULES", "TARIFF", "FTA", "POLICY"}
    assert all(d["is_demo"] and "NON-AUTHORITATIVE" in d["label"] and d["version"].startswith("demo-") and d["effective_from"] for d in ds)
    hs = next(d for d in ds if d["kind"] == "HS_RULES")
    detail = client.get(f"/api/v1/knowledge/datasets/{hs['id']}", headers=world.h()).json()
    assert any(r["heading"] == "8413" for r in detail["rules"])
    patch = {"is_active": False, "reason": "testing fail-closed"}
    assert client.patch(f"/api/v1/knowledge/datasets/{hs['id']}", json=patch, headers=world.h("REVIEWER")).status_code == 403
    assert client.patch(f"/api/v1/knowledge/datasets/{hs['id']}", json=patch, headers=world.h("ADMIN")).status_code == 200
    try:
        case = run(world, client, docs=("INVOICE",))
        codes = open_codes(client, world, case["id"])
        assert ("HS_KNOWLEDGE_UNAVAILABLE", None) in codes
        assert client.get(f"/api/v1/cases/{case['id']}", headers=world.h()).json()["status"] == "BLOCKED"
        assert all(i["candidates"] == [] for i in items(client, world, case["id"]).values())
    finally:
        client.patch(f"/api/v1/knowledge/datasets/{hs['id']}", json={"is_active": True, "reason": "restore"}, headers=world.h("ADMIN"))
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert ("HS_KNOWLEDGE_UNAVAILABLE", None) not in open_codes(client, world, case["id"])


def test_invoice_total_mismatch_flagged(world, client):
    inv = open(__import__("conftest").FIXTURES + "/invoice.txt", "rb").read().replace(b"Total Amount: 1980.00", b"Total Amount: 17900.00")
    case = run(world, client, docs=(), extra=(("INVOICE", "invoice.txt", inv),))
    assert ("INVOICE_TOTAL_MISMATCH", "invoice.total_amount") in open_codes(client, world, case["id"])
    assert assess(client, world, case["id"], "VALUATION")["inputs"]["line_sum"] == "1980.00"
