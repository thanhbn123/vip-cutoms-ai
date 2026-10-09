import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ensure, load_case, require
from app.api.pipeline import IssueOut
from app.core.errors import DomainError, not_found
from app.core.http import content_disposition
from app.core.rbac import Perm, has_perm
from app.db import get_db
from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.draft import DeclarationDraft
from app.models.extraction import CaseField
from app.models.identity import User
from app.models.issue import Issue
from app.services import audit, declaration, evaluators, release
from app.services.export_adapters import ADAPTERS
from app.services.release import recompute_case_status
from app.services.workflow import CaseStatus, transition

router = APIRouter(tags=["review"])


class ResolveIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)
    resolution_value: str | None = Field(default=None, max_length=2000)
    evidence: list[str] = []


class DraftIn(BaseModel):
    kind: Literal["PREVIEW", "RELEASE"] = "PREVIEW"
    reason: str | None = Field(default=None, max_length=2000)


class DraftOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    version: int
    kind: str
    schema_version: str
    release_eligible: bool
    watermark: str
    case_status_at_export: str
    checksum: str
    created_by: uuid.UUID
    created_at: object
    model_config = {"from_attributes": True}


def _issue(db: Session, user: User, case_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
    i = db.execute(select(Issue).where(Issue.id == issue_id, Issue.case_id == case_id, Issue.tenant_id == user.tenant_id)).scalar()
    if not i:
        raise not_found("issue")
    return i


def _close(db, case, user, issue: Issue, status: str, body: ResolveIn, action: str) -> Issue:
    if issue.status != "OPEN":
        raise DomainError("ISSUE_NOT_OPEN", f"issue is {issue.status}")
    before = {"status": issue.status}
    issue.status = status
    issue.resolved_by = user.id
    issue.resolved_by_type = "USER"
    issue.resolution = body.reason
    issue.resolution_value = body.resolution_value
    issue.resolved_at = utcnow()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action=action, entity_type="issue", entity_id=issue.id,
                 case_id=case.id, before=before, after={"status": status, "code": issue.code, "severity": issue.severity, "target": issue.target_ref},
                 reason=body.reason, evidence=body.evidence or issue.evidence)
    recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    db.refresh(issue)
    return issue


@router.post("/cases/{case_id}/issues/{issue_id}/resolve", response_model=IssueOut)
def resolve_issue(case_id: uuid.UUID, issue_id: uuid.UUID, body: ResolveIn, user: User = Depends(require(Perm.ISSUE_RESOLVE)),
                  db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    return _close(db, case, user, _issue(db, user, case_id, issue_id), "RESOLVED", body, "issue.resolved")


@router.post("/cases/{case_id}/issues/{issue_id}/waive", response_model=IssueOut)
def waive_issue(case_id: uuid.UUID, issue_id: uuid.UUID, body: ResolveIn, user: User = Depends(require(Perm.ISSUE_WAIVE_WARNING)),
                db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    issue = _issue(db, user, case_id, issue_id)
    if issue.severity == "CRITICAL":
        ensure(user, Perm.ISSUE_WAIVE_CRITICAL)  # Senior Reviewer only (D-009)
        if not body.evidence:
            raise HTTPException(status_code=422, detail={"code": "EVIDENCE_REQUIRED", "message": "waiving a critical issue requires evidence"})
    return _close(db, case, user, issue, "WAIVED", body, "issue.waived")


class ApproveAllIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/cases/{case_id}/fields/approve-all")
def approve_all_fields(case_id: uuid.UUID, body: ApproveAllIn, user: User = Depends(require(Perm.PROPOSAL_DECIDE)), db: Session = Depends(get_db)):
    """Approve every NEEDS_REVIEW critical field that has a value and no open conflict on it. Conflicted fields are skipped (fail closed)."""
    case = load_case(db, user, case_id, for_update=True)
    conflicted = {i.target_ref for i in db.execute(select(Issue).where(Issue.case_id == case.id, Issue.status == "OPEN",
                                                                        Issue.category.in_(("DOCUMENT_CONFLICT", "VALIDATION")))).scalars()}
    approved, skipped = [], []
    for cf in db.execute(select(CaseField).where(CaseField.case_id == case.id, CaseField.review_status == "NEEDS_REVIEW")).scalars():
        if not cf.value or cf.key in conflicted:
            skipped.append(cf.key)
            continue
        cf.review_status = "APPROVED"
        cf.approved_by = user.id
        cf.approved_at = utcnow()
        approved.append(cf.key)
        audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="field.approved", entity_type="case_field", entity_id=cf.id,
                     case_id=case.id, before={"review_status": "NEEDS_REVIEW"}, after={"key": cf.key, "value": cf.value, "review_status": "APPROVED"},
                     reason=body.reason)
    evaluators.run_all(db, case, audit.Actor.user(user))
    recompute_case_status(db, case, audit.Actor.user(user))
    db.commit()
    return {"approved": sorted(approved), "skipped": sorted(skipped)}


@router.post("/cases/{case_id}/mark-ready")
def mark_ready(case_id: uuid.UUID, body: ApproveAllIn, user: User = Depends(require(Perm.CASE_MARK_READY)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    g = release.gate(db, case)
    if not g["eligible"]:
        raise DomainError("RELEASE_GATE_FAILED", "case does not pass the release gate", details={"checks": [c for c in g["checks"] if not c["ok"]]})
    if case.status != CaseStatus.REVIEWED.value:
        recompute_case_status(db, case, audit.Actor.user(user))
    transition(db, case, CaseStatus.READY_TO_EXPORT, audit.Actor.user(user), reason=body.reason, evidence=g["checks"])
    db.commit()
    return {"status": case.status, "gate": g}


def _draft_payload(db, case, user, kind: str) -> tuple[dict, bool, str]:
    decl = declaration.build(db, case)
    eligible = kind == "RELEASE" and decl["release_eligible"] and case.status in (CaseStatus.READY_TO_EXPORT.value, CaseStatus.DRAFT_EXPORTED.value)
    watermark = "DRAFT — INTERNAL RELEASE DRAFT — NOT A CUSTOMS SUBMISSION" if eligible else "DRAFT — INTERNAL PREVIEW — NOT FOR SUBMISSION"
    return decl, eligible, watermark


@router.post("/cases/{case_id}/drafts", response_model=DraftOut, status_code=201)
def create_draft(case_id: uuid.UUID, body: DraftIn, user: User = Depends(require(Perm.DRAFT_PREVIEW)), db: Session = Depends(get_db)):
    case = load_case(db, user, case_id, for_update=True)
    if body.kind == "RELEASE":
        ensure(user, Perm.DRAFT_EXPORT_RELEASE)
        g = release.gate(db, case)
        if case.status not in (CaseStatus.READY_TO_EXPORT.value, CaseStatus.DRAFT_EXPORTED.value) or not g["eligible"]:
            raise DomainError("RELEASE_BLOCKED", "release draft requires READY_TO_EXPORT and a passing release gate",
                              details={"status": case.status, "checks": [c for c in g["checks"] if not c["ok"]]})
    decl, eligible, watermark = _draft_payload(db, case, user, body.kind)
    version = (db.execute(select(func.max(DeclarationDraft.version)).where(DeclarationDraft.case_id == case.id)).scalar() or 0) + 1
    payload = {"meta": {"schema_version": declaration.SCHEMA_VERSION, "version": version, "kind": body.kind, "watermark": watermark,
                        "release_eligible": eligible, "generated_at": utcnow().isoformat(), "generated_by": str(user.id),
                        "case_status": case.status, "disclaimer": decl["disclaimer"], "legal_notice": decl["demo_notice"],
                        "demo_datasets": decl["demo_datasets"]}, **decl}
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    d = DeclarationDraft(tenant_id=case.tenant_id, case_id=case.id, version=version, kind=body.kind, schema_version=declaration.SCHEMA_VERSION,
                         release_eligible=eligible, watermark=watermark, case_status_at_export=case.status, payload=payload, checksum=checksum,
                         created_by=user.id, created_at=utcnow())
    db.add(d)
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="draft.exported", entity_type="declaration_draft", entity_id=d.id,
                 case_id=case.id, after={"version": version, "kind": body.kind, "release_eligible": eligible, "checksum": checksum},
                 reason=body.reason or f"{body.kind} draft")
    if eligible:
        transition(db, case, CaseStatus.DRAFT_EXPORTED, audit.Actor.user(user), reason=f"release draft v{version} exported", evidence={"draft_id": str(d.id)})
    db.commit()
    return d


@router.get("/cases/{case_id}/drafts", response_model=list[DraftOut])
def list_drafts(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    return db.execute(select(DeclarationDraft).where(DeclarationDraft.case_id == case_id).order_by(DeclarationDraft.version)).scalars().all()


@router.get("/drafts/{draft_id}")
def download_draft(draft_id: uuid.UUID, format: Literal["json", "csv"] = "json", user: User = Depends(require(Perm.CASE_READ)),
                   db: Session = Depends(get_db)):
    d = db.execute(select(DeclarationDraft).where(DeclarationDraft.id == draft_id, DeclarationDraft.tenant_id == user.tenant_id)).scalar()
    if not d:
        raise not_found("draft")
    adapter = ADAPTERS[format]
    fname = f"{d.payload['case']['case_no']}-draft-v{d.version}.{format}"
    return Response(content=adapter.render(d.payload), media_type=adapter.content_type,
                    headers={"Content-Disposition": content_disposition(fname), "X-Draft-Checksum": d.checksum, "Cache-Control": "private, no-store"})


@router.get("/review/queue")
def review_queue(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    cases = db.execute(select(CustomsCase).where(CustomsCase.tenant_id == user.tenant_id,
                                                 CustomsCase.status.in_(("REVIEW_REQUIRED", "BLOCKED", "REVIEWED", "AI_PROCESSING")))).scalars().all()
    rows = []
    for c in cases:
        issues = db.execute(select(Issue).where(Issue.case_id == c.id, Issue.status == "OPEN")).scalars().all()
        crit = sum(i.severity == "CRITICAL" for i in issues)
        rows.append({"case_id": str(c.id), "case_no": c.case_no, "status": c.status, "priority": c.priority, "owner_id": str(c.owner_id),
                     "reviewer_id": str(c.reviewer_id) if c.reviewer_id else None, "open_critical": crit, "open_warning": len(issues) - crit,
                     "top_issues": [{"id": str(i.id), "code": i.code, "severity": i.severity, "title": i.title, "target_ref": i.target_ref,
                                     "assignee_role": i.assignee_role} for i in sorted(issues, key=lambda i: (i.severity != "CRITICAL", i.created_at))[:4]],
                     "updated_at": c.updated_at.isoformat()})
    prio = {"HIGH": 0, "NORMAL": 1, "LOW": 2}
    rows.sort(key=lambda r: (-r["open_critical"], prio.get(r["priority"], 9), r["updated_at"]))
    return rows


@router.get("/dashboard/summary")
def dashboard(user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(CustomsCase.status, func.count()).where(CustomsCase.tenant_id == user.tenant_id).group_by(CustomsCase.status)).all())
    open_issues = db.execute(select(Issue.severity, func.count()).where(Issue.tenant_id == user.tenant_id, Issue.status == "OPEN").group_by(Issue.severity)).all()
    fields = db.execute(select(CaseField.review_status, func.count()).where(CaseField.tenant_id == user.tenant_id).group_by(CaseField.review_status)).all()
    ft = dict(fields)
    total_fields = sum(ft.values())
    auto = ft.get("AUTO_ACCEPTABLE", 0) + ft.get("APPROVED", 0)
    return {"cases_by_status": counts, "open_issues": dict(open_issues), "fields_total": total_fields,
            "fields_accepted_pct": round(100 * auto / total_fields) if total_fields else 0, "drafts_exported": db.execute(
                select(func.count()).select_from(DeclarationDraft).where(DeclarationDraft.tenant_id == user.tenant_id, DeclarationDraft.release_eligible.is_(True))).scalar(),
            "can_decide": has_perm(user.role, Perm.PROPOSAL_DECIDE)}
