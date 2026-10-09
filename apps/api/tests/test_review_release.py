import json

from conftest import FIXTURE_FILES, upload


def api(client, world, method, path, role="OPERATOR", **kw):
    return getattr(client, method)(f"/api/v1{path}", headers=world.h(role), **kw)


def setup(world, client, with_catalogue=True):
    case = world.create_case()
    cid = case["id"]
    for d in ("INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO"):
        upload(client, world.h(), cid, d, FIXTURE_FILES[d])
    if with_catalogue:
        upload(client, world.h(), cid, "CATALOGUE", "catalogue_ct88.txt")
    assert api(client, world, "post", f"/cases/{cid}/pipeline/run").status_code == 200
    return cid


def open_issues(client, world, cid):
    return api(client, world, "get", f"/cases/{cid}/issues?status=OPEN").json()


def items(client, world, cid):
    return {i["line_no"]: i for i in api(client, world, "get", f"/cases/{cid}/items").json()}


def drive_to_reviewed(client, world, cid):
    """Reviewer workflow: approve HS, C/O decisions, insurance, approve fields, close remaining warnings."""
    its = items(client, world, cid)
    for n, code in ((1, "84137099"), (2, "39172300"), (3, "85371099")):
        r = api(client, world, "post", f"/cases/{cid}/items/{its[n]['id']}/hs-decision", role="REVIEWER",
                json={"decision": "APPROVE", "hs_code": code, "reason": "classification verified with catalogue and notes"})
        assert r.status_code == 201, r.text
    api(client, world, "post", f"/cases/{cid}/items/{its[2]['id']}/co-decision", role="REVIEWER", json={"decision": "APPLY", "reason": "Form E verified"})
    api(client, world, "post", f"/cases/{cid}/items/{its[1]['id']}/co-decision", role="REVIEWER", json={"decision": "DO_NOT_APPLY", "reason": "model missing"})
    for n in (1, 2, 3):
        api(client, world, "patch", f"/cases/{cid}/items/{its[n]['id']}", role="OPERATOR",
            json={"description_vn": f"Mô tả khai báo dòng {n}, hàng mới 100%", "reason": "reviewed description"})
    assert api(client, world, "put", f"/cases/{cid}/fields/valuation.insurance", role="REVIEWER",
               json={"value": "100", "reason": "insurance invoice received"}).status_code == 200
    assert api(client, world, "post", f"/cases/{cid}/fields/shipment.total_packages/approve", role="REVIEWER",
               json={"value": "126", "reason": "verified with warehouse"}).status_code == 200
    for i in open_issues(client, world, cid):  # conflicts must be closed before approve-all accepts the field
        if i["category"] in ("DOCUMENT_CONFLICT", "VALIDATION"):
            api(client, world, "post", f"/cases/{cid}/issues/{i['id']}/resolve", role="REVIEWER", json={"reason": "verified against source documents"})
    r = api(client, world, "post", f"/cases/{cid}/fields/approve-all", role="REVIEWER", json={"reason": "header fields verified"})
    assert r.status_code == 200, r.text
    for i in open_issues(client, world, cid):
        if i["severity"] == "CRITICAL":
            # G18C: system-detected critical conditions cannot be "resolved" by hand — a Senior waives them with evidence (D-009)
            r = api(client, world, "post", f"/cases/{cid}/issues/{i['id']}/waive", role="SENIOR_REVIEWER",
                    json={"reason": "reviewed and confirmed by senior reviewer", "evidence": ["review-memo"]})
        else:
            r = api(client, world, "post", f"/cases/{cid}/issues/{i['id']}/resolve", role="REVIEWER", json={"reason": "reviewed and confirmed by reviewer"})
        assert r.status_code == 200, r.text
    return its


def test_critical_issue_prevents_release_but_allows_watermarked_preview(world, client):
    cid = setup(world, client, with_catalogue=False)
    assert api(client, world, "get", f"/cases/{cid}").json()["status"] == "BLOCKED"
    r = api(client, world, "post", f"/cases/{cid}/mark-ready", role="REVIEWER", json={"reason": "try release"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RELEASE_GATE_FAILED"
    failed = {c["code"] for c in r.json()["detail"]["details"]["checks"]}
    assert {"NO_OPEN_CRITICAL", "ITEMS_HS_APPROVED"} <= failed
    r = api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RELEASE_BLOCKED"
    r = api(client, world, "post", f"/cases/{cid}/drafts", role="OPERATOR", json={"kind": "PREVIEW"})
    assert r.status_code == 201 and r.json()["release_eligible"] is False and "NOT FOR SUBMISSION" in r.json()["watermark"]
    assert api(client, world, "get", f"/cases/{cid}").json()["status"] == "BLOCKED"  # preview never changes state
    gate = api(client, world, "get", f"/cases/{cid}/release-gate").json()
    assert gate["eligible"] is False


def test_declaration_view_has_sections_lineage_items_and_validation(world, client):
    cid = setup(world, client)
    d = api(client, world, "get", f"/cases/{cid}/declaration").json()
    assert [s["id"] for s in d["sections"]] == ["general", "transport", "invoice", "valuation", "origin"]
    inv = next(f for s in d["sections"] for f in s["fields"] if f["key"] == "invoice.number")
    assert inv["value"] == "INV-2026-889" and inv["confidence"] and inv["source"]["source_ref"] and inv["review_status"] == "NEEDS_REVIEW"
    assert len(d["items"]) == 3 and d["items"][0]["hs"]["candidate"]["heading"] == "8413"
    assert 0 <= d["readiness"] <= 100 and d["release_eligible"] is False
    assert {c["code"] for c in d["validation"]} >= {"NO_OPEN_CRITICAL", "ITEMS_HS_APPROVED", "CRITICAL_FIELDS_APPROVED", "VALUATION_COMPUTED"}
    assert "NON-AUTHORITATIVE" in d["disclaimer"]


def test_full_reviewer_path_to_ready_and_versioned_release_draft(world, client):
    cid = setup(world, client)
    drive_to_reviewed(client, world, cid)
    assert open_issues(client, world, cid) == []
    case = api(client, world, "get", f"/cases/{cid}").json()
    assert case["status"] == "REVIEWED"
    gate = api(client, world, "get", f"/cases/{cid}/release-gate").json()
    assert gate["eligible"] is True, [c for c in gate["checks"] if not c["ok"]]
    assert api(client, world, "post", f"/cases/{cid}/mark-ready", role="OPERATOR", json={"reason": "x" * 5}).status_code == 403
    r = api(client, world, "post", f"/cases/{cid}/mark-ready", role="REVIEWER", json={"reason": "all checks passed"})
    assert r.status_code == 200 and r.json()["status"] == "READY_TO_EXPORT"
    assert api(client, world, "post", f"/cases/{cid}/drafts", role="OPERATOR", json={"kind": "RELEASE"}).status_code == 403
    r = api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE", "reason": "release draft for broker"})
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["version"] == 1 and draft["release_eligible"] is True and "NOT A CUSTOMS SUBMISSION" in draft["watermark"]
    assert api(client, world, "get", f"/cases/{cid}").json()["status"] == "DRAFT_EXPORTED"
    body = api(client, world, "get", f"/drafts/{draft['id']}?format=json")
    payload = json.loads(body.content)
    assert payload["meta"]["schema_version"] == "internal-draft-v1" and payload["items"][2]["hs"]["code"] == "85371099"
    assert payload["items"][1]["tax"]["result"]["import_duty"] == "0.00"  # FTA applied on item 2
    assert body.headers["X-Draft-Checksum"] == draft["checksum"]
    csv_body = api(client, world, "get", f"/drafts/{draft['id']}?format=csv").content.decode("utf-8-sig")
    assert csv_body.startswith("# DRAFT") and "85371099" in csv_body
    r2 = api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE"})
    assert r2.json()["version"] == 2
    assert [d["version"] for d in api(client, world, "get", f"/cases/{cid}/drafts").json()] == [1, 2]
    acts = [e["action"] for e in api(client, world, "get", f"/cases/{cid}/audit").json()]
    assert acts.count("draft.exported") == 2 and "issue.resolved" in acts and "hs.approve" in acts and "case.status_changed" in acts
    assert api(client, world, "get", "/audit/verify").json()["chain_valid"] is True


def test_issue_actions_rbac_and_critical_waiver_rules(world, client):
    cid = setup(world, client, with_catalogue=False)
    issues = open_issues(client, world, cid)
    crit = next(i for i in issues if i["severity"] == "CRITICAL")
    warn = next(i for i in issues if i["severity"] == "WARNING")
    assert api(client, world, "post", f"/cases/{cid}/issues/{warn['id']}/resolve", role="OPERATOR", json={"reason": "operator says ok"}).status_code == 403
    assert api(client, world, "post", f"/cases/{cid}/issues/{warn['id']}/resolve", role="ADMIN", json={"reason": "admin says ok"}).status_code == 403
    assert api(client, world, "post", f"/cases/{cid}/issues/{crit['id']}/waive", role="REVIEWER", json={"reason": "reviewer waives"}).status_code == 403
    r = api(client, world, "post", f"/cases/{cid}/issues/{crit['id']}/waive", role="SENIOR_REVIEWER", json={"reason": "senior waives w/o evidence"})
    assert r.status_code == 422
    r = api(client, world, "post", f"/cases/{cid}/issues/{crit['id']}/waive", role="SENIOR_REVIEWER",
            json={"reason": "customer declaration accepted", "evidence": ["email-2026-10-07"]})
    assert r.status_code == 200 and r.json()["status"] == "WAIVED"
    r = api(client, world, "post", f"/cases/{cid}/issues/{warn['id']}/waive", role="REVIEWER", json={"reason": "immaterial difference"})
    assert r.status_code == 200 and r.json()["status"] == "WAIVED"
    assert api(client, world, "post", f"/cases/{cid}/issues/{warn['id']}/resolve", role="REVIEWER", json={"reason": "again"}).status_code == 409
    ev = [e for e in api(client, world, "get", f"/cases/{cid}/audit").json() if e["action"] == "issue.waived"]
    assert ev[0]["actor_role"] == "SENIOR_REVIEWER" and ev[0]["evidence"] == ["email-2026-10-07"] and ev[0]["before"] == {"status": "OPEN"}
    assert api(client, world, "get", f"/cases/{cid}/issues/{crit['id']}/resolve", role="REVIEWER").status_code in (404, 405)


def test_approve_all_skips_conflicted_fields(world, client):
    cid = setup(world, client)
    r = api(client, world, "post", f"/cases/{cid}/fields/approve-all", role="REVIEWER", json={"reason": "bulk approve"})
    assert "shipment.total_packages" in r.json()["skipped"]  # open conflict 124 vs 126
    assert "invoice.number" in r.json()["approved"]


def test_queue_and_dashboard_are_tenant_scoped(world, client):
    cid = setup(world, client, with_catalogue=False)
    q = api(client, world, "get", "/review/queue", role="REVIEWER").json()
    assert [r["case_id"] for r in q] == [cid] and q[0]["open_critical"] >= 1 and q[0]["top_issues"][0]["severity"] == "CRITICAL"
    assert api(client, world, "get", "/review/queue", role="REVIEWER", **{}).json() == q
    assert client.get("/api/v1/review/queue", headers=world.h("REVIEWER", "T2")).json() == []
    dash = api(client, world, "get", "/dashboard/summary").json()
    assert dash["cases_by_status"].get("BLOCKED") == 1 and dash["open_issues"]["CRITICAL"] >= 1
    assert client.get("/api/v1/dashboard/summary", headers=world.h("OPERATOR", "T2")).json()["cases_by_status"] == {}


def test_new_upload_after_export_reopens_case(world, client):
    cid = setup(world, client)
    drive_to_reviewed(client, world, cid)
    api(client, world, "post", f"/cases/{cid}/mark-ready", role="REVIEWER", json={"reason": "all checks passed"})
    api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE"})
    assert upload(client, world.h(), cid, "INVOICE", "invoice.txt", content=b"Invoice No: INV-2026-889-R2\nTotal Amount: 1980.00\n").status_code == 201
    assert api(client, world, "get", f"/cases/{cid}").json()["status"] == "DOCUMENTS_UPLOADED"
    api(client, world, "post", f"/cases/{cid}/pipeline/run")
    assert api(client, world, "get", f"/cases/{cid}").json()["status"] in ("REVIEW_REQUIRED", "BLOCKED")
    assert api(client, world, "post", f"/cases/{cid}/drafts", role="REVIEWER", json={"kind": "RELEASE"}).status_code == 409
