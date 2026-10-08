"""C/O / FTA assessment. Produces an *assessment state*, never an automatic legal approval."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.models.extraction import CaseField
from app.models.goods import GoodsItem, HsCandidate
from app.services import assessments, audit
from app.services.issues import IssueSpec, sync
from app.services.knowledge import NoActiveDataset, dataset_payload, require_dataset
from app.services.mapping import current_extractions
from app.services.normalize import norm_name, norm_text


def evaluate(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    specs: list[IssueSpec] = []
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars().all()
    co = {f.key: (f, d) for d, f in current_extractions(db, case) if d.doc_type == "CO" and f.key.startswith("co.")}
    fields = {f.key: f for f in db.execute(select(CaseField).where(CaseField.case_id == case.id)).scalars()}
    if not co:
        for it in items:
            assessments.upsert(db, case, "CO", it.id, status="NOT_COVERED", ds=None, inputs={}, result={},
                               reasoning=["Không có C/O trong hồ sơ → áp dụng thuế suất thông thường (MFN)."], keep_decision=False)
        sync(db, case, specs, "origin")
        return
    try:
        ds = require_dataset(db, "FTA")
    except NoActiveDataset:
        specs.append(IssueSpec("fta_dataset", "FTA_KNOWLEDGE_UNAVAILABLE", "CRITICAL", "CO", "Không có bộ quy tắc FTA hiệu lực",
                               "Không đánh giá C/O khi thiếu dataset (fail-closed).", auto_resolvable=True))
        sync(db, case, specs, "origin")
        return
    forms = dataset_payload(ds).get("forms", {})
    form = (co["co.form"][0].value.strip().upper() if "co.form" in co else "")
    rule = forms.get(form)
    header_checks: dict[str, bool | None] = {}
    reasons: list[str] = []

    def val(k):
        return fields[k].value if fields.get(k) and fields[k].value else None

    if rule is None:
        specs.append(IssueSpec("co_form", "CO_FORM_UNKNOWN", "WARNING", "CO", f"C/O form '{form or '?'}' không có trong bộ quy tắc FTA",
                               target_ref="co.form", auto_resolvable=True))
    else:
        header_checks["exporter_matches_invoice"] = norm_name(co["co.exporter"][0].value) == norm_name(val("party.exporter")) if "co.exporter" in co else None
        header_checks["importer_matches_invoice"] = norm_name(co["co.importer"][0].value) == norm_name(val("party.importer")) if "co.importer" in co else None
        header_checks["invoice_ref_matches"] = norm_text(co["co.invoice_ref"][0].value) == norm_text(val("invoice.number")) if "co.invoice_ref" in co else None
        header_checks["origin_country_allowed"] = (co["co.origin_country"][0].value.strip().upper() in rule["origin_countries"]) if "co.origin_country" in co else None
        for k, ok in header_checks.items():
            if ok is False:
                specs.append(IssueSpec(f"co_header:{k}", "CO_HEADER_MISMATCH", "WARNING", "CO", f"C/O: kiểm tra '{k}' không đạt",
                                       target_ref="co.number", auto_resolvable=True,
                                       evidence=[{"document_id": str(co[next(iter(co))][1].id)}]))
            elif ok is None:
                reasons.append(f"Không kiểm tra được '{k}' (thiếu dữ liệu trên C/O).")
    header_ok = rule is not None and all(v is True for v in header_checks.values())

    for it in items:
        prev = assessments.get(db, case.id, "CO", it.id)
        inputs = {"form": form, "origin_criterion": it.origin_criterion, "co_line_matched": it.co_line_matched, "header_checks": header_checks}
        heading = it.hs_code[:4] if it.hs_status == "APPROVED" and it.hs_code else None
        if heading is None:
            top = db.execute(select(HsCandidate).where(HsCandidate.item_id == it.id, HsCandidate.status == "PROPOSED")
                             .order_by(HsCandidate.rank)).scalars().first()
            heading = top.heading if top else None
        pref = (rule or {}).get("preferential_duty_pct", {}).get(heading) if heading else None
        result = {"preferential_duty_pct": pref, "heading_basis": "approved" if it.hs_status == "APPROVED" else "candidate (provisional)",
                  "agreement": (rule or {}).get("agreement")}
        item_reasons = list(reasons)
        if it.co_line_matched is None:
            status = "NOT_COVERED"
            item_reasons.append("Mặt hàng không có trên C/O.")
        elif rule is None or not header_ok:
            status = "NEEDS_REVIEW"
            item_reasons.append("Kiểm tra tiêu đề C/O chưa đạt hoặc form không xác định.")
        elif it.co_line_matched is False:
            status = "NEEDS_REVIEW"
            item_reasons.append("Dòng hàng trên C/O không khớp Invoice (mô tả/model).")
        elif it.origin_criterion and it.origin_criterion.upper() not in rule["allowed_criteria"]:
            status = "NEEDS_REVIEW"
            item_reasons.append(f"Tiêu chí xuất xứ '{it.origin_criterion}' không thuộc danh mục cho phép {rule['allowed_criteria']}.")
            specs.append(IssueSpec(f"co_criterion:item:{it.line_no}", "CO_CRITERION_INVALID", "WARNING", "CO",
                                   f"Item {it.line_no}: tiêu chí xuất xứ '{it.origin_criterion}' không hợp lệ", target_ref=f"item:{it.line_no}",
                                   auto_resolvable=True))
        elif pref is None:
            status = "NEEDS_REVIEW"
            item_reasons.append(f"Không có thuế suất ưu đãi demo cho nhóm {heading} trong {rule['agreement']}.")
        else:
            status = "ELIGIBLE_PENDING_REVIEW"
            item_reasons.append(f"Tất cả kiểm tra tự động đạt; ưu đãi {pref}% ({rule['agreement']}) CHỈ áp dụng sau khi reviewer quyết định.")
            if not (prev and prev.reviewer_decision):
                specs.append(IssueSpec(f"co_decision:item:{it.line_no}", "CO_DECISION_PENDING", "WARNING", "CO",
                                       f"Item {it.line_no}: chờ reviewer quyết định áp dụng C/O form {form}", target_ref=f"item:{it.line_no}",
                                       auto_resolvable=True))
        keep = status == "ELIGIBLE_PENDING_REVIEW" or (prev is not None and prev.reviewer_decision and prev.reviewer_decision.get("decision") == "DO_NOT_APPLY")
        if prev and prev.reviewer_decision and prev.reviewer_decision.get("decision") == "APPLY" and not keep:
            specs.append(IssueSpec(f"co_invalidated:item:{it.line_no}", "CO_DECISION_INVALIDATED", "WARNING", "CO",
                                   f"Item {it.line_no}: quyết định áp dụng C/O bị hủy do dữ liệu thay đổi", target_ref=f"item:{it.line_no}",
                                   auto_resolvable=False))
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.system(), action="co.decision_invalidated", entity_type="goods_item",
                         entity_id=it.id, case_id=case.id, before=prev.reviewer_decision, after=None, reason="assessment no longer eligible")
        assessments.upsert(db, case, "CO", it.id, status=status, ds=ds, inputs=inputs, result=result, reasoning=item_reasons, keep_decision=keep)
    sync(db, case, specs, "origin")
