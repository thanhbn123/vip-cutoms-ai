import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.api.masterdata import tenant_customer, tenant_supplier
from app.api.schemas import AuditOut, CaseCreate, CaseOut, CaseUpdate
from app.core.rbac import Perm, Role
from app.db import get_db
from app.models.audit import AuditEvent
from app.models.case import CustomsCase
from app.models.identity import User
from app.services import audit
from app.services.workflow import CaseStatus

router = APIRouter(tags=["cases"])


def _next_case_no(db: Session, tenant_id: uuid.UUID) -> str:
    prefix = "VIP-HQ-" + datetime.now(UTC).strftime("%y%m%d") + "-"
    n = db.execute(
        select(func.count()).select_from(CustomsCase).where(CustomsCase.tenant_id == tenant_id, CustomsCase.case_no.like(prefix + "%"))
    ).scalar_one()
    return f"{prefix}{n + 1:03d}"


def _check_reviewer(db: Session, user: User, reviewer_id: uuid.UUID | None) -> None:
    if reviewer_id is None:
        return
    r = db.execute(select(User).where(User.id == reviewer_id, User.tenant_id == user.tenant_id)).scalar()
    if not r or r.role not in (Role.REVIEWER, Role.SENIOR_REVIEWER):
        raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEWER", "message": "reviewer must be a tenant Reviewer"})


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(body: CaseCreate, user: User = Depends(require(Perm.CASE_CREATE)), db: Session = Depends(get_db)):
    tenant_customer(db, user, body.customer_id)
    if body.supplier_id:
        tenant_supplier(db, user, body.supplier_id)
    _check_reviewer(db, user, body.reviewer_id)
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext("case_no:" + str(user.tenant_id)))))
    case = CustomsCase(tenant_id=user.tenant_id, case_no=_next_case_no(db, user.tenant_id), owner_id=user.id,
                       status=CaseStatus.NEW.value, **body.model_dump())
    db.add(case)
    db.flush()
    audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.user(user), action="case.created", entity_type="case",
                 entity_id=case.id, case_id=case.id, after=body.model_dump() | {"case_no": case.case_no, "status": case.status})
    db.commit()
    return case


@router.get("/cases", response_model=list[CaseOut])
def list_cases(status: str | None = Query(default=None), user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    stmt = select(CustomsCase).where(CustomsCase.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(CustomsCase.status == status)
    return db.execute(stmt.order_by(CustomsCase.created_at.desc())).scalars().all()


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    return load_case(db, user, case_id)


@router.patch("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: uuid.UUID, body: CaseUpdate, user: User = Depends(require(Perm.CASE_UPDATE)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    changes = body.model_dump(exclude_unset=True)
    if "reviewer_id" in changes:
        _check_reviewer(db, user, changes["reviewer_id"])
    before = {k: getattr(case, k) for k in changes}
    for k, v in changes.items():
        setattr(case, k, v)
    case.row_version += 1
    audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.user(user), action="case.updated", entity_type="case",
                 entity_id=case.id, case_id=case.id, before=before, after=changes)
    db.commit()
    return case


@router.get("/cases/{case_id}/audit", response_model=list[AuditOut])
def case_audit(case_id: uuid.UUID, user: User = Depends(require(Perm.AUDIT_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(
        select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id, AuditEvent.case_id == case_id).order_by(AuditEvent.created_at)
    ).scalars().all()


@router.get("/audit/verify")
def verify_audit(user: User = Depends(require(Perm.AUDIT_READ)), db: Session = Depends(get_db)):
    return {"tenant_id": str(user.tenant_id), "chain_valid": audit.verify_chain(db, user.tenant_id)}
