import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class Assessment(IdMixin, TimestampMixin, TenantMixin, Base):
    """Latest deterministic assessment per (case, item, kind). kind: VALUATION (case-level) | TAX | CO | POLICY.

    Results are proposals computed from versioned datasets; they never finalise a legal decision.
    """

    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("case_id", "item_id", "kind"),)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("goods_items.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(30))
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("knowledge_datasets.id"))
    dataset_version: Mapped[str | None] = mapped_column(String(40))
    dataset_is_demo: Mapped[bool | None] = mapped_column()
    effective_date: Mapped[date] = mapped_column(Date)
    inputs: Mapped[Any] = mapped_column(JSONType, default=dict)
    result: Mapped[Any] = mapped_column(JSONType, default=dict)
    reasoning: Mapped[Any] = mapped_column(JSONType, default=list)
    reviewer_decision: Mapped[Any] = mapped_column(JSONType, nullable=True)  # {decision, by, role, at, reason}
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
