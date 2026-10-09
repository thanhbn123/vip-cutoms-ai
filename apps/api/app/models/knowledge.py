import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TimestampMixin


class KnowledgeDataset(IdMixin, TimestampMixin, Base):
    """A versioned, effective-dated knowledge dataset (HS rules, tariff, FTA, policy).

    G18 provenance: a dataset may back a real filing decision (APP_MODE=full) only when
    `is_authoritative` is true, which `app.services.customs_data.verify` sets after checking the
    legal-source fields and the payload checksum. Demo datasets can never be authoritative (DB
    CHECK constraint). Superseded datasets stay for lineage but are never selected.
    """

    __tablename__ = "knowledge_datasets"
    __table_args__ = (CheckConstraint("NOT (is_authoritative AND is_demo)", name="ck_knowledge_datasets_authoritative_not_demo"),)
    kind: Mapped[str] = mapped_column(String(20))  # HS_RULES | TARIFF | FTA | POLICY
    version: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(300))  # provenance description / URL / document ref
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    # --- provenance (G18) ---
    source_authority: Mapped[str | None] = mapped_column(String(200))  # issuing authority (owner-selected source)
    source_document: Mapped[str | None] = mapped_column(String(300))  # legal document number / title
    source_reference: Mapped[str | None] = mapped_column(String(500))  # URL / archive reference
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # users.id (not FK: users may be deactivated/removed later)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    checksum: Mapped[str | None] = mapped_column(String(64))  # sha256 of the canonical payload
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("knowledge_datasets.id"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HsRule(IdMixin, Base):
    __tablename__ = "hs_rules"
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("knowledge_datasets.id"), index=True)
    heading: Mapped[str] = mapped_column(String(10))  # 4-digit heading (candidates are heading-level, D-006)
    title: Mapped[str] = mapped_column(String(300))
    keywords: Mapped[Any] = mapped_column(JSONType)  # list[str] matched against normalised description
    exclusions: Mapped[Any] = mapped_column(JSONType, default=list)  # keywords that reduce confidence
    required_attributes: Mapped[Any] = mapped_column(JSONType, default=list)  # technical attributes needed to classify
    base_confidence: Mapped[float] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)  # classification note / legal note reference (demo text)
