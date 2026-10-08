import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.api.goods import _item
from app.core.errors import DomainError
from app.core.rbac import Perm
from app.db import get_db
from app.models.assessment import Assessment
from app.models.base import utcnow
from app.models.identity import User
from app.models.knowledge import HsRule, KnowledgeDataset
from app.services import assessments, audit, evaluators
from app.services.knowledge import dataset_payload
from app.services.release import recompute_case_status

router = APIRouter(tags=["knowledge"])


class DatasetOut(BaseModel):
    id: uuid.UUID
    kind: str
    version: str
    label: str
    source: str
    is_demo: bool
    effective_from: date
    effective_to: date | None
    is_active: bool
    rule_count: int = 0
    model_config = {"from_attributes": True}


class DatasetPatch(BaseModel):
    is_active: bool
    reason: str = Field(min_length=3, max_length=2000)


class AssessmentOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID | None
    kind: str
    status: str
    dataset_version: str | None
    dataset_is_demo: bool | None
    effective_date: date
    inputs: dict
    result: dict
    reasoning: list
    reviewer_decision: dict | None
    model_config = {"from_attributes": True}


class CoDecisionIn(BaseModel):
    decision: Literal["APPLY", "DO_NOT_APPLY"]
    reason: str = Field(min_length=5, max_length=2000)
    evidence: list[str] = []


@router.get("/knowledge/datasets", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    from app.services.knowledge import seed_demo

    seed_demo(db)  # idempotent demo seed so the Knowledge Hub is never empty in dev/test
    db.commit()
    counts = dict(db.execute(select(HsRule.dataset_id, func.count()).group_by(HsRule.dataset_id)).all())
    out = []
    for ds in db.execute(select(KnowledgeDataset).order_by(KnowledgeDataset.kind, KnowledgeDataset.effective_from.desc())).scalars():
        o = DatasetOut.model_validate(ds)
        payload = dataset_payload(ds) if ds.kind != "HS_RULES" else {}
        o.rule_count = counts.get(ds.id, 0) or sum(len(v) if isinstance(v, (list, dict)) else 1 for v in payload.values())
        out.append(o)
    return out


@router.get("/knowledge/datasets/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    ds = db.get(KnowledgeDataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "dataset not found"})
    body = DatasetOut.model_validate(ds).model_dump()
    if ds.kind == "HS_RULES":
        body["rules"] = [{"heading": r.heading, "title": r.title, "keywords": r.keywords, "exclusions": r.exclusions,
                          "required_attributes": r.required_attributes, "base_confidence": r.base_confidence, "notes": r.notes}
                         for r in db.execute(select(HsRule).where(HsRule.dataset_id == ds.id).order_by(HsRule.heading)).scalars()]
    else:
        body["payload"] = dataset_payload(ds)
    return body


@router.patch("/knowledge/datasets/{dataset_id}", response_model=DatasetOut)
def patch_dataset(dataset_id: uuid.UUID, body: DatasetPatch, admin: User = Depends(require(Perm.KNOWLEDGE_MANAGE)),
                  db: Session = Depends(get_db)):
    ds = db.get(KnowledgeDataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "dataset not found"})
    before = {"is_active": ds.is_active}
    ds.is_active = body.is_active
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action="knowledge.dataset_toggled", entity_type="knowledge_dataset",
                 entity_id=ds.id, before=before, after={"is_active": ds.is_active, "kind": ds.kind, "version": ds.version}, reason=body.reason)
    db.commit()
    return DatasetOut.model_validate(ds)


@router.get("/cases/{case_id}/assessments", response_model=list[AssessmentOut])
def list_assessments(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(Assessment).where(Assessment.case_id == case_id).order_by(Assessment.kind, Assessment.item_id)).scalars().all()


@router.post("/cases/{case_id}/items/{item_id}/co-decision", response_model=AssessmentOut)
def co_decision(case_id: uuid.UUID, item_id: uuid.UUID, body: CoDecisionIn, user: User = Depends(require(Perm.PROPOSAL_DECIDE)),
                db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    it = _item(db, user, case_id, item_id)
    a = assessments.get(db, case.id, "CO", it.id)
    if a is None:
        raise DomainError("NO_ASSESSMENT", "run the pipeline first")
    if body.decision == "APPLY" and a.status != "ELIGIBLE_PENDING_REVIEW":
        raise DomainError("CO_NOT_ELIGIBLE", f"cannot apply C/O while assessment status is {a.status}", details={"status": a.status})
    before = a.reviewer_decision
    a.reviewer_decision = {"decision": body.decision, "by": str(user.id), "role": user.role, "at": utcnow().isoformat(), "reason": body.reason,
                           "evidence": body.evidence, "preferential_duty_pct": a.result.get("preferential_duty_pct")}
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action=f"co.{body.decision.lower()}", entity_type="goods_item",
                 entity_id=it.id, case_id=case.id, before=before, after=a.reviewer_decision, reason=body.reason, evidence=body.evidence)
    evaluators.run_all(db, case, audit.Actor.user(user))
    recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    db.refresh(a)
    return a
