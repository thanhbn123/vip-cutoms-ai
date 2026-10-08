"""ACCEPTANCE MVP — the owner's 13-step scenario executed end-to-end through the public API (G12)."""

import json

from conftest import FIXTURE_FILES, upload
from test_review_release import drive_to_reviewed


def test_acceptance_mvp_thirteen_steps(world, client):
    H = world.h("OPERATOR")
    R = world.h("REVIEWER")

    # 1. tạo case
    case = world.create_case(priority="HIGH")
    cid = case["id"]
    assert case["status"] == "NEW" and case["case_no"].startswith("VIP-HQ-")

    # 2. upload bộ chứng từ (Invoice, Packing List, B/L, Form E)
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        assert upload(client, H, cid, d, FIXTURE_FILES[d]).status_code == 201
    assert client.get(f"/api/v1/cases/{cid}", headers=H).json()["status"] == "DOCUMENTS_UPLOADED"

    # 3. chạy parser (mock provider) + mapping + evaluators
    out = client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=H).json()
    assert out["documents_parsed"] == 4

    # 4. field được map kèm confidence/source
    fields = {f["key"]: f for f in client.get(f"/api/v1/cases/{cid}/fields", headers=H).json()}
    inv = fields["invoice.number"]
    assert inv["value"] == "INV-2026-889" and inv["confidence"] > 0.9 and inv["source_ref"] and inv["source_document_id"]
    assert fields["shipment.total_packages"]["alternatives"]  # 124 vs 126 conflict surfaced, not silently chosen

    # 5. thấy 3 line items
    items = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=H).json()}
    assert sorted(items) == [1, 2, 3]

    # 6. HS candidate với confidence + reasoning + dataset version
    assert items[1]["candidates"][0]["heading"] == "8413" and items[1]["candidates"][0]["reasoning"]
    assert items[1]["candidates"][0]["dataset_version"].startswith("demo-")

    # 7. item confidence thấp → BLOCKED, case BLOCKED
    assert items[3]["hs_status"] == "BLOCKED" and items[3]["hs_confidence"] < 0.70
    assert client.get(f"/api/v1/cases/{cid}", headers=H).json()["status"] == "BLOCKED"

    # 8. hỏi AI Copilot "còn thiếu gì?"
    a = client.post(f"/api/v1/cases/{cid}/copilot/ask", json={"question": "Còn thiếu gì để khai?"}, headers=H).json()
    assert a["intent"] == "MISSING" and "Item 3" in a["answer"] and a["sources"]

    # 9. reviewer xử lý issue (bổ sung catalogue → review → duyệt HS, C/O, trường critical, resolve warnings)
    assert upload(client, H, cid, "CATALOGUE", "catalogue_ct88.txt").status_code == 201
    client.post(f"/api/v1/cases/{cid}/pipeline/run", headers=H)
    assert {i["line_no"]: i for i in client.get(f"/api/v1/cases/{cid}/items", headers=H).json()}[3]["hs_status"] == "NEEDS_REVIEW"
    drive_to_reviewed(client, world, cid)

    # 10. audit lưu thay đổi với actor / before / after / reason
    audit = client.get(f"/api/v1/cases/{cid}/audit", headers=H).json()
    hs = next(e for e in audit if e["action"] == "hs.approve")
    assert hs["actor_type"] == "USER" and hs["actor_role"] == "REVIEWER" and hs["before"]["hs_code"] is None and hs["after"]["hs_code"] and hs["reason"]
    assert client.get("/api/v1/audit/verify", headers=H).json()["chain_valid"] is True

    # 11. hết critical → reviewer đánh dấu READY_TO_EXPORT
    assert client.get(f"/api/v1/cases/{cid}/issues?status=OPEN", headers=H).json() == []
    r = client.post(f"/api/v1/cases/{cid}/mark-ready", json={"reason": "all release checks passed"}, headers=R)
    assert r.status_code == 200 and r.json()["status"] == "READY_TO_EXPORT"

    # 12. xuất declaration DRAFT (JSON + CSV, versioned, checksum, watermark)
    d = client.post(f"/api/v1/cases/{cid}/drafts", json={"kind": "RELEASE", "reason": "owner acceptance"}, headers=R).json()
    assert d["version"] == 1 and d["release_eligible"] and "NOT A CUSTOMS SUBMISSION" in d["watermark"]
    payload = json.loads(client.get(f"/api/v1/drafts/{d['id']}?format=json", headers=H).content)
    assert payload["meta"]["schema_version"] == "internal-draft-v1" and len(payload["items"]) == 3
    assert all(it["hs"]["status"] == "APPROVED" for it in payload["items"])
    assert client.get(f"/api/v1/drafts/{d['id']}?format=csv", headers=H).status_code == 200
    assert client.get(f"/api/v1/cases/{cid}", headers=H).json()["status"] == "DRAFT_EXPORTED"

    # 13. approved decision xuất hiện trong historical memory
    mem = client.get("/api/v1/memory", headers=H).json()
    assert {m["hs_code"] for m in mem} == {"84137099", "39172300", "85371099"} and all(m["reusable"] for m in mem)

    # 14-16. new similar case (same customer/supplier/models) finds the approved history and is nudged, never auto-copied
    case2 = world.create_case()
    for d in ("INVOICE", "PACKING_LIST"):
        upload(client, H, case2["id"], d, FIXTURE_FILES[d])
    client.post(f"/api/v1/cases/{case2['id']}/pipeline/run", headers=H)
    items2 = {i["line_no"]: i for i in client.get(f"/api/v1/cases/{case2['id']}/items", headers=H).json()}
    top = items2[1]["candidates"][0]
    assert top["history_refs"][0]["match"] == "EXACT" and top["history_refs"][0]["hs_code"] == "84137099"
    assert top["confidence"] == round(items[1]["candidates"][0]["confidence"] + 0.05, 2)
    assert items2[1]["hs_status"] == "NEEDS_REVIEW" and items2[1]["hs_code"] is None  # history informs, reviewer still decides
    hist = client.get(f"/api/v1/cases/{case2['id']}/items/{items2[1]['id']}/history", headers=H).json()
    assert hist["comparison"][0]["hs_previous"] == "84137099" and hist["comparison"][0]["price_flag"] == "NORMAL"
