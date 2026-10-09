"""Release gate + case status recomputation. Deterministic; extended in G08."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.services import audit
from app.services.issues import open_issues
from app.services.workflow import CaseStatus, transition


def recompute_case_status(db: Session, case: CustomsCase, actor: audit.Actor) -> str:
    """After evaluation: any CRITICAL open → BLOCKED; any other open → REVIEW_REQUIRED; none → REVIEWED.

    READY_TO_EXPORT is never reached automatically — a Reviewer must mark it (G08).
    """
    issues = open_issues(db, case)
    if any(i.severity == "CRITICAL" for i in issues):
        target = CaseStatus.BLOCKED
    elif issues:
        target = CaseStatus.REVIEW_REQUIRED
    else:
        target = CaseStatus.REVIEWED
    current = CaseStatus(case.status)
    if current in (CaseStatus.READY_TO_EXPORT, CaseStatus.DRAFT_EXPORTED) and target == CaseStatus.REVIEWED:
        return case.status  # nothing new to review; keep the reviewer's decision
    if current in (CaseStatus.NEW, CaseStatus.DOCUMENTS_UPLOADED):
        return case.status  # pipeline has not run yet
    transition(db, case, target, actor, reason=f"{len(issues)} open issue(s), critical={sum(i.severity == 'CRITICAL' for i in issues)}",
               evidence=[{"issue_id": str(i.id), "code": i.code, "severity": i.severity} for i in issues])
    return case.status


def reopen_if_exported(db: Session, case: CustomsCase, actor: audit.Actor, reason: str) -> bool:
    """A decision that changes case data after READY_TO_EXPORT/DRAFT_EXPORTED reopens the case for review (G18C).

    Otherwise the released draft silently diverges from the case. Returns True when a transition happened.
    """
    if case.status in (CaseStatus.READY_TO_EXPORT.value, CaseStatus.DRAFT_EXPORTED.value):
        transition(db, case, CaseStatus.REVIEW_REQUIRED, actor, reason=f"reopened: {reason} after {case.status}")
        return True
    return False


def gate(db: Session, case: CustomsCase) -> dict:
    """Release gate = declaration validation (all CRITICAL checks ok). Deterministic, no LLM."""
    from app.services import declaration

    decl = declaration.build(db, case)
    return {"eligible": decl["release_eligible"], "checks": decl["validation"], "readiness": decl["readiness"], "status": case.status}
