import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.api.goods import _item
from app.core.errors import not_found
from app.core.rbac import Perm
from app.db import get_db
from app.models.identity import User
from app.models.memory import ProductMemory
from app.services import memory

router = APIRouter(tags=["memory"])


class MemoryOut(BaseModel):
    id: uuid.UUID
    fingerprint: str
    customer_id: uuid.UUID
    supplier_id: uuid.UUID | None
    case_id: uuid.UUID
    case_no: str
    item_id: uuid.UUID
    decision_id: uuid.UUID
    model: str | None
    description: str
    description_vn: str | None
    hs_code: str
    heading: str
    unit_price: str | None
    currency: str | None
    co_form: str | None
    approved_by: uuid.UUID
    approved_by_role: str
    evidence_hash: str
    outcome: str
    reusable: bool
    outcome_reason: str | None
    approved_at: object
    model_config = {"from_attributes": True}


class OutcomeIn(BaseModel):
    outcome: Literal["CLEARED", "CONSULTATION", "DISPUTE", "AMENDED", "UNKNOWN"]
    reason: str = Field(min_length=3, max_length=2000)


@router.get("/memory", response_model=list[MemoryOut])
def list_memory(model: str | None = None, customer_id: uuid.UUID | None = None, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    stmt = select(ProductMemory).where(ProductMemory.tenant_id == user.tenant_id)
    if model:
        from app.services.normalize import norm_text

        stmt = stmt.where(ProductMemory.model_norm == norm_text(model))
    if customer_id:
        stmt = stmt.where(ProductMemory.customer_id == customer_id)
    return db.execute(stmt.order_by(ProductMemory.approved_at.desc())).scalars().all()


@router.post("/memory/{memory_id}/outcome", response_model=MemoryOut)
def set_outcome(memory_id: uuid.UUID, body: OutcomeIn, user: User = Depends(require(Perm.MEMORY_OUTCOME)), db: Session = Depends(get_db)):
    mem = db.execute(select(ProductMemory).where(ProductMemory.id == memory_id, ProductMemory.tenant_id == user.tenant_id)).scalar()
    if not mem:
        raise not_found("memory")
    memory.set_outcome(db, mem, user, body.outcome, body.reason)
    db.commit()
    return mem


@router.get("/cases/{case_id}/items/{item_id}/history")
def item_history(case_id: uuid.UUID, item_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id)
    it = _item(db, user, case_id, item_id)
    refs = memory.history_for_item(db, case, it, limit=10)
    comparison = []
    for h in refs:
        row = {"case_no": h["case_no"], "match": h["match"], "hs_previous": h["hs_code"], "hs_current": it.hs_code,
               "hs_stable": (it.hs_code or "")[:4] == h["heading"] if it.hs_code else None, "outcome": h["outcome"], "reusable": h["reusable"]}
        try:
            prev, cur = float(h["unit_price"]), float(it.unit_price)
            row["unit_price_previous"], row["unit_price_current"] = prev, cur
            row["unit_price_delta_pct"] = round((cur - prev) / prev * 100, 2) if prev else None
            row["price_flag"] = "RISK" if prev and abs(row["unit_price_delta_pct"]) > 15 else "NORMAL"
        except (TypeError, ValueError):
            pass
        comparison.append(row)
    return {"item_id": str(it.id), "fingerprint": it.fingerprint, "references": refs, "comparison": comparison}
