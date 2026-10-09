import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin, TimestampMixin, utcnow


class ExtractedField(IdMixin, TenantMixin, Base):
    """Raw, immutable parser output with full lineage. Never edited; re-parsing appends new rows."""

    __tablename__ = "extracted_fields"
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("documents.id"), index=True)
    parse_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(50))
    provider_version: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str] = mapped_column(String(300))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseField(IdMixin, TimestampMixin, TenantMixin, Base):
    """Working declaration field: value + confidence + source + reasoning + review status."""

    __tablename__ = "case_fields"
    __table_args__ = (UniqueConstraint("case_id", "key"),)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    section: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120))
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    # AUTO_ACCEPTABLE | NEEDS_REVIEW | BLOCKED | APPROVED | REJECTED
    review_status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(12))  # AI | MANUAL | REVIEWER | CASE
    method: Mapped[str | None] = mapped_column(String(60))
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id"))
    source_extracted_field_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("extracted_fields.id"))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    reasoning: Mapped[str | None] = mapped_column(Text)
    rule_ref: Mapped[str | None] = mapped_column(String(120))
    alternatives: Mapped[Any] = mapped_column(JSONType, default=list)  # other source values (conflicts)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
