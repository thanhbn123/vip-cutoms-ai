"""Deterministic HS candidate engine over the active HS_RULES dataset.

Confidence is a heuristic score, *not* authority: every item needs an APPROVED reviewer decision
before release (D-008). Thresholds: < 0.70 → CRITICAL (BLOCKED); 0.70–0.90 → WARNING (NEEDS_REVIEW).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.goods import GoodsItem, HsCandidate
from app.models.knowledge import HsRule
from app.services import audit
from app.services.goods import build_items
from app.services.issues import IssueSpec, sync
from app.services.knowledge import NoActiveDataset, require_dataset

BLOCK_BELOW = 0.70
REVIEW_BELOW = 0.90
HISTORY_BOOSTERS: list = []  # G10 registers: fn(db, case, item) -> list[dict] (approved-memory references)


def score_item(item: GoodsItem, rules: list[HsRule]) -> list[dict]:
    text = f"{item.description} {item.description_vn or ''} {item.model or ''}".lower()
    attrs = item.attributes or {}
    out = []
    for r in rules:
        matched = [k for k in r.keywords if k.lower() in text]
        if not matched:
            continue
        excluded = [k for k in (r.exclusions or []) if k.lower() in text]
        missing = [a for a in (r.required_attributes or []) if not attrs.get(a)]
        present = [a for a in (r.required_attributes or []) if attrs.get(a)]
        conf = r.base_confidence + 0.03 * (len(matched) - 1) + 0.05 * len(present) - 0.03 * len(missing) - 0.15 * len(excluded)
        conf = round(max(0.05, min(0.99, conf)), 2)
        reasoning = [f"Khớp từ khóa {matched} với nhóm {r.heading} ({r.title}) trong bộ quy tắc {{dataset}}."]
        if present:
            reasoning.append(f"Thuộc tính kỹ thuật đã có: {present} (+{0.05 * len(present):.2f}).")
        if missing:
            reasoning.append(f"Thiếu thuộc tính bắt buộc để chốt nhóm: {missing} (−{0.03 * len(missing):.2f}).")
        if excluded:
            reasoning.append(f"Có từ khóa loại trừ {excluded} (−{0.15 * len(excluded):.2f}).")
        if r.notes:
            reasoning.append(f"Ghi chú quy tắc: {r.notes}")
        out.append({"rule": r, "heading": r.heading, "title": r.title, "confidence": conf, "matched": matched, "missing": missing,
                    "reasoning": reasoning})
    out.sort(key=lambda c: (-c["confidence"], c["heading"]))
    return out


def evaluate(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    specs = build_items(db, case, actor)
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id).order_by(GoodsItem.line_no)).scalars().all()
    try:
        ds = require_dataset(db, "HS_RULES")
    except NoActiveDataset:
        specs.append(IssueSpec("hs_dataset", "HS_KNOWLEDGE_UNAVAILABLE", "CRITICAL", "HS", "Không có bộ quy tắc HS hiệu lực",
                               "Hệ thống không phân loại khi thiếu knowledge dataset (fail-closed).", auto_resolvable=True))
        sync(db, case, specs, "hs_engine")
        return
    rules = db.execute(select(HsRule).where(HsRule.dataset_id == ds.id)).scalars().all()
    run_id = uuid.uuid4()
    for item in items:
        ref = f"item:{item.line_no}"
        if item.hs_status == "APPROVED":
            continue  # reviewer decision stands; re-evaluation does not reopen it
        for old in db.execute(select(HsCandidate).where(HsCandidate.item_id == item.id, HsCandidate.status == "PROPOSED")).scalars():
            old.status = "SUPERSEDED"
        scored = score_item(item, rules)
        history = []
        for booster in HISTORY_BOOSTERS:
            history += booster(db, case, item, scored)
        evidence = [{"document_id": str(item.source_document_id), "source_ref": item.source_ref}] + [
            {"attribute": k, **v} for k, v in (item.attributes or {}).items()]
        for rank, c in enumerate(scored[:3], start=1):
            db.add(HsCandidate(tenant_id=case.tenant_id, item_id=item.id, case_id=case.id, run_id=run_id, rank=rank, heading=c["heading"],
                               title=c["title"], confidence=c["confidence"],
                               reasoning=[s.replace("{dataset}", f"{ds.kind} {ds.version}") for s in c["reasoning"]],
                               matched_keywords=c["matched"], missing_attributes=c["missing"], evidence=evidence, history_refs=history,
                               dataset_id=ds.id, dataset_version=ds.version, method="rules.keyword-attr.v1", status="PROPOSED",
                               created_at=utcnow()))
        top = scored[0] if scored else None
        item.hs_confidence = top["confidence"] if top else 0.0
        if top is None:
            item.hs_status = "BLOCKED"
            specs.append(IssueSpec(f"hs_none:{ref}", "HS_NO_CANDIDATE", "CRITICAL", "HS", f"Item {item.line_no}: không có ứng viên HS",
                                   "Không quy tắc nào khớp mô tả; cần reviewer phân loại thủ công.", target_ref=ref, auto_resolvable=True))
        elif top["confidence"] < BLOCK_BELOW:
            item.hs_status = "BLOCKED"
            specs.append(IssueSpec(f"hs_low:{ref}", "HS_LOW_CONFIDENCE", "CRITICAL", "HS",
                                   f"Item {item.line_no} HS: chưa đủ căn cứ ({top['heading']}, {top['confidence']:.0%})",
                                   "Thiếu: " + ", ".join(top["missing"]) if top["missing"] else "Độ tin cậy thấp.", target_ref=ref,
                                   auto_resolvable=True, evidence=evidence))
        else:
            item.hs_status = "NEEDS_REVIEW"
            specs.append(IssueSpec(f"hs_pending:{ref}", "HS_PENDING_APPROVAL", "WARNING", "HS",
                                   f"Item {item.line_no} HS: chờ reviewer duyệt ({top['heading']}, {top['confidence']:.0%})",
                                   ("Thiếu thuộc tính: " + ", ".join(top["missing"])) if top["missing"] else "Ứng viên đủ dữ liệu.",
                                   target_ref=ref, auto_resolvable=True, evidence=evidence))
        audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.ai(), action="hs.candidates_proposed", entity_type="goods_item",
                     entity_id=item.id, case_id=case.id,
                     after={"run_id": str(run_id), "top": top["heading"] if top else None, "confidence": item.hs_confidence,
                            "hs_status": item.hs_status, "dataset": f"{ds.kind}:{ds.version}", "is_demo": ds.is_demo})
    sync(db, case, specs, "hs_engine")
