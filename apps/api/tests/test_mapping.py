from conftest import upload


def setup_case(world, client, docs=("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO")):
    from conftest import FIXTURE_FILES

    case = world.create_case()
    for d in docs:
        assert upload(client, world.h(), case["id"], d, FIXTURE_FILES[d]).status_code == 201
    r = client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    assert r.status_code == 200, r.text
    return case, r.json()


def fields_by_key(client, world, case_id):
    return {f["key"]: f for f in client.get(f"/api/v1/cases/{case_id}/fields", headers=world.h()).json()}


def test_pipeline_parses_documents_and_maps_fields_with_lineage(world, client):
    case, out = setup_case(world, client)
    assert out["documents_parsed"] == 4
    fields = fields_by_key(client, world, case["id"])
    inv = fields["invoice.number"]
    assert inv["value"] == "INV-2026-889"
    assert inv["origin"] == "AI" and inv["method"] == "mock.key-value"
    assert inv["source_document_id"] and inv["source_ref"].startswith("invoice.txt#line=")
    assert 0 < inv["confidence"] <= 1
    assert inv["is_critical"] and inv["review_status"] == "NEEDS_REVIEW"  # critical → never auto-accepted
    assert fields["transport.vessel"]["review_status"] == "AUTO_ACCEPTABLE"
    ex = client.get(f"/api/v1/cases/{case['id']}/extractions", headers=world.h()).json()
    assert any(e["key"] == "items[3].model" and e["value"] == "CT-88" for e in ex)
    assert all(e["provider"] == "mock" and e["provider_version"] for e in ex)
    docs = client.get(f"/api/v1/cases/{case['id']}/documents", headers=world.h()).json()
    assert all(d["status"] == "PARSED" and d["parse_provider"] == "mock" for d in docs)


def test_package_count_conflict_detected_with_evidence(world, client):
    case, out = setup_case(world, client, docs=("INVOICE", "PACKING_LIST"))
    issues = client.get(f"/api/v1/cases/{case['id']}/issues?status=OPEN", headers=world.h()).json()
    conflict = next(i for i in issues if i["code"] == "DOCUMENT_CONFLICT" and i["target_ref"] == "shipment.total_packages")
    assert conflict["severity"] == "WARNING"
    assert {e["value"] for e in conflict["evidence"]} == {"124", "126"}
    assert {e["doc_type"] for e in conflict["evidence"]} == {"INVOICE", "PACKING_LIST"}
    pk = fields_by_key(client, world, case["id"])["shipment.total_packages"]
    assert pk["value"] == "126"  # packing list has source priority
    assert pk["review_status"] == "NEEDS_REVIEW" and pk["alternatives"][0]["value"] == "124"
    assert out["status"] in ("REVIEW_REQUIRED", "BLOCKED")


def test_fob_without_insurance_raises_valuation_warning(world, client):
    import os

    from conftest import FIXTURES

    inv = open(os.path.join(FIXTURES, "invoice.txt"), "rb").read().replace(b"Insurance: 100.00\n", b"")
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", "invoice.txt", content=inv)
    assert client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h()).status_code == 200
    codes = {(i["code"], i["target_ref"]) for i in client.get(f"/api/v1/cases/{case['id']}/issues", headers=world.h()).json()}
    assert ("VALUATION_INPUT_MISSING", "valuation.insurance") in codes


def test_reviewer_resolves_conflict_by_choosing_value_and_rerun_does_not_overwrite(world, client):
    case, _ = setup_case(world, client, docs=("INVOICE", "PACKING_LIST"))
    r = client.post(f"/api/v1/cases/{case['id']}/fields/shipment.total_packages/approve",
                    json={"value": "126", "reason": "Packing list verified with warehouse"}, headers=world.h("REVIEWER"))
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "APPROVED" and r.json()["origin"] == "REVIEWER"
    # re-run pipeline → approved value preserved, conflict issue stays visible as evidence but field not reset
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    pk = fields_by_key(client, world, case["id"])["shipment.total_packages"]
    assert pk["value"] == "126" and pk["review_status"] == "APPROVED"
    audit = client.get(f"/api/v1/cases/{case['id']}/audit", headers=world.h()).json()
    ev = next(e for e in audit if e["action"] == "field.manual_set")
    assert ev["actor_role"] == "REVIEWER" and ev["before"]["review_status"] == "NEEDS_REVIEW" and ev["after"]["value"] == "126"
    assert ev["reason"] == "Packing list verified with warehouse"


def test_operator_edit_of_critical_field_requires_review(world, client):
    case, _ = setup_case(world, client, docs=("INVOICE",))
    r = client.put(f"/api/v1/cases/{case['id']}/fields/valuation.insurance", json={"value": "100", "reason": "per broker quote"},
                   headers=world.h("OPERATOR"))
    assert r.status_code == 200 and r.json()["review_status"] == "NEEDS_REVIEW"
    assert client.post(f"/api/v1/cases/{case['id']}/fields/valuation.insurance/approve", headers=world.h("OPERATOR")).status_code == 403
    r = client.post(f"/api/v1/cases/{case['id']}/fields/valuation.insurance/approve", headers=world.h("REVIEWER"))
    assert r.status_code == 200 and r.json()["review_status"] == "APPROVED"


def test_unknown_field_key_and_no_documents_rejected(world, client):
    case = world.create_case()
    assert client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h()).status_code == 409
    upload(client, world.h(), case["id"], "INVOICE", "invoice.txt")
    r = client.put(f"/api/v1/cases/{case['id']}/fields/hacker.key", json={"value": "x", "reason": "abc"}, headers=world.h())
    assert r.status_code == 422


def test_binary_document_fails_closed_to_manual_review(world, client):
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", "scan.pdf", content=b"%PDF-1.4\x00\xff\xfe binary")
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    doc = client.get(f"/api/v1/cases/{case['id']}/documents", headers=world.h()).json()[0]
    assert doc["status"] == "PARSE_FAILED" and any("manual review" in w for w in doc["parse_warnings"])
    assert fields_by_key(client, world, case["id"]) == {}  # nothing fabricated
