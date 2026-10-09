import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.api.goods import _item
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.modes import policy
from app.core.rbac import Perm
from app.db import get_db
from app.models.assessment import Assessment
from app.models.base import utcnow
from app.models.identity import User
from app.models.knowledge import HsRule, KnowledgeDataset
from app.services import assessments, audit, customs_data, evaluators
from app.services.knowledge import dataset_payload
from app.services.release import recompute_case_status, reopen_if_exported

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
    # G18 provenance
    is_authoritative: bool = False
    source_authority: str | None = None
    source_document: str | None = None
    source_reference: str | None = None
    ingested_at: datetime | None = None
    verified_at: datetime | None = None
    verified_by: uuid.UUID | None = None
    checksum: str | None = None
    supersedes_id: uuid.UUID | None = None
    superseded_at: datetime | None = None
    model_config = {"from_attributes": True}


class DatasetPatch(BaseModel):
    is_active: bool
    reason: str = Field(min_length=3, max_length=2000)


class DatasetImportIn(BaseModel):
    """An owner-supplied dataset package (docs/G18_CUSTOMS_DATA_SCHEMA.md). Stored INACTIVE and UNVERIFIED."""

    kind: Literal["HS_RULES", "TARIFF", "FTA", "POLICY"]
    version: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=3, max_length=200)
    effective_from: date
    effective_to: date | None = None
    source_authority: str | None = Field(default=None, max_length=200)
    source_document: str | None = Field(default=None, max_length=300)
    source_reference: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any]
    is_demo: bool = False
    notes: str | None = None
    reason: str = Field(min_length=3, max_length=2000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class SupersedeIn(ReasonIn):
    new_dataset_id: uuid.UUID


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


def _get(db: Session, dataset_id: uuid.UUID) -> KnowledgeDataset:
    ds = db.get(KnowledgeDataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "dataset not found"})
    return ds


@router.get("/knowledge/datasets", response_model=list[DatasetOut])
def list_datasets(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    s = get_settings()
    if s.is_development and policy(s).demo_data_allowed:
        from app.services.knowledge import seed_demo

        seed_demo(db)  # idempotent demo seed so the Knowledge Hub is never empty in dev/test (never in full mode)
        db.commit()
    counts = dict(db.execute(select(HsRule.dataset_id, func.count()).group_by(HsRule.dataset_id)).all())
    out = []
    for ds in db.execute(select(KnowledgeDataset).order_by(KnowledgeDataset.kind, KnowledgeDataset.effective_from.desc())).scalars():
        o = DatasetOut.model_validate(ds)
        payload = dataset_payload(ds) if ds.kind != "HS_RULES" else {}
        o.rule_count = counts.get(ds.id, 0) or sum(len(v) if isinstance(v, (list, dict)) else 1 for v in payload.values())
        out.append(o)
    return out


@router.get("/knowledge/notice")
def demo_notice(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    """UI banner source: runtime mode + which active datasets are demo. Never empty-string a notice when demo data is in use."""
    from app.services.declaration import DEMO_NOTICE

    s = get_settings()
    pol = policy(s)
    active = db.execute(select(KnowledgeDataset).where(KnowledgeDataset.is_active.is_(True),
                                                      KnowledgeDataset.superseded_at.is_(None))).scalars().all()
    demo = [f"{d.kind} {d.version}" for d in active if d.is_demo]
    providers = {cap: s.provider_for(cap) for cap in ("document_ocr", "document_ai", "hs_ai", "copilot")}
    return {"demo_active": bool(demo), "notice": DEMO_NOTICE if demo else None, "datasets": demo,
            "non_demo_datasets": [f"{d.kind} {d.version}" for d in active if not d.is_demo],
            "authoritative_datasets": [f"{d.kind} {d.version}" for d in active if d.is_authoritative],
            "app_mode": s.app_mode, "mode_notice": pol.notice, "real_filing_decisions": pol.real_filing_decisions,
            "mock_ai_active": any(v == "mock" for v in providers.values()), "providers": providers}


@router.get("/knowledge/datasets/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    ds = _get(db, dataset_id)
    body = DatasetOut.model_validate(ds).model_dump(mode="json")
    body["provenance_problems"] = customs_data.provenance_problems(ds)
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
    ds = _get(db, dataset_id)
    before = {"is_active": ds.is_active}
    ds.is_active = body.is_active
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action="knowledge.dataset_toggled", entity_type="knowledge_dataset",
                 entity_id=ds.id, before=before, after={"is_active": ds.is_active, "kind": ds.kind, "version": ds.version}, reason=body.reason)
    db.commit()
    return DatasetOut.model_validate(ds)


@router.post("/knowledge/datasets/import", response_model=DatasetOut, status_code=201)
def import_dataset(body: DatasetImportIn, admin: User = Depends(require(Perm.KNOWLEDGE_MANAGE)), db: Session = Depends(get_db)):
    """Register a dataset package. It arrives INACTIVE and UNVERIFIED; nothing uses it until it is verified and activated."""
    pkg = customs_data.package_from_dict(body.model_dump(exclude={"reason"}))
    ds = customs_data.register(db, pkg, admin, reason=body.reason)
    db.commit()
    db.refresh(ds)
    return DatasetOut.model_validate(ds)


@router.post("/knowledge/datasets/{dataset_id}/verify", response_model=DatasetOut)
def verify_dataset(dataset_id: uuid.UUID, body: ReasonIn, verifier: User = Depends(require(Perm.KNOWLEDGE_VERIFY)),
                   db: Session = Depends(get_db)):
    """Mark a dataset authoritative. Refused (409 MISSING_AUTHORITY) for demo data, missing legal source or checksum mismatch."""
    ds = _get(db, dataset_id)
    customs_data.verify(db, ds, verifier, reason=body.reason)
    db.commit()
    db.refresh(ds)
    return DatasetOut.model_validate(ds)


@router.post("/knowledge/datasets/{dataset_id}/supersede", response_model=DatasetOut)
def supersede_dataset(dataset_id: uuid.UUID, body: SupersedeIn, admin: User = Depends(require(Perm.KNOWLEDGE_MANAGE)),
                      db: Session = Depends(get_db)):
    old = _get(db, dataset_id)
    new = _get(db, body.new_dataset_id)
    customs_data.supersede(db, old, new, admin, reason=body.reason)
    db.commit()
    db.refresh(old)
    return DatasetOut.model_validate(old)


@router.get("/cases/{case_id}/assessments", response_model=list[AssessmentOut])
def list_assessments(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(Assessment).where(Assessment.case_id == case_id).order_by(Assessment.kind, Assessment.item_id)).scalars().all()


@router.post("/cases/{case_id}/items/{item_id}/co-decision", response_model=AssessmentOut)
def co_decision(case_id: uuid.UUID, item_id: uuid.UUID, body: CoDecisionIn, user: User = Depends(require(Perm.PROPOSAL_DECIDE)),
                db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    reopen_if_exported(db, case, audit.Actor.user(user), "C/O decision")
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
