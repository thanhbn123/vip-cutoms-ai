from conftest import FIXTURE_FILES, upload


def new_case(world, client, extra=()):
    case = world.create_case()
    cid = case["id"]
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), cid, d, FIXTURE_FILES[d])
    for d, fn in extra:
        upload(client, world.h(), cid, d, fn)
    assert client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h()).status_code == 200
    return cid, {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}


def decide(client, world, cid, item, decision, code=None, role="REVIEWER"):
    body = {"decision": decision, "reason": "verified by reviewer with catalogue"} | ({"hs_code": code} if code else {})
    r = client.post(f"/api/v1/cases/{cid}/items/{item['id']}/hs-decision", json=body, headers=world.h(role))
    assert r.status_code == 201, r.text
    return r.json()


def memory(client, world, tenant="T1", **params):
    return client.get("/api/v1/memory", params=params, headers=world.h("OPERATOR", tenant)).json()


def test_rejected_ai_suggestion_does_not_enter_memory(world, client):
    cid, its = new_case(world, client)
    decide(client, world, cid, its[1], "REJECT")
    assert memory(client, world) == []


def test_approved_decision_enters_memory_with_lineage(world, client):
    cid, its = new_case(world, client)
    dec = decide(client, world, cid, its[1], "APPROVE", "84137099")
    mem = memory(client, world)
    assert len(mem) == 1
    m = mem[0]
    assert m["hs_code"] == "84137099" and m["model"] == "ABC-500" and m["decision_id"] == dec["id"] and m["approved_by_role"] == "REVIEWER"
    assert m["reusable"] is True and m["outcome"] == "UNKNOWN" and len(m["evidence_hash"]) == 64 and m["fingerprint"] == its[1]["fingerprint"]
    assert memory(client, world, tenant="T2") == []  # tenant isolation
    acts = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "memory.recorded" in acts


def test_history_boosts_next_case_and_consultation_outcome_is_reference_only(world, client):
    cid1, its1 = new_case(world, client)
    baseline = its1[1]["candidates"][0]["confidence"]
    decide(client, world, cid1, its1[1], "APPROVE", "84137099")
    cid2, its2 = new_case(world, client)
    top = its2[1]["candidates"][0]
    assert top["heading"] == "8413" and top["confidence"] == round(baseline + 0.05, 2)
    assert top["history_refs"][0]["match"] == "EXACT" and top["history_refs"][0]["hs_code"] == "84137099"
    assert any("Lịch sử đã duyệt" in r for r in top["reasoning"])
    hist = client.get(f"/api/v1/cases/{cid2}/items/{its2[1]['id']}/history", headers=world.h()).json()
    assert hist["comparison"][0]["hs_previous"] == "84137099" and hist["comparison"][0]["price_flag"] == "NORMAL"
    # senior marks the earlier decision as CONSULTATION → never auto-copied
    mid = memory(client, world)[0]["id"]
    assert client.post(f"/api/v1/memory/{mid}/outcome", json={"outcome": "CONSULTATION", "reason": "customs consulted"}, headers=world.h("REVIEWER")).status_code == 403
    r = client.post(f"/api/v1/memory/{mid}/outcome", json={"outcome": "CONSULTATION", "reason": "customs consulted"}, headers=world.h("SENIOR_REVIEWER"))
    assert r.status_code == 200 and r.json()["reusable"] is False
    cid3, its3 = new_case(world, client)
    top3 = its3[1]["candidates"][0]
    assert top3["confidence"] == baseline  # no boost
    assert top3["history_refs"][0]["reusable"] is False and any("KHÔNG tự áp dụng" in r for r in top3["reasoning"])


def test_copilot_uses_history_for_price_anomaly(world, client):
    cid1, its1 = new_case(world, client)
    decide(client, world, cid1, its1[3], "APPROVE", "85371099", role="SENIOR_REVIEWER") if False else None
    decide(client, world, cid1, its1[2], "APPROVE", "39172300")
    inv = open(__import__("conftest").FIXTURES + "/invoice.txt", "rb").read().replace(b"| 1.20 | 600.00", b"| 0.90 | 450.00").replace(b"Total Amount: 17900.00", b"Total Amount: 17750.00")
    case = world.create_case()
    upload(client, world.h(), case["id"], "INVOICE", "invoice.txt", content=inv)
    client.post(f"/api/v1/cases/{case['id']}/pipeline/run", headers=world.h())
    a = client.post(f"/api/v1/cases/{case['id']}/copilot/ask", json={"question": "trị giá có bất thường không?"}, headers=world.h()).json()
    assert "-25.0%" in a["answer"] and "bất thường" in a["answer"]
