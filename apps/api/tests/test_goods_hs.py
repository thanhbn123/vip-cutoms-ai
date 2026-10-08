from conftest import FIXTURE_FILES, upload


def run(world, client, docs=("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"), extra=()):
    case = world.create_case()
    for d in docs:
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    for d, fn in extra:
        upload(client, world.h(), case["id"], d, fn)
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    return case, r.json()


def items(client, world, case_id):
    return {i["line_no"]: i for i in client.get(f"/api/v1/cases/{case_id}/items", headers=world.h()).json()}


def issues(client, world, case_id, status="OPEN"):
    return client.get(f"/api/v1/cases/{case_id}/issues?status={status}", headers=world.h()).json()


def test_three_items_built_with_lineage_and_candidates(world, client):
    case, out = run(world, client)
    its = items(client, world, case["id"])
    assert sorted(its) == [1, 2, 3]
    pump = its[1]
    assert pump["model"] == "ABC-500" and pump["quantity"] == "20" and pump["packages"] == "20"
    assert pump["source_ref"].startswith("invoice.txt#line=")
    assert pump["candidates"][0]["heading"] == "8413" and pump["candidates"][0]["reasoning"]
    assert pump["candidates"][0]["dataset_version"].startswith("demo-")
    assert pump["hs_status"] == "NEEDS_REVIEW"  # 0.70 ≤ conf < 0.90 → review
    pvc = its[2]
    assert pvc["candidates"][0]["heading"] == "3917" and pvc["candidates"][0]["confidence"] >= 0.90
    assert pvc["attributes"]["material"]["value"] == "PVC"
    assert pvc["hs_status"] == "NEEDS_REVIEW"  # high confidence still needs approval (D-008)


def test_low_confidence_item_is_blocked_and_blocks_case(world, client):
    case, out = run(world, client)
    ct88 = items(client, world, case["id"])[3]
    assert ct88["hs_status"] == "BLOCKED" and ct88["hs_confidence"] < 0.70
    assert set(ct88["candidates"][0]["missing_attributes"]) == {"function", "voltage", "application"}
    crit = [i for i in issues(client, world, case["id"]) if i["severity"] == "CRITICAL"]
    assert any(i["code"] == "HS_LOW_CONFIDENCE" and i["target_ref"] == "item:3" for i in crit)
    assert out["status"] == "BLOCKED"
    assert client.get(f"/api/v1/cases/{case['id']}", headers=world.h()).json()["status"] == "BLOCKED"


def test_catalogue_upload_lifts_blocked_item_to_review(world, client):
    case, _ = run(world, client, extra=(("CATALOGUE", "catalogue_ct88.txt"),))
    ct88 = items(client, world, case["id"])[3]
    assert ct88["attributes"]["voltage"]["source"] == "catalogue"
    assert ct88["hs_status"] == "NEEDS_REVIEW" and ct88["hs_confidence"] >= 0.70
    assert not any(i["code"] == "HS_LOW_CONFIDENCE" for i in issues(client, world, case["id"]))


def test_co_line_missing_model_flagged(world, client):
    case, _ = run(world, client)
    its = items(client, world, case["id"])
    assert its[1]["co_line_matched"] is False and its[2]["co_line_matched"] is True
    assert any(i["code"] == "CO_LINE_MISMATCH" and i["target_ref"] == "item:1" for i in issues(client, world, case["id"]))


def test_reviewer_approval_changes_item_state_and_clears_issue(world, client):
    case, _ = run(world, client)
    pump = items(client, world, case["id"])[1]
    cand = pump["candidates"][0]
    r = client.post(f"/api/v1/cases/{case['id']}/items/{pump['id']}/hs-decision",
                    json={"decision": "APPROVE", "hs_code": "84137099", "candidate_id": cand["id"], "reason": "Catalogue verified; centrifugal pump"},
                    headers=world.h("REVIEWER"))
    assert r.status_code == 201, r.text
    pump = items(client, world, case["id"])[1]
    assert pump["hs_status"] == "APPROVED" and pump["hs_code"] == "84137099"
    assert not any(i["target_ref"] == "item:1" and i["category"] == "HS" for i in issues(client, world, case["id"]))
    ev = [e for e in client.get(f"/api/v1/cases/{case['id']}/audit", headers=world.h()).json() if e["action"] == "hs.approve"]
    assert ev and ev[0]["before"]["hs_status"] == "NEEDS_REVIEW" and ev[0]["after"]["hs_code"] == "84137099"
    assert ev[0]["reason"].startswith("Catalogue verified")
    # re-running the pipeline does not reopen the approved decision
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert items(client, world, case["id"])[1]["hs_status"] == "APPROVED"


def test_hs_decision_rbac_validation_and_override_rules(world, client):
    case, _ = run(world, client)
    pump = items(client, world, case["id"])[1]
    url = f"/api/v1/cases/{case['id']}/items/{pump['id']}/hs-decision"
    ok = {"decision": "APPROVE", "hs_code": "84137099", "reason": "verified ok"}
    assert client.post(url, json=ok, headers=world.h("OPERATOR")).status_code == 403
    assert client.post(url, json=ok, headers=world.h("ADMIN")).status_code == 403
    assert client.post(url, json=ok | {"hs_code": "8413"}, headers=world.h("REVIEWER")).status_code == 422
    assert client.post(url, json={"decision": "APPROVE", "reason": "no code"}, headers=world.h("REVIEWER")).status_code == 422
    # code outside AI candidates: reviewer forbidden, senior needs evidence
    assert client.post(url, json=ok | {"hs_code": "85011000"}, headers=world.h("REVIEWER")).status_code == 403
    assert client.post(url, json=ok | {"hs_code": "85011000"}, headers=world.h("SENIOR_REVIEWER")).status_code == 422
    r = client.post(url, json=ok | {"hs_code": "85011000", "evidence": ["ruling-DEMO-001"]}, headers=world.h("SENIOR_REVIEWER"))
    assert r.status_code == 201 and r.json()["is_override"] is True


def test_rejected_candidate_keeps_item_unapproved(world, client):
    case, _ = run(world, client)
    pump = items(client, world, case["id"])[1]
    cand = pump["candidates"][0]
    r = client.post(f"/api/v1/cases/{case['id']}/items/{pump['id']}/hs-decision",
                    json={"decision": "REJECT", "candidate_id": cand["id"], "reason": "Not a liquid pump per catalogue"}, headers=world.h("REVIEWER"))
    assert r.status_code == 201 and r.json()["decision"] == "REJECT"
    pump = items(client, world, case["id"])[1]
    assert pump["hs_status"] != "APPROVED" and pump["hs_code"] is None
    decs = client.get(f"/api/v1/cases/{case['id']}/items/{pump['id']}/decisions", headers=world.h()).json()
    assert [d["decision"] for d in decs] == ["REJECT"]


def test_manual_attributes_rescore_item(world, client):
    case, _ = run(world, client)
    ct88 = items(client, world, case["id"])[3]
    r = client.patch(f"/api/v1/cases/{case['id']}/items/{ct88['id']}",
                     json={"attributes": {"function": "pump motor control panel", "voltage": "220V", "application": "pump station"},
                           "reason": "per customer email"}, headers=world.h("OPERATOR"))
    assert r.status_code == 200, r.text
    assert r.json()["hs_status"] == "NEEDS_REVIEW" and r.json()["attributes"]["voltage"]["source"] == "manual"
    assert client.get(f"/api/v1/cases/{case['id']}", headers=world.h()).json()["status"] == "REVIEW_REQUIRED"
