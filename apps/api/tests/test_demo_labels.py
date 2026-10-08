"""Demo knowledge must be unmistakable: is_demo flags + visible wording on every surface that shows rule-derived values (D-029)."""

from conftest import FIXTURE_FILES, upload

WORDS = ("DEMO DATA", "NON-AUTHORITATIVE", "NOT FOR CUSTOMS FILING")


def _setup(world, client):
    case = world.create_case()
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), case["id"], d, FIXTURE_FILES[d])
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    return case["id"]


def test_every_dataset_is_flagged_and_labelled(world, client):
    ds = client.get("/api/v1/knowledge/datasets", headers=world.h()).json()
    assert ds and all(d["is_demo"] for d in ds)
    for d in ds:
        assert all(w in d["label"] for w in WORDS), d["label"]
        assert d["version"].startswith("demo-") and d["source"]
    notice = client.get("/api/v1/knowledge/notice", headers=world.h()).json()
    assert notice["demo_active"] is True and all(w in notice["notice"] for w in WORDS) and notice["non_demo_datasets"] == []


def test_rule_derived_outputs_carry_the_demo_notice(world, client):
    cid = _setup(world, client)
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    assert all(c["dataset_version"].startswith("demo-") for it in items.values() for c in it["candidates"])
    r = client.post(f"/api/v1/cases/{cid}/items/{items[2]['id']}/hs-decision", headers=world.h("REVIEWER"),
                    json={"decision": "APPROVE", "hs_code": "39172300", "reason": "verified for label test"})
    assert r.status_code == 201
    tax = next(a for a in client.get(f"/api/v1/cases/{cid}/assessments", headers=world.h()).json() if a["kind"] == "TAX" and a["item_id"] == items[2]["id"])
    assert tax["dataset_is_demo"] is True and all(w in tax["result"]["label"] for w in WORDS)
    decl = client.get(f"/api/v1/cases/{cid}/declaration", headers=world.h()).json()
    assert decl["demo_datasets"] and all(w in decl["demo_notice"] for w in WORDS) and all(w in decl["disclaimer"] for w in WORDS)
    draft = client.post(f"/api/v1/cases/{cid}/drafts", json={"kind": "PREVIEW"}, headers=world.h()).json()
    payload = client.get(f"/api/v1/drafts/{draft['id']}?format=json", headers=world.h()).json()
    assert all(w in payload["meta"]["legal_notice"] for w in WORDS) and payload["meta"]["demo_datasets"] == decl["demo_datasets"]
    csv_text = client.get(f"/api/v1/drafts/{draft['id']}?format=csv", headers=world.h()).content.decode("utf-8-sig")
    assert "NOT FOR CUSTOMS FILING" in csv_text.splitlines()[0]
