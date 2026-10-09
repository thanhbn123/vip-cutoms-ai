import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin


class DeclarationDraft(IdMixin, TenantMixin, Base):
    """Immutable, versioned internal declaration draft. Never a customs submission (no write endpoints)."""

    __tablename__ = "declaration_drafts"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))  # PREVIEW | RELEASE
    schema_version: Mapped[str] = mapped_column(String(30))
    release_eligible: Mapped[bool] = mapped_column(Boolean)
    watermark: Mapped[str] = mapped_column(String(120))
    case_status_at_export: Mapped[str] = mapped_column(String(32))
    payload: Mapped[Any] = mapped_column(JSONType)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
