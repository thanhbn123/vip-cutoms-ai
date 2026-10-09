"""Owner acceptance flow A–P executed over HTTP against a running stack (Docker or native). Exit 1 on any failed step.

Usage: BASE_URL=http://localhost:8000 SEED_DEMO_PASSWORD=... apps/api/.venv/bin/python scripts/acceptance_http.py
Requires the demo tenant (scripts/seed_demo.py) — users operator/reviewer/senior@demo.local.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
PW = os.environ.get("SEED_DEMO_PASSWORD") or sys.exit("SEED_DEMO_PASSWORD required")
FIX = Path(__file__).resolve().parents[1] / "apps" / "api" / "tests" / "fixtures" / "minh_phat"
RESULTS: list[tuple[str, str, str]] = []


def step(code: str, title: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((code, title, "PASS" if ok else "FAIL", ))
    print(f"[{'PASS' if ok else 'FAIL'}] {code}. {title}" + (f" — {detail}" if detail else ""))
    if not ok:
        finish()


def finish() -> None:
    fails = [r for r in RESULTS if r[2] == "FAIL"]
    print(f"\nACCEPTANCE_HTTP: {len(RESULTS) - len(fails)}/{len(RESULTS)} steps PASS against {BASE}")
    sys.exit(1 if fails else 0)


class Api:
    def __init__(self, email: str):
        self.c = httpx.Client(base_url=BASE + "/api/v1", timeout=60)
        r = self.c.post("/auth/login", json={"email": email, "password": PW})
        r.raise_for_status()
        self.c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def __getattr__(self, name):
        return getattr(self.c, name)


def main() -> None:
    health = httpx.get(BASE + "/health", timeout=10).json()
    ready = httpx.get(BASE + "/ready", timeout=10).json()
    step("0", "health/ready", health["status"] == "ok" and ready["status"] == "ready", f"migrations={ready['checks']['migrations']} provider={ready['checks']['ai_provider']}")
    op, rv, sr = Api("operator@demo.local"), Api("reviewer@demo.local"), Api("senior@demo.local")
    step("A", "authentication/login (operator, reviewer, senior)", op.get("/auth/me").status_code == 200)

    customer = op.get("/customers").json()[0]
    supplier = op.get("/suppliers").json()[0]
    case = op.post("/cases", json={"customer_id": customer["id"], "supplier_id": supplier["id"], "declaration_type": "A11", "customs_office": "Bắc Ninh", "priority": "HIGH"}).json()
    cid = case["id"]
    step("B", "create case", case["status"] == "NEW", case["case_no"])

    for dt, fn in (("INVOICE", "invoice.txt"), ("PACKING_LIST", "packing_list.txt"), ("BILL_OF_LADING", "bill_of_lading.txt"), ("CO", "form_e.txt")):
        r = op.post(f"/cases/{cid}/documents", data={"doc_type": dt}, files={"file": (fn, (FIX / fn).read_bytes(), "text/plain")})
        assert r.status_code == 201, r.text
    step("C", "upload mock documents (Invoice, PL, B/L, Form E)", len(op.get(f"/cases/{cid}/documents").json()) == 4)

    run = op.post(f"/cases/{cid}/pipeline/run").json()
    docs = op.get(f"/cases/{cid}/documents").json()
    step("D", "parse with mock provider", run["documents_parsed"] == 4 and all(d["status"] == "PARSED" and d["parse_provider"] == "mock" for d in docs))

    issues = op.get(f"/cases/{cid}/issues", params={"status": "OPEN"}).json()
    conflict = next((i for i in issues if i["code"] == "DOCUMENT_CONFLICT" and i["target_ref"] == "shipment.total_packages"), None)
    step("E", "package conflict 124/126 detected, not auto-resolved", conflict is not None and {e["value"] for e in conflict["evidence"]} == {"124", "126"})

    items = {i["line_no"]: i for i in op.get(f"/cases/{cid}/items").json()}
    step("F", "3 goods items", sorted(items) == [1, 2, 3])
    c = {n: items[n]["candidates"][0] for n in (1, 2, 3)}
    # Reference values hold on an empty database. If approved memory for the same fingerprint already exists (re-run on a used
    # staging DB), the engine adds +0.05 (D-016) — accepted ONLY when history_refs are present, and reported explicitly.
    boosted = {n: bool(c[n]["history_refs"]) for n in (1, 2, 3)}
    exp = {1: 0.92 if boosted[1] else 0.87, 2: 0.99 if boosted[2] else 0.95, 3: 0.69 if boosted[3] else 0.64}
    step("G", "HS 0.87 review / 0.95 / 0.64 blocked" + (" (approved-memory boost +0.05 applied on re-used DB)" if any(boosted.values()) else ""),
         (c[1]["heading"], c[1]["confidence"], items[1]["hs_status"]) == ("8413", exp[1], "NEEDS_REVIEW")
         and (c[2]["heading"], c[2]["confidence"]) == ("3917", exp[2])
         and (c[3]["heading"], c[3]["confidence"], items[3]["hs_status"]) == ("8537", exp[3], "BLOCKED") and run["status"] == "BLOCKED",
         f"item1={c[1]['confidence']} item2={c[2]['confidence']} item3={c[3]['confidence']} history={boosted}")

    val = next(a for a in op.get(f"/cases/{cid}/assessments").json() if a["kind"] == "VALUATION")
    step("H", "valuation 17900 + 420 + 100 = 18420", val["status"] == "COMPUTED" and val["result"]["customs_value"] == "18420.00")

    assess = op.get(f"/cases/{cid}/assessments").json()
    co2 = next(a for a in assess if a["kind"] == "CO" and a["item_id"] == items[2]["id"])
    pol3 = next(a for a in assess if a["kind"] == "POLICY" and a["item_id"] == items[3]["id"])
    step("I", "C/O + policy demo rules (versioned, is_demo)", co2["status"] == "ELIGIBLE_PENDING_REVIEW" and pol3["status"] == "UNDETERMINED"
         and co2["dataset_is_demo"] and pol3["dataset_is_demo"] and co2["dataset_version"].startswith("demo-"))

    ans = op.post(f"/cases/{cid}/copilot/ask", json={"question": "Còn thiếu gì để khai?"}).json()
    step("J", "Copilot answers with sources/confidence/requires_review", ans["intent"] == "MISSING" and "Item 3" in ans["answer"] and ans["sources"] and ans["requires_review"] is True)

    # K. reviewer resolution
    op.post(f"/cases/{cid}/documents", data={"doc_type": "CATALOGUE"}, files={"file": ("catalogue_ct88.txt", (FIX / "catalogue_ct88.txt").read_bytes(), "text/plain")})
    op.post(f"/cases/{cid}/pipeline/run")
    items = {i["line_no"]: i for i in op.get(f"/cases/{cid}/items").json()}
    for n, code in ((1, "84137099"), (2, "39172300"), (3, "85371099")):
        r = rv.post(f"/cases/{cid}/items/{items[n]['id']}/hs-decision", json={"decision": "APPROVE", "hs_code": code, "reason": "verified with catalogue and classification notes"})
        assert r.status_code == 201, r.text
    rv.post(f"/cases/{cid}/items/{items[2]['id']}/co-decision", json={"decision": "APPLY", "reason": "Form E verified on issuing portal"})
    rv.post(f"/cases/{cid}/items/{items[1]['id']}/co-decision", json={"decision": "DO_NOT_APPLY", "reason": "model missing on Form E"})
    for n in (1, 2, 3):
        op.patch(f"/cases/{cid}/items/{items[n]['id']}", json={"description_vn": f"Mô tả khai báo dòng {n}, hàng mới 100%", "reason": "reviewed description"})
    rv.post(f"/cases/{cid}/fields/shipment.total_packages/approve", json={"value": "126", "reason": "verified with warehouse"})
    for i in op.get(f"/cases/{cid}/issues", params={"status": "OPEN"}).json():
        if i["category"] in ("DOCUMENT_CONFLICT", "VALIDATION"):
            rv.post(f"/cases/{cid}/issues/{i['id']}/resolve", json={"reason": "verified against source documents"})
    rv.post(f"/cases/{cid}/fields/approve-all", json={"reason": "header fields verified"})
    for i in op.get(f"/cases/{cid}/issues", params={"status": "OPEN"}).json():
        if i["severity"] == "CRITICAL":  # G18C: system-detected criticals are waived by a Senior with evidence, never "resolved"
            r = sr.post(f"/cases/{cid}/issues/{i['id']}/waive", json={"reason": "reviewed and confirmed by senior reviewer", "evidence": ["review-memo"]})
        else:
            r = rv.post(f"/cases/{cid}/issues/{i['id']}/resolve", json={"reason": "reviewed and confirmed by reviewer"})
        assert r.status_code == 200, r.text
    audit = op.get(f"/cases/{cid}/audit").json()
    hs = next(e for e in audit if e["action"] == "hs.approve")
    step("K", "reviewer resolution with audit (actor/before/after/reason)", not op.get(f"/cases/{cid}/issues", params={"status": "OPEN"}).json()
         and hs["actor_role"] == "REVIEWER" and hs["before"]["hs_code"] is None and hs["after"]["hs_code"] and hs["reason"]
         and op.get("/audit/verify").json()["chain_valid"] is True)

    gate = op.get(f"/cases/{cid}/release-gate").json()
    step("L", "release gate passes only after all checks", gate["eligible"] is True, f"status={gate['status']}")
    r = rv.post(f"/cases/{cid}/mark-ready", json={"reason": "all release checks passed"})
    step("M", "READY_TO_EXPORT after all critical resolved", r.status_code == 200 and r.json()["status"] == "READY_TO_EXPORT")

    d = rv.post(f"/cases/{cid}/drafts", json={"kind": "RELEASE", "reason": "docker acceptance"}).json()
    payload = json.loads(op.get(f"/drafts/{d['id']}", params={"format": "json"}).content)
    csv_ok = op.get(f"/drafts/{d['id']}", params={"format": "csv"}).status_code == 200
    step("N", "DRAFT export (versioned JSON + CSV, watermark, legal notice)", d["release_eligible"] and "NOT A CUSTOMS SUBMISSION" in d["watermark"]
         and payload["meta"]["schema_version"] == "internal-draft-v1" and "NOT FOR CUSTOMS FILING" in payload["meta"]["legal_notice"] and csv_ok
         and op.get(f"/cases/{cid}").json()["status"] == "DRAFT_EXPORTED")

    mem = op.get("/memory").json()
    step("O", "approved-only historical memory", {"84137099", "39172300", "85371099"} <= {m["hs_code"] for m in mem} and all(m["reusable"] for m in mem if m["case_no"] == case["case_no"]))

    case2 = op.post("/cases", json={"customer_id": customer["id"], "supplier_id": supplier["id"], "declaration_type": "A11"}).json()
    for dt, fn in (("INVOICE", "invoice.txt"), ("PACKING_LIST", "packing_list.txt")):
        op.post(f"/cases/{case2['id']}/documents", data={"doc_type": dt}, files={"file": (fn, (FIX / fn).read_bytes(), "text/plain")})
    op.post(f"/cases/{case2['id']}/pipeline/run")
    it2 = {i["line_no"]: i for i in op.get(f"/cases/{case2['id']}/items").json()}
    top = it2[1]["candidates"][0]
    step("P", "similar next case finds history (EXACT, +0.05, still NEEDS_REVIEW)",
         top["history_refs"] and top["history_refs"][0]["match"] == "EXACT" and top["confidence"] == 0.92 and it2[1]["hs_status"] == "NEEDS_REVIEW")
    finish()


if __name__ == "__main__":
    main()
