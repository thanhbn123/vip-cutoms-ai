import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.core.errors import DomainError, not_found
from app.core.rbac import Perm
from app.db import get_db
from app.models.base import utcnow
from app.models.copilot import CopilotMessage, Proposal
from app.models.goods import GoodsItem
from app.models.identity import User
from app.services import audit, copilot, evaluators
from app.services.release import recompute_case_status, reopen_if_exported

router = APIRouter(tags=["copilot"])


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    intent: str | None
    sources: list
    reasoning: list
    provider: str | None
    proposal_id: uuid.UUID | None
    meta: dict
    created_at: object
    model_config = {"from_attributes": True}


class ProposalOut(BaseModel):
    id: uuid.UUID
    target_type: str
    target_ref: str
    current_value: str | None
    proposed_value: str
    reasoning: list
    sources: list
    provider: str
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decision_reason: str | None
    created_at: object
    model_config = {"from_attributes": True}


class DecideIn(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/cases/{case_id}/copilot/ask")
def ask(case_id: uuid.UUID, body: AskIn, user: User = Depends(require(Perm.COPILOT_ASK)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id)
    try:
        out = copilot.ask(db, case, user, body.question)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "PROVIDER_INVALID_OUTPUT", "message": str(exc)}) from exc
    db.commit()
    return out


@router.get("/cases/{case_id}/copilot/messages", response_model=list[MessageOut])
def messages(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(CopilotMessage).where(CopilotMessage.case_id == case_id).order_by(CopilotMessage.created_at, CopilotMessage.role.desc())).scalars().all()


@router.get("/cases/{case_id}/proposals", response_model=list[ProposalOut])
def proposals(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(Proposal).where(Proposal.case_id == case_id).order_by(Proposal.created_at)).scalars().all()


@router.post("/cases/{case_id}/proposals/{proposal_id}/decide", response_model=ProposalOut)
def decide(case_id: uuid.UUID, proposal_id: uuid.UUID, body: DecideIn, user: User = Depends(require(Perm.PROPOSAL_DECIDE)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    p = db.execute(select(Proposal).where(Proposal.id == proposal_id, Proposal.case_id == case.id, Proposal.tenant_id == user.tenant_id)).scalar()
    if not p:
        raise not_found("proposal")
    if p.status != "PROPOSED":
        raise DomainError("PROPOSAL_DECIDED", f"proposal already {p.status}")
    if p.requested_by == user.id:
        raise DomainError("SEPARATION_OF_DUTIES", "the requester of a proposal cannot approve it (D-011)")
    if body.decision == "APPROVE":
        reopen_if_exported(db, case, audit.Actor.user(user), "proposal applied")
    p.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    p.decided_by, p.decided_at, p.decision_reason = user.id, utcnow(), body.reason
    applied = None
    if p.status == "APPROVED" and p.target_type == "ITEM_DESCRIPTION_VN":
        item = db.execute(select(GoodsItem).where(GoodsItem.id == uuid.UUID(p.target_ref), GoodsItem.case_id == case.id)).scalar()
        if item is None:
            raise DomainError("TARGET_MISSING", "target item no longer exists")
        applied = {"before": item.description_vn, "after": p.proposed_value}
        item.description_vn = p.proposed_value
        item.description_vn_status = "APPROVED"
        item.manual_fields = sorted(set(item.manual_fields or []) | {"description_vn"})
        item.row_version += 1
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action=f"proposal.{body.decision.lower()}d", entity_type="proposal", entity_id=p.id,
                 case_id=case.id, before={"status": "PROPOSED", "value": p.current_value}, after={"status": p.status, "applied": applied}, reason=body.reason,
                 evidence=p.sources)
    if applied:
        evaluators.run_all(db, case, audit.Actor.user(user))
        recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    return p
