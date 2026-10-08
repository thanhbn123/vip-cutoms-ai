import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import IdMixin, TenantMixin, utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


class AuditEvent(IdMixin, TenantMixin, Base):
    """Append-only. UPDATE/DELETE are rejected by a database trigger (migration 0002)."""

    __tablename__ = "audit_events"
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_type: Mapped[str] = mapped_column(String(10))  # USER | AI | SYSTEM
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    before: Mapped[Any] = mapped_column(JSONType, nullable=True)
    after: Mapped[Any] = mapped_column(JSONType, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2000))
    evidence: Mapped[Any] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
