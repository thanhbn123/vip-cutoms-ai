import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.core.errors import DomainError
from app.core.rbac import Perm
from app.db import get_db
from app.models.document import Document
from app.models.extraction import CaseField, ExtractedField
from app.models.identity import User
from app.models.issue import Issue
from app.services import audit, evaluators, mapping
from app.services.issues import IssueSpec
from app.services.issues import sync as sync_issues
from app.services.release import reopen_if_exported
from app.services.workflow import CaseStatus, transition

router = APIRouter(tags=["pipeline"])


class FieldOut(BaseModel):
    id: uuid.UUID
    key: str
    section: str
    label: str
    value: str | None
    confidence: float | None
    is_critical: bool
    review_status: str
    origin: str
    method: str | None
    source_document_id: uuid.UUID | None
    source_ref: str | None
    reasoning: str | None
    rule_ref: str | None
    alternatives: list
    approved_by: uuid.UUID | None
    model_config = {"from_attributes": True}


class ExtractedOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    parse_run_id: uuid.UUID
    key: str
    value: str
    confidence: float
    method: str
    provider: str
    provider_version: str
    source_ref: str
    model_config = {"from_attributes": True}


class IssueOut(BaseModel):
    id: uuid.UUID
    code: str
    severity: str
    category: str
    title: str
    detail: str | None
    target_ref: str | None
    evidence: list
    status: str
    assignee_role: str | None
    resolution: str | None
    resolution_value: str | None
    model_config = {"from_attributes": True}


class FieldSetIn(BaseModel):
    value: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=3, max_length=2000)


def run_pipeline(db: Session, case, user: User, *, parse: bool = True) -> dict:
    """Parse current unparsed/all documents, map fields, then run downstream evaluators (registered by later gates)."""
    actor = audit.Actor.user(user)
    docs = db.execute(select(Document).where(Document.case_id == case.id, Document.is_current.is_(True))).scalars().all()
    if not docs:
        raise DomainError("NO_DOCUMENTS", "upload at least one document before running the pipeline")
    transition(db, case, CaseStatus.AI_PROCESSING, actor, reason="pipeline started")
    parsed = 0
    if parse:
        for d in docs:
            mapping.parse_document(db, case, d, actor)
            parsed += 1
    specs = []
    for d in docs:
        if d.status != "PARSE_FAILED":
            continue
        provider_failed = any(str(w).startswith("provider failure") for w in (d.parse_warnings or []))
        # Any current document that yielded no values blocks the case (G18C): a scanned invoice nobody could read must
        # never let a case reach REVIEWED just because the other documents parsed.
        specs.append(IssueSpec(f"provider_failed:{d.id}" if provider_failed else f"unreadable:{d.id}",
                               "AI_PROVIDER_FAILED" if provider_failed else "DOCUMENT_UNREADABLE", "CRITICAL", "DOCUMENT",
                               f"{d.doc_type} {d.filename}: " + ("AI provider không trả kết quả hợp lệ" if provider_failed
                                                                else "không trích xuất được dữ liệu (scan/ảnh hoặc định dạng không đọc được)"),
                               "Không có giá trị nào được trích xuất (fail-closed). Tải lại bản đọc được, thử lại pipeline hoặc nhập thủ công; không suy đoán.",
                               target_ref=f"document:{d.id}", auto_resolvable=True, evidence=[{"warnings": d.parse_warnings}]))
    sync_issues(db, case, specs, "provider")
    mapping.map_fields(db, case, actor)
    evaluators.run_all(db, case, actor)
    from app.services.release import recompute_case_status

    status = recompute_case_status(db, case, actor)
    return {"documents_parsed": parsed, "status": status}


@router.post("/cases/{case_id}/pipeline/run")
def pipeline_run(case_id: uuid.UUID, user: User = Depends(require(Perm.PARSE_RUN)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    out = run_pipeline(db, case, user)
    db.commit()
    return out


@router.get("/cases/{case_id}/fields", response_model=list[FieldOut])
def list_fields(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(CaseField).where(CaseField.case_id == case_id).order_by(CaseField.section, CaseField.key)).scalars().all()


@router.get("/cases/{case_id}/extractions", response_model=list[ExtractedOut])
def list_extractions(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(ExtractedField).where(ExtractedField.case_id == case_id)
                      .order_by(ExtractedField.document_id, ExtractedField.key)).scalars().all()


@router.get("/cases/{case_id}/issues", response_model=list[IssueOut])
def list_issues(case_id: uuid.UUID, status: str | None = None, user: User = Depends(require(Perm.CASE_READ)),
                db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    stmt = select(Issue).where(Issue.case_id == case_id)
    if status:
        stmt = stmt.where(Issue.status == status)
    return db.execute(stmt.order_by(Issue.severity, Issue.created_at)).scalars().all()


@router.put("/cases/{case_id}/fields/{key}", response_model=FieldOut)
def set_field(case_id: uuid.UUID, key: str, body: FieldSetIn, user: User = Depends(require(Perm.FIELD_EDIT)),
              db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    if case.status == CaseStatus.DRAFT_EXPORTED.value:
        raise DomainError("CASE_EXPORTED", "re-open the case (upload/pipeline) before editing an exported case")
    try:
        cf = mapping.set_field_manual(db, case, user, key, body.value, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "UNKNOWN_FIELD", "message": str(exc)}) from exc
    _reevaluate(db, case, user)
    db.commit()
    db.refresh(cf)
    return cf


@router.post("/cases/{case_id}/fields/{key}/approve", response_model=FieldOut)
def approve_field(case_id: uuid.UUID, key: str, body: FieldSetIn | None = None, user: User = Depends(require(Perm.PROPOSAL_DECIDE)),
                  db: Session = Depends(get_db)):
    """Reviewer approves the current AI value (optionally choosing one of the alternatives via body.value)."""
    case = load_case(db, user, case_id, for_update=True)
    cf = db.execute(select(CaseField).where(CaseField.case_id == case.id, CaseField.key == key)).scalar()
    if cf is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "field not mapped"})
    reopen_if_exported(db, case, audit.Actor.user(user), f"field {key} approved")
    if body and body.value and (body.value.strip() != (cf.value or "").strip() or cf.alternatives):
        # A different value, or an explicit choice among conflicting document values, is a reviewer entry (field.manual_set).
        # The SAME value on an unconflicted field is an approval of the AI value and keeps its document lineage (G18C).
        cf = mapping.set_field_manual(db, case, user, key, body.value, body.reason)
    else:
        if not cf.value:
            raise DomainError("NO_VALUE", "cannot approve an empty field; enter a value instead")
        before = {"review_status": cf.review_status}
        cf.review_status = "APPROVED"
        cf.approved_by = user.id
        from app.models.base import utcnow

        cf.approved_at = utcnow()
        audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="field.approved", entity_type="case_field",
                     entity_id=cf.id, case_id=case.id, before=before, after={"key": key, "value": cf.value, "review_status": "APPROVED"},
                     reason=body.reason if body else "approved AI value")
    _reevaluate(db, case, user)
    db.commit()
    db.refresh(cf)
    return cf


def _reevaluate(db: Session, case, user: User) -> None:
    """Field changes feed valuation/tax/C-O/policy: re-map against documents, re-run evaluators, recompute status."""
    from app.services.release import recompute_case_status

    actor = audit.Actor.user(user)
    mapping.map_fields(db, case, actor)
    evaluators.run_all(db, case, actor)
    recompute_case_status(db, case, actor)
