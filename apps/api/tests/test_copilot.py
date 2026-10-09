from conftest import FIXTURE_FILES, upload


def setup(world, client):
    case = world.create_case()
    cid = case["id"]
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), cid, d, FIXTURE_FILES[d])
    assert client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=world.h()).status_code == 200
    return cid


def ask(client, world, cid, q, role="OPERATOR"):
    r = client.post(f"/api/v1/cases/{cid}/copilot/ask", json={"question": q}, headers=world.h(role))
    assert r.status_code == 200, r.text
    return r.json()


def test_missing_question_lists_open_issues_with_sources(world, client):
    cid = setup(world, client)
    a = ask(client, world, cid, "Còn thiếu gì để khai?")
    assert a["intent"] == "MISSING" and "critical" in a["answer"]
    assert a["requires_review"] is True and a["confidence"] >= 0.9 and any("Item 3" in x for x in a["recommended_actions"])
    assert "Item 3" in a["answer"] and "BLOCKED" in a["answer"]
    issue_ids = {i["id"] for i in client.get(f"/api/v1/cases/{cid}/issues?status=OPEN", headers=world.h()).json()}
    assert a["sources"] and all(s["id"] in issue_ids for s in a["sources"] if s["type"] == "issue")
    assert a["reasoning"] and a["provider"] == "mock"


def test_why_hs_explains_candidate_missing_attributes_and_dataset(world, client):
    cid = setup(world, client)
    a = ask(client, world, cid, "Vì sao item 3 chưa chốt được HS?")
    assert a["intent"] == "HS_WHY" and "8537" in a["answer"] and "BLOCKED" in a["answer"]
    assert "function" in a["answer"] and "voltage" in a["answer"]
    assert any(s["type"] == "hs_candidate" and "demo-" in s["label"] for s in a["sources"])
    assert "reviewer" in a["answer"].lower()


def test_form_e_and_valuation_questions_use_case_context_only(world, client):
    cid = setup(world, client)
    a = ask(client, world, cid, "Form E có vấn đề gì?")
    assert a["intent"] == "CO" and "Item 1" in a["answer"] and ("không khớp" in a["answer"] or "CO_LINE_MISMATCH" in str(a["sources"]))
    v = ask(client, world, cid, "Kiểm tra trị giá lô hàng")
    assert v["intent"] == "VALUATION" and "18420.00" in v["answer"] and "Tổng Invoice" in v["answer"]  # CIF + line-sum warning, from case data
    assert "lịch sử" in v["answer"].lower()  # explicitly says there is no history to compare


def test_describe_creates_proposal_that_requires_reviewer_and_separation_of_duties(world, client):
    cid = setup(world, client)
    a = ask(client, world, cid, "Đề xuất mô tả item 1", role="REVIEWER")
    assert a["intent"] == "DESCRIBE" and a["proposal_id"]
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    assert items[1]["description_vn"] is None  # nothing applied yet
    props = client.get(f"/api/v1/cases/{cid}/proposals", headers=world.h()).json()
    assert props[0]["status"] == "PROPOSED" and "ABC-500" in props[0]["proposed_value"] and props[0]["reasoning"]
    url = f"/api/v1/cases/{cid}/proposals/{props[0]['id']}/decide"
    assert client.post(url, json={"decision": "APPROVE", "reason": "fine"}, headers=world.h("OPERATOR")).status_code == 403
    r = client.post(url, json={"decision": "APPROVE", "reason": "fine"}, headers=world.h("REVIEWER"))  # same user who asked
    assert r.status_code == 409 and r.json()["detail"]["code"] == "SEPARATION_OF_DUTIES"
    r = client.post(url, json={"decision": "APPROVE", "reason": "description complete"}, headers=world.h("SENIOR_REVIEWER"))
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    assert items[1]["description_vn"] == props[0]["proposed_value"] and items[1]["description_vn_status"] == "APPROVED"
    acts = [e["action"] for e in client.get(f"/api/v1/cases/{cid}/audit", headers=world.h()).json()]
    assert "proposal.created" in acts and "proposal.approved" in acts and "copilot.answered" in acts
    assert client.post(url, json={"decision": "REJECT", "reason": "again"}, headers=world.h("SENIOR_REVIEWER")).status_code == 409


def test_rejected_proposal_changes_nothing(world, client):
    cid = setup(world, client)
    a = ask(client, world, cid, "đề xuất mô tả dòng 2", role="OPERATOR")
    r = client.post(f"/api/v1/cases/{cid}/proposals/{a['proposal_id']}/decide", json={"decision": "REJECT", "reason": "wording"}, headers=world.h("REVIEWER"))
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=world.h()).json()}
    assert items[2]["description_vn"] is None


def test_copilot_is_tenant_scoped_and_messages_persisted(world, client):
    cid = setup(world, client)
    assert client.post(f"/api/v1/cases/{cid}/copilot/ask", json={"question": "còn thiếu gì?"}, headers=world.h("OPERATOR", "T2")).status_code == 404
    ask(client, world, cid, "tóm tắt hồ sơ")
    msgs = client.get(f"/api/v1/cases/{cid}/copilot/messages", headers=world.h()).json()
    assert [m["role"] for m in msgs] == ["USER", "AI"] and msgs[1]["intent"] == "GENERAL" and msgs[1]["sources"]


def test_fabricated_sources_are_dropped(world, client, monkeypatch):
    from app.ai import gateway
    from app.ai.base import CopilotAnswer

    cid = setup(world, client)

    class Fake:
        name, version = "mock", "fake"

        def answer_case_question(self, q, ctx):
            return CopilotAnswer("answer", "GENERAL", [{"type": "document", "id": "00000000-0000-0000-0000-000000000000", "label": "x"}], ["r"], "mock")

    monkeypatch.setattr(gateway, "get_provider", lambda: Fake())
    monkeypatch.setattr("app.services.copilot.get_provider", lambda: Fake())
    a = ask(client, world, cid, "hello")
    assert a["sources"] == [] and any("[validation]" in r for r in a["reasoning"])
    assert a["confidence"] == 0.0  # Fake returned no confidence → never inflated


def test_five_mandated_questions_return_grounded_structured_answers(world, client):
    cid = setup(world, client)
    expected = {"Còn thiếu gì để khai?": "MISSING", "Form E có vấn đề gì?": "CO", "Tại sao Item 3 chưa chốt HS?": "HS_WHY",
                "Kiểm tra trị giá lô hàng": "VALUATION", "Đề xuất mô tả Item 1": "DESCRIBE"}
    for q, intent in expected.items():
        a = ask(client, world, cid, q, role="REVIEWER")
        assert a["intent"] == intent, (q, a["intent"])
        assert a["answer"] and isinstance(a["sources"], list) and a["reasoning"]
        assert 0.0 <= a["confidence"] <= 1.0 and isinstance(a["recommended_actions"], list) and isinstance(a["requires_review"], bool)
        assert a["requires_review"] is True  # case has a critical issue → every answer defers to the reviewer
    hs = ask(client, world, cid, "Tại sao Item 3 chưa chốt HS?")
    assert any("bổ sung" in x and "Item 3" in x for x in hs["recommended_actions"])
    msgs = client.get(f"/api/v1/cases/{cid}/copilot/messages", headers=world.h()).json()
    assert all(m["meta"].get("confidence") is not None for m in msgs if m["role"] == "AI")
