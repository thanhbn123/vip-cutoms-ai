from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.knowledge import KnowledgeDataset


def upsert(db: Session, case: CustomsCase, kind: str, item_id: uuid.UUID | None, *, status: str, ds: KnowledgeDataset | None,
           inputs: dict, result: dict, reasoning: list[str], effective: date | None = None, keep_decision: bool = True) -> Assessment:
    a = db.execute(select(Assessment).where(Assessment.case_id == case.id, Assessment.item_id == item_id, Assessment.kind == kind)).scalar()
    if a is None:
        a = Assessment(tenant_id=case.tenant_id, case_id=case.id, item_id=item_id, kind=kind)
        db.add(a)
    a.status, a.inputs, a.result, a.reasoning = status, inputs, result, reasoning
    a.dataset_id, a.dataset_version, a.dataset_is_demo = (ds.id, ds.version, ds.is_demo) if ds else (None, None, None)
    a.effective_date = effective or date.today()
    a.computed_at = utcnow()
    if not keep_decision:
        a.reviewer_decision = None
    db.flush()
    return a


def get(db: Session, case_id: uuid.UUID, kind: str, item_id: uuid.UUID | None) -> Assessment | None:
    return db.execute(select(Assessment).where(Assessment.case_id == case_id, Assessment.item_id == item_id, Assessment.kind == kind)).scalar()
