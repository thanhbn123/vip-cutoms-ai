"""Deterministic case state machine (no LLM involvement)."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.case import CustomsCase
from app.services import audit


class CaseStatus(StrEnum):
    NEW = "NEW"
    DOCUMENTS_UPLOADED = "DOCUMENTS_UPLOADED"
    AI_PROCESSING = "AI_PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    REVIEWED = "REVIEWED"
    READY_TO_EXPORT = "READY_TO_EXPORT"
    DRAFT_EXPORTED = "DRAFT_EXPORTED"


S = CaseStatus
_REVIEW_STATES = {S.REVIEW_REQUIRED, S.BLOCKED, S.REVIEWED}

ALLOWED: dict[CaseStatus, set[CaseStatus]] = {
    S.NEW: {S.DOCUMENTS_UPLOADED},
    S.DOCUMENTS_UPLOADED: {S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
    S.AI_PROCESSING: _REVIEW_STATES | {S.DOCUMENTS_UPLOADED},
    S.REVIEW_REQUIRED: _REVIEW_STATES | {S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
    S.BLOCKED: _REVIEW_STATES | {S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
    S.REVIEWED: _REVIEW_STATES | {S.READY_TO_EXPORT, S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
    S.READY_TO_EXPORT: _REVIEW_STATES | {S.DRAFT_EXPORTED, S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
    S.DRAFT_EXPORTED: _REVIEW_STATES | {S.DOCUMENTS_UPLOADED, S.AI_PROCESSING},
}


def transition(db: Session, case: CustomsCase, to: CaseStatus, actor: audit.Actor, reason: str, evidence=None) -> None:
    current = CaseStatus(case.status)
    if to == current:
        return
    if to not in ALLOWED[current]:
        raise DomainError("INVALID_TRANSITION", f"{current} → {to} is not allowed", details={"from": current, "to": to})
    before = case.status
    case.status = to.value
    case.row_version += 1
    audit.record(
        db, tenant_id=case.tenant_id, actor=actor, action="case.status_changed", entity_type="case", entity_id=case.id,
        case_id=case.id, before={"status": before}, after={"status": to.value}, reason=reason, evidence=evidence,
    )
