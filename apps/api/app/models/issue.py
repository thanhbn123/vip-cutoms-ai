import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class Issue(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("case_id", "dedupe_key"),)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    raised_by: Mapped[str] = mapped_column(String(30), default="system")  # evaluator that owns this issue
    code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(10))  # CRITICAL | WARNING | INFO
    category: Mapped[str] = mapped_column(String(30))  # DOCUMENT_CONFLICT | HS | POLICY | VALUATION | CO | MISSING_DATA | VALIDATION | LEARNING
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(Text)
    target_ref: Mapped[str | None] = mapped_column(String(200))  # field key or goods item ref
    evidence: Mapped[Any] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN | RESOLVED | WAIVED
    auto_resolvable: Mapped[bool] = mapped_column(Boolean, default=False)
    assignee_role: Mapped[str | None] = mapped_column(String(32))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    resolved_by_type: Mapped[str | None] = mapped_column(String(10))
    resolution: Mapped[str | None] = mapped_column(Text)
    resolution_value: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
