"""Historical learning. Only APPROVED reviewer decisions enter memory; CONSULTATION/DISPUTE outcomes are reference-only."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.extraction import CaseField
from app.models.goods import ClassificationDecision, GoodsItem
from app.models.identity import User
from app.models.memory import ProductMemory
from app.services import audit
from app.services.normalize import norm_text

BOOST = 0.05
NON_REUSABLE_OUTCOMES = {"CONSULTATION", "DISPUTE"}


def record_approved(db: Session, case: CustomsCase, item: GoodsItem, decision: ClassificationDecision, user: User) -> ProductMemory | None:
    if decision.decision != "APPROVE" or not decision.hs_code:
        return None  # rejected / non-final → never memory
    if db.execute(select(ProductMemory).where(ProductMemory.decision_id == decision.id)).scalar():
        return None
    currency = db.execute(select(CaseField.value).where(CaseField.case_id == case.id, CaseField.key == "valuation.currency")).scalar()
    co_form = db.execute(select(CaseField.value).where(CaseField.case_id == case.id, CaseField.key == "co.form")).scalar()
    mem = ProductMemory(tenant_id=case.tenant_id, fingerprint=item.fingerprint or "", customer_id=case.customer_id, supplier_id=case.supplier_id,
                        case_id=case.id, case_no=case.case_no, item_id=item.id, decision_id=decision.id, model=item.model, model_norm=norm_text(item.model),
                        description=item.description, description_vn=item.description_vn, hs_code=decision.hs_code, heading=decision.hs_code[:4],
                        unit_price=item.unit_price, currency=currency, co_form=co_form, approved_by=user.id, approved_by_role=user.role,
                        evidence_hash=hashlib.sha256(json.dumps(decision.snapshot, sort_keys=True, default=str).encode()).hexdigest(),
                        outcome="UNKNOWN", reusable=True, approved_at=decision.decided_at, updated_at=utcnow())
    db.add(mem)
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.system(), action="memory.recorded", entity_type="product_memory", entity_id=mem.id,
                 case_id=case.id, after={"hs_code": mem.hs_code, "model": mem.model, "fingerprint": mem.fingerprint, "decision_id": str(decision.id)},
                 reason="reviewer-approved classification entered enterprise memory")
    return mem


def history_for_item(db: Session, case: CustomsCase, item: GoodsItem, limit: int = 5) -> list[dict]:
    """Approved-memory references for this item, tenant-scoped, excluding the item itself. EXACT (fingerprint) > MODEL."""
    rows = db.execute(select(ProductMemory).where(ProductMemory.tenant_id == case.tenant_id, ProductMemory.item_id != item.id)
                      .order_by(ProductMemory.approved_at.desc())).scalars().all()
    out = []
    for m in rows:
        if item.fingerprint and m.fingerprint == item.fingerprint:
            match = "EXACT"
        elif item.model and m.model_norm == norm_text(item.model):
            match = "MODEL"
        else:
            continue
        out.append({"memory_id": str(m.id), "match": match, "hs_code": m.hs_code, "heading": m.heading, "case_no": m.case_no, "outcome": m.outcome,
                    "reusable": m.reusable, "same_customer": m.customer_id == case.customer_id, "same_supplier": m.supplier_id == case.supplier_id,
                    "unit_price": m.unit_price, "currency": m.currency, "approved_at": m.approved_at.isoformat()})
        if len(out) >= limit:
            break
    return out


def boost_candidates(db: Session, case: CustomsCase, item: GoodsItem, scored: list[dict]) -> list[dict]:
    """HS engine hook: approved, reusable history nudges the matching heading; non-reusable history is reference only."""
    refs = history_for_item(db, case, item)
    for c in scored:
        for h in refs:
            if h["heading"] != c["heading"]:
                continue
            if h["reusable"] and h["match"] in ("EXACT", "MODEL"):
                c["confidence"] = round(min(0.99, c["confidence"] + BOOST), 2)
                c["reasoning"].append(f"Lịch sử đã duyệt ({h['case_no']}, {h['match']}, outcome {h['outcome']}): HS {h['hs_code']} (+{BOOST:.2f}).")
            else:
                c["reasoning"].append(f"Lịch sử {h['case_no']} từng {h['outcome']} với HS {h['hs_code']} — chỉ tham khảo, KHÔNG tự áp dụng.")
            break
    scored.sort(key=lambda c: (-c["confidence"], c["heading"]))
    return refs


def set_outcome(db: Session, mem: ProductMemory, user: User, outcome: str, reason: str) -> ProductMemory:
    before = {"outcome": mem.outcome, "reusable": mem.reusable}
    mem.outcome = outcome
    mem.reusable = outcome not in NON_REUSABLE_OUTCOMES
    mem.outcome_reason = reason
    mem.outcome_set_by = user.id
    mem.updated_at = utcnow()
    audit.record(db, tenant_id=mem.tenant_id, actor=audit.Actor.user(user), action="memory.outcome_set", entity_type="product_memory", entity_id=mem.id,
                 case_id=mem.case_id, before=before, after={"outcome": mem.outcome, "reusable": mem.reusable}, reason=reason)
    return mem
