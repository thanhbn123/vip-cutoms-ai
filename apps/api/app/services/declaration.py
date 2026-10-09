"""Smart Declaration read-model: every field carries value, confidence, source, reasoning and review status."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.case import CustomsCase
from app.models.document import Document
from app.models.extraction import CaseField
from app.models.goods import GoodsItem, HsCandidate
from app.models.identity import Customer, Supplier
from app.models.issue import Issue
from app.services.mapping import FIELD_DEFS

SECTIONS = [("general", "Thông tin chung"), ("transport", "Vận đơn & vận tải"), ("invoice", "Invoice"), ("valuation", "Trị giá"),
            ("origin", "Xuất xứ / C/O")]
SCHEMA_VERSION = "internal-draft-v1"
DEMO_NOTICE = "DEMO DATA — NON-AUTHORITATIVE — NOT FOR CUSTOMS FILING"


def _field(cf: CaseField | None, fd) -> dict:
    if cf is None:
        return {"key": fd.key, "label": fd.label, "section": fd.section, "value": None, "confidence": None, "is_critical": fd.critical,
                "review_status": "MISSING" if fd.critical else "EMPTY", "origin": None, "source": None, "reasoning": None, "rule_ref": None,
                "alternatives": []}
    return {"key": cf.key, "label": cf.label, "section": cf.section, "value": cf.value, "confidence": cf.confidence, "is_critical": cf.is_critical,
            "review_status": cf.review_status, "origin": cf.origin, "method": cf.method,
            "source": {"document_id": str(cf.source_document_id) if cf.source_document_id else None, "source_ref": cf.source_ref,
                       "extracted_field_id": str(cf.source_extracted_field_id) if cf.source_extracted_field_id else None},
            "reasoning": cf.reasoning, "rule_ref": cf.rule_ref, "alternatives": cf.alternatives or [],
            "approved_by": str(cf.approved_by) if cf.approved_by else None}


def build(db: Session, case: CustomsCase) -> dict:
    fields = {f.key: f for f in db.execute(select(CaseField).where(CaseField.case_id == case.id)).scalars()}
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars().all()
    assess = db.execute(select(Assessment).where(Assessment.case_id == case.id)).scalars().all()
    by_item = {}
    for a in assess:
        by_item.setdefault(a.item_id, {})[a.kind] = a
    issues = db.execute(select(Issue).where(Issue.case_id == case.id, Issue.status == "OPEN")).scalars().all()
    docs = db.execute(select(Document).where(Document.case_id == case.id, Document.is_current.is_(True))).scalars().all()
    customer = db.get(Customer, case.customer_id)
    supplier = db.get(Supplier, case.supplier_id) if case.supplier_id else None

    sections = []
    for sid, title in SECTIONS:
        sections.append({"id": sid, "title": title, "fields": [_field(fields.get(fd.key), fd) for fd in FIELD_DEFS if fd.section == sid]})
    sections[0]["fields"] = [
        {"key": "case.declaration_type", "label": "Loại hình", "section": "general", "value": case.declaration_type, "confidence": 1.0,
         "is_critical": True, "review_status": "APPROVED", "origin": "CASE", "source": {"source_ref": "case"}, "reasoning": "Khai báo khi tạo hồ sơ",
         "rule_ref": None, "alternatives": []},
        {"key": "case.customs_office", "label": "Chi cục HQ", "section": "general", "value": case.customs_office, "confidence": 1.0,
         "is_critical": False, "review_status": "APPROVED" if case.customs_office else "EMPTY", "origin": "CASE", "source": {"source_ref": "case"},
         "reasoning": None, "rule_ref": None, "alternatives": []},
        {"key": "case.customer", "label": "Khách hàng (hồ sơ)", "section": "general", "value": customer.name if customer else None, "confidence": 1.0,
         "is_critical": False, "review_status": "APPROVED", "origin": "CASE", "source": {"source_ref": "master-data"}, "reasoning": None,
         "rule_ref": None, "alternatives": []},
        {"key": "case.supplier", "label": "Nhà cung cấp (hồ sơ)", "section": "general", "value": supplier.name if supplier else None, "confidence": 1.0,
         "is_critical": False, "review_status": "APPROVED" if supplier else "EMPTY", "origin": "CASE", "source": {"source_ref": "master-data"},
         "reasoning": None, "rule_ref": None, "alternatives": []},
    ] + sections[0]["fields"]
    val = next((a for a in assess if a.kind == "VALUATION"), None)
    if val:
        sections[3]["fields"].append({"key": "valuation.customs_value", "label": "Trị giá tính thuế (tính toán)", "section": "valuation",
                                      "value": val.result.get("customs_value"), "confidence": 1.0 if val.status == "COMPUTED" else 0.0,
                                      "is_critical": True, "review_status": "COMPUTED" if val.status == "COMPUTED" else "BLOCKED", "origin": "RULE",
                                      "source": {"source_ref": "assessment:VALUATION"}, "reasoning": " ".join(val.reasoning), "rule_ref": "VAL-ARITH-1",
                                      "alternatives": []})

    item_rows = []
    top_by_item: dict = {}
    if items:  # one query for the top candidate of every item (G18C-2)
        for c in db.execute(select(HsCandidate).where(HsCandidate.item_id.in_([it.id for it in items]), HsCandidate.status != "SUPERSEDED")
                            .order_by(HsCandidate.item_id, HsCandidate.rank)).scalars():
            top_by_item.setdefault(c.item_id, c)
    for it in items:
        a = by_item.get(it.id, {})
        top = top_by_item.get(it.id)
        tax, co, pol = a.get("TAX"), a.get("CO"), a.get("POLICY")
        item_rows.append({
            "item_id": str(it.id), "line_no": it.line_no, "description": it.description, "description_vn": it.description_vn,
            "description_vn_status": it.description_vn_status, "model": it.model, "quantity": it.quantity, "unit": it.unit,
            "unit_price": it.unit_price, "amount": it.amount, "packages": it.packages, "attributes": it.attributes,
            "source": {"document_id": str(it.source_document_id) if it.source_document_id else None, "source_ref": it.source_ref},
            "hs": {"code": it.hs_code, "status": it.hs_status, "confidence": it.hs_confidence,
                   "candidate": {"heading": top.heading, "title": top.title, "confidence": top.confidence, "reasoning": top.reasoning,
                                 "missing_attributes": top.missing_attributes, "dataset_version": top.dataset_version} if top else None},
            "origin": {"criterion": it.origin_criterion, "co_line_matched": it.co_line_matched, "status": co.status if co else None,
                       "reviewer_decision": co.reviewer_decision if co else None, "preferential_duty_pct": co.result.get("preferential_duty_pct") if co else None},
            "tax": {"status": tax.status, "inputs": tax.inputs, "result": tax.result, "dataset_version": tax.dataset_version,
                    "is_demo": tax.dataset_is_demo} if tax else None,
            "policy": {"status": pol.status, "requirements": pol.result.get("requirements", []), "dataset_version": pol.dataset_version} if pol else None,
            "open_issues": [{"code": i.code, "severity": i.severity, "title": i.title} for i in issues if i.target_ref == f"item:{it.line_no}"],
        })

    validation = validate(case, fields, items, issues, docs, val)
    demo_versions = sorted({a.dataset_version for a in assess if a.dataset_is_demo and a.dataset_version}
                           | {r["hs"]["candidate"]["dataset_version"] for r in item_rows if r["hs"]["candidate"] and r["hs"]["candidate"]["dataset_version"].startswith("demo-")})
    all_fields = [f for s in sections for f in s["fields"]]
    scored = [f for f in all_fields if f["is_critical"] or f["value"]]
    good = sum(1 for f in scored if f["review_status"] in ("APPROVED", "AUTO_ACCEPTABLE", "COMPUTED"))
    item_good = sum(1 for it in items if it.hs_status == "APPROVED")
    denom = len(scored) + len(items)
    readiness = round(100 * (good + item_good) / denom) if denom else 0
    return {
        "case": {"id": str(case.id), "case_no": case.case_no, "status": case.status, "direction": case.direction,
                 "declaration_type": case.declaration_type, "customs_office": case.customs_office, "priority": case.priority},
        "readiness": readiness,
        "summary": {"fields_total": len(scored), "fields_ok": good, "items_total": len(items), "items_hs_approved": item_good,
                    "open_critical": sum(1 for i in issues if i.severity == "CRITICAL"), "open_warning": sum(1 for i in issues if i.severity == "WARNING"),
                    "documents": [{"id": str(d.id), "doc_type": d.doc_type, "status": d.status, "version": d.version, "parse_confidence": d.parse_confidence} for d in docs]},
        "sections": sections,
        "items": item_rows,
        "validation": validation,
        "release_eligible": all(v["ok"] for v in validation if v["severity"] == "CRITICAL"),
        "demo_datasets": demo_versions,
        "demo_notice": DEMO_NOTICE if demo_versions else None,
        "disclaimer": "Internal draft generated from reviewed case data. Not a customs submission. "
                      + (f"Rule-derived values come from {DEMO_NOTICE} ({', '.join(demo_versions)})." if demo_versions else ""),
    }


def validate(case, fields, items, issues, docs, val) -> list[dict]:
    checks = []

    def add(code, ok, msg, severity="CRITICAL"):
        checks.append({"code": code, "ok": bool(ok), "severity": severity, "message": msg})

    doc_types = {d.doc_type for d in docs if d.status == "PARSED"}
    add("DOCS_MINIMUM", {"INVOICE", "PACKING_LIST"} <= doc_types, "Invoice và Packing List đã parse")
    add("ITEMS_PRESENT", len(items) >= 1, "Có ít nhất 1 dòng hàng")
    add("NO_OPEN_CRITICAL", not any(i.severity == "CRITICAL" for i in issues), "Không còn issue CRITICAL mở")
    add("NO_OPEN_ISSUES", not issues, "Không còn issue mở (warning phải được resolve/waive — D-009)")
    missing = [fd.label for fd in FIELD_DEFS if fd.critical and fd.key in ("invoice.number", "party.exporter", "party.importer", "valuation.incoterm",
                                                                             "valuation.currency", "invoice.total_amount", "shipment.total_packages")
               and not (fields.get(fd.key) and fields[fd.key].value)]
    add("CRITICAL_FIELDS_PRESENT", not missing, "Trường critical bắt buộc có giá trị" + (f" — thiếu: {missing}" if missing else ""))
    unapproved = [f.label for f in fields.values() if f.is_critical and f.value and f.review_status != "APPROVED"]
    add("CRITICAL_FIELDS_APPROVED", not unapproved, "Mọi trường critical có giá trị đều đã được reviewer duyệt" + (f" — chờ: {unapproved}" if unapproved else ""))
    add("ITEMS_HS_APPROVED", all(it.hs_status == "APPROVED" and it.hs_code for it in items) and bool(items), "Mọi dòng hàng có HS 8 số đã duyệt")
    add("VALUATION_COMPUTED", val is not None and val.status == "COMPUTED", "Trị giá tính thuế tính được từ các khoản đã duyệt")
    add("DESCRIPTIONS_VN", all(it.description_vn for it in items), "Mọi dòng hàng có mô tả khai báo tiếng Việt", severity="WARNING")
    return checks
