import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class Document(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "documents"
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(20))  # INVOICE | PACKING_LIST | BILL_OF_LADING | CO | CONTRACT | CATALOGUE | OTHER
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_backend: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id"))
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED")  # UPLOADED | PARSED | PARSE_FAILED | SUPERSEDED
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    meta: Mapped[Any] = mapped_column(JSONType, default=dict)  # issuer, document no/date supplied at upload
    parse_provider: Mapped[str | None] = mapped_column(String(50))
    parse_provider_version: Mapped[str | None] = mapped_column(String(50))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_confidence: Mapped[float | None] = mapped_column(Float)
    parse_warnings: Mapped[Any] = mapped_column(JSONType, default=list)
