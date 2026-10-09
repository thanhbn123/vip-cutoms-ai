"""Specialized-management policy scaffold over the versioned POLICY dataset (demo). Fail closed on unknown HS."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.models.document import Document
from app.models.goods import GoodsItem
from app.services import assessments, audit
from app.services.issues import IssueSpec, sync
from app.services.knowledge import ConflictingDatasets, NoActiveDataset, dataset_payload, require_dataset

BLOCK_BELOW = 0.70


def evaluate(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    specs: list[IssueSpec] = []
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars().all()
    doc_types = {d.doc_type for d in db.execute(select(Document).where(Document.case_id == case.id, Document.is_current.is_(True))).scalars()}
    try:
        ds = require_dataset(db, "POLICY")
    except ConflictingDatasets as exc:
        specs.append(IssueSpec("policy_dataset_conflict", "POLICY_KNOWLEDGE_CONFLICT", "CRITICAL", "POLICY",
                               "Xung đột bộ quy tắc chính sách hiệu lực", f"Reviewer phải giải quyết. {exc}", auto_resolvable=True))
        sync(db, case, specs, "policy")
        return
    except NoActiveDataset:
        specs.append(IssueSpec("policy_dataset", "POLICY_KNOWLEDGE_UNAVAILABLE", "CRITICAL", "POLICY", "Không có bộ quy tắc chính sách hiệu lực",
                               auto_resolvable=True))
        sync(db, case, specs, "policy")
        return
    reqs_by_heading = dataset_payload(ds).get("requirements", {})
    for it in items:
        ref = f"item:{it.line_no}"
        if it.hs_status != "APPROVED" or not it.hs_code:
            if (it.hs_confidence or 0) < BLOCK_BELOW:
                specs.append(IssueSpec(f"policy_undetermined:{ref}", "POLICY_UNDETERMINED", "CRITICAL", "POLICY",
                                       f"Item {it.line_no} policy: chưa xác định", "Phụ thuộc phân loại HS cuối cùng và công dụng (D-015).",
                                       target_ref=ref, auto_resolvable=True))
                status = "UNDETERMINED"
            else:
                specs.append(IssueSpec(f"policy_pending:{ref}", "POLICY_PENDING_HS", "WARNING", "POLICY",
                                       f"Item {it.line_no} policy: chờ HS được duyệt", target_ref=ref, auto_resolvable=True))
                status = "PENDING_HS"
            assessments.upsert(db, case, "POLICY", it.id, status=status, ds=ds, inputs={"hs_code": None}, result={},
                               reasoning=["Chính sách chỉ đánh giá trên HS đã duyệt."])
            continue
        heading = it.hs_code[:4]
        reqs = reqs_by_heading.get(heading, [])
        results = []
        for r in reqs:
            evidence_present = (not r.get("evidence_doc_types")) or any(t in doc_types for t in r["evidence_doc_types"])
            if "CATALOGUE" in r.get("evidence_doc_types", []):
                evidence_present = any(s.get("doc_type") == "CATALOGUE" for s in (it.attribute_sources or []))
            results.append({"code": r["code"], "title": r["title"], "evidence_present": evidence_present,
                            "needs_reviewer_confirmation": r.get("needs_reviewer_confirmation", True), "notes": r.get("notes")})
            specs.append(IssueSpec(f"policy_req:{ref}:{r['code']}", "POLICY_REQUIREMENT", "WARNING", "POLICY",
                                   f"Item {it.line_no}: {r['title']}",
                                   ("Có chứng từ liên quan; " if evidence_present else "Chưa có chứng từ chứng minh; ") + "reviewer phải xác nhận phạm vi áp dụng.",
                                   target_ref=ref, auto_resolvable=False,
                                   evidence=[{"requirement": r["code"], "evidence_doc_types": r.get("evidence_doc_types", []), "present": evidence_present}]))
        assessments.upsert(db, case, "POLICY", it.id, status="REQUIREMENTS_PENDING_REVIEW" if reqs else "NO_REQUIREMENT", ds=ds,
                           inputs={"hs_code": it.hs_code, "heading": heading}, result={"requirements": results},
                           reasoning=[f"Tra cứu nhóm {heading} trong {ds.label}: {len(reqs)} yêu cầu."])
    sync(db, case, specs, "policy")
