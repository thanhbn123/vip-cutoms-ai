import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ensure, load_case, require
from app.core.errors import DomainError, not_found
from app.core.rbac import Perm
from app.db import get_db
from app.models.base import utcnow
from app.models.goods import ClassificationDecision, GoodsItem, HsCandidate
from app.models.identity import User
from app.services import audit, evaluators
from app.services.release import recompute_case_status
from app.services.workflow import CaseStatus

router = APIRouter(tags=["goods"])
HS_CODE_RE = re.compile(r"^\d{8}$")


class CandidateOut(BaseModel):
    id: uuid.UUID
    rank: int
    heading: str
    title: str
    confidence: float
    reasoning: list
    matched_keywords: list
    missing_attributes: list
    evidence: list
    history_refs: list
    dataset_version: str
    method: str
    status: str
    model_config = {"from_attributes": True}


class ItemOut(BaseModel):
    id: uuid.UUID
    line_no: int
    description: str
    description_vn: str | None
    description_vn_status: str
    model: str | None
    quantity: str | None
    unit: str | None
    unit_price: str | None
    amount: str | None
    packages: str | None
    origin_criterion: str | None
    co_line_matched: bool | None
    attributes: dict
    attribute_sources: list
    source_document_id: uuid.UUID | None
    source_ref: str | None
    manual_fields: list
    fingerprint: str | None
    hs_code: str | None
    hs_status: str
    hs_confidence: float | None
    hs_decision_id: uuid.UUID | None
    candidates: list[CandidateOut] = []
    model_config = {"from_attributes": True}


class ItemPatch(BaseModel):
    description_vn: str | None = Field(default=None, max_length=2000)
    model: str | None = Field(default=None, max_length=120)
    attributes: dict[str, str] | None = None  # technical attributes entered by a human
    reason: str = Field(min_length=3, max_length=2000)


class DecisionIn(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    hs_code: str | None = Field(default=None, description="8-digit code, required for APPROVE")
    candidate_id: uuid.UUID | None = None
    reason: str = Field(min_length=5, max_length=2000)
    evidence: list[str] = []


class DecisionOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    candidate_id: uuid.UUID | None
    decision: str
    hs_code: str | None
    is_override: bool
    reason: str
    evidence: list
    decided_by: uuid.UUID
    decided_by_role: str
    decided_at: object
    model_config = {"from_attributes": True}


def _item(db: Session, user: User, case_id: uuid.UUID, item_id: uuid.UUID) -> GoodsItem:
    it = db.execute(select(GoodsItem).where(GoodsItem.id == item_id, GoodsItem.case_id == case_id,
                                            GoodsItem.tenant_id == user.tenant_id)).scalar()
    if not it:
        raise not_found("item")
    return it


def _with_candidates(db: Session, items: list[GoodsItem]) -> list[ItemOut]:
    out = []
    for it in items:
        cands = db.execute(select(HsCandidate).where(HsCandidate.item_id == it.id, HsCandidate.status != "SUPERSEDED")
                           .order_by(HsCandidate.rank)).scalars().all()
        o = ItemOut.model_validate(it)
        o.candidates = [CandidateOut.model_validate(c) for c in cands]
        out.append(o)
    return out


@router.get("/cases/{case_id}/items", response_model=list[ItemOut])
def list_items(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    items = db.execute(select(GoodsItem).where(GoodsItem.case_id == case_id).order_by(GoodsItem.line_no)).scalars().all()
    return _with_candidates(db, items)


@router.patch("/cases/{case_id}/items/{item_id}", response_model=ItemOut)
def patch_item(case_id: uuid.UUID, item_id: uuid.UUID, body: ItemPatch, user: User = Depends(require(Perm.FIELD_EDIT)),
               db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    if case.status == CaseStatus.DRAFT_EXPORTED.value:
        raise DomainError("CASE_EXPORTED", "case already exported; re-run pipeline to reopen")
    it = _item(db, user, case_id, item_id)
    before = {"description_vn": it.description_vn, "model": it.model, "attributes": it.attributes}
    manual = set(it.manual_fields or [])
    if body.description_vn is not None:
        it.description_vn = body.description_vn
        it.description_vn_status = "MANUAL"
        manual.add("description_vn")
    if body.model is not None:
        it.model = body.model
        manual.add("model")
    if body.attributes:
        attrs = dict(it.attributes or {})
        for k, v in body.attributes.items():
            attrs[k] = {"value": v, "source": "manual", "source_ref": f"user:{user.email}"}
        it.attributes = attrs
    it.manual_fields = sorted(manual)
    it.row_version += 1
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="item.edited", entity_type="goods_item",
                 entity_id=it.id, case_id=case.id, before=before,
                 after={"description_vn": it.description_vn, "model": it.model, "attributes": it.attributes}, reason=body.reason)
    evaluators.run_all(db, case, audit.Actor.user(user))  # re-score with the new attributes
    recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    return _with_candidates(db, [it])[0]


@router.post("/cases/{case_id}/items/{item_id}/hs-decision", response_model=DecisionOut, status_code=201)
def hs_decision(case_id: uuid.UUID, item_id: uuid.UUID, body: DecisionIn, user: User = Depends(require(Perm.HS_DECIDE)),
                db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    it = _item(db, user, case_id, item_id)
    cands = db.execute(select(HsCandidate).where(HsCandidate.item_id == it.id, HsCandidate.status.in_(("PROPOSED", "REJECTED")))).scalars().all()
    cand = None
    if body.candidate_id:
        cand = next((c for c in cands if c.id == body.candidate_id), None)
        if cand is None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CANDIDATE", "message": "candidate not on this item"})
    is_override = False
    if body.decision == "APPROVE":
        if not body.hs_code or not HS_CODE_RE.match(body.hs_code):
            raise HTTPException(status_code=422, detail={"code": "HS_CODE_REQUIRED", "message": "APPROVE requires an 8-digit hs_code"})
        headings = {c.heading for c in cands}
        if body.hs_code[:4] not in headings:
            ensure(user, Perm.HS_OVERRIDE)  # outside AI candidates → Senior Reviewer only
            is_override = True
            if not body.evidence:
                raise HTTPException(status_code=422, detail={"code": "EVIDENCE_REQUIRED", "message": "override requires evidence refs"})
        if cand is None:
            cand = next((c for c in cands if c.heading == body.hs_code[:4]), None)
    dec = ClassificationDecision(tenant_id=case.tenant_id, item_id=it.id, case_id=case.id, candidate_id=cand.id if cand else None,
                                 decision=body.decision, hs_code=body.hs_code if body.decision == "APPROVE" else None,
                                 is_override=is_override, reason=body.reason, evidence=body.evidence, decided_by=user.id,
                                 decided_by_role=user.role, decided_at=utcnow(),
                                 snapshot={"description": it.description, "description_vn": it.description_vn, "model": it.model,
                                           "attributes": it.attributes, "candidate_confidence": cand.confidence if cand else None})
    db.add(dec)
    db.flush()
    before = {"hs_code": it.hs_code, "hs_status": it.hs_status}
    if body.decision == "APPROVE":
        it.hs_code = body.hs_code
        it.hs_status = "APPROVED"
        it.hs_decision_id = dec.id
        for c in cands:
            c.status = "APPROVED" if cand and c.id == cand.id else "REJECTED"
    else:
        if cand:
            cand.status = "REJECTED"
        it.hs_status = "BLOCKED" if (it.hs_confidence or 0) < 0.70 else "NEEDS_REVIEW"
    it.row_version += 1
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action=f"hs.{body.decision.lower()}", entity_type="goods_item",
                 entity_id=it.id, case_id=case.id, before=before,
                 after={"hs_code": it.hs_code, "hs_status": it.hs_status, "decision_id": str(dec.id), "override": is_override},
                 reason=body.reason, evidence=body.evidence)
    evaluators.run_all(db, case, audit.Actor.user(user))  # HS issues clear/re-raise; tax, C/O, policy follow the decision
    for hook in DECISION_HOOKS:  # populated by evaluators.ensure_registered()
        hook(db, case, it, dec, user)
    recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    return dec


DECISION_HOOKS: list = []  # G10 learning memory


@router.get("/cases/{case_id}/items/{item_id}/decisions", response_model=list[DecisionOut])
def list_decisions(case_id: uuid.UUID, item_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    _item(db, user, case_id, item_id)
    return db.execute(select(ClassificationDecision).where(ClassificationDecision.item_id == item_id)
                      .order_by(ClassificationDecision.decided_at)).scalars().all()
