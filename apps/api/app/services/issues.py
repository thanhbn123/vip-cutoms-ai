"""Idempotent issue synchronisation. Issues are deterministic outputs of evaluators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.issue import Issue
from app.services import audit


@dataclass
class IssueSpec:
    dedupe_key: str
    code: str
    severity: str  # CRITICAL | WARNING | INFO
    category: str
    title: str
    detail: str = ""
    target_ref: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    auto_resolvable: bool = False
    assignee_role: str | None = "REVIEWER"


def sync(db: Session, case: CustomsCase, specs: list[IssueSpec], owner: str) -> None:
    """Create new issues, refresh open ones, auto-resolve vanished auto-resolvable ones.

    Only issues raised by `owner` (an evaluator name) are touched, so evaluators run independently.
    """
    existing = {
        i.dedupe_key: i
        for i in db.execute(select(Issue).where(Issue.case_id == case.id, Issue.raised_by == owner)).scalars()
    }
    seen: set[str] = set()
    for spec in specs:
        seen.add(spec.dedupe_key)
        cur = existing.get(spec.dedupe_key)
        if cur is None:
            cur = Issue(tenant_id=case.tenant_id, case_id=case.id, dedupe_key=spec.dedupe_key, raised_by=owner, code=spec.code,
                        severity=spec.severity, category=spec.category, title=spec.title, detail=spec.detail,
                        target_ref=spec.target_ref, evidence=spec.evidence, status="OPEN",
                        auto_resolvable=spec.auto_resolvable, assignee_role=spec.assignee_role)
            db.add(cur)
            db.flush()
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.system(), action="issue.raised", entity_type="issue",
                         entity_id=cur.id, case_id=case.id,
                         after={"code": spec.code, "severity": spec.severity, "title": spec.title, "target": spec.target_ref},
                         evidence=spec.evidence)
        elif cur.status == "OPEN":
            cur.detail, cur.evidence, cur.title = spec.detail, spec.evidence, spec.title
        elif cur.status == "RESOLVED" and cur.resolved_by_type == "SYSTEM":
            # auto-resolved earlier, condition detected again → reopen (never leave a live condition hidden, G18C)
            cur.status, cur.resolved_at, cur.resolution, cur.resolved_by_type = "OPEN", None, None, None
            cur.detail, cur.evidence, cur.title, cur.severity = spec.detail, spec.evidence, spec.title, spec.severity
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.system(), action="issue.reopened", entity_type="issue",
                         entity_id=cur.id, case_id=case.id, before={"status": "RESOLVED"}, after={"status": "OPEN", "code": cur.code},
                         reason="Condition detected again after re-evaluation")
    for key, cur in existing.items():
        if key not in seen and cur.status == "OPEN" and cur.auto_resolvable:
            cur.status = "RESOLVED"
            cur.resolved_by_type = "SYSTEM"
            cur.resolution = "Condition no longer present after re-evaluation"
            cur.resolved_at = utcnow()
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.system(), action="issue.auto_resolved",
                         entity_type="issue", entity_id=cur.id, case_id=case.id, before={"status": "OPEN"},
                         after={"status": "RESOLVED"}, reason=cur.resolution)


def open_issues(db: Session, case: CustomsCase) -> list[Issue]:
    return list(db.execute(select(Issue).where(Issue.case_id == case.id, Issue.status == "OPEN")).scalars())
