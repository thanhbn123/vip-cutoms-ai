import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, Float, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TimestampMixin


class KnowledgeDataset(IdMixin, TimestampMixin, Base):
    """Versioned, effective-dated knowledge (HS rules, tariff, FTA, policy). Global, not tenant-scoped.

    `is_demo=True` rows are fixtures and are labelled NON-AUTHORITATIVE everywhere they are shown.
    """

    __tablename__ = "knowledge_datasets"
    __table_args__ = (UniqueConstraint("kind", "version"),)
    kind: Mapped[str] = mapped_column(String(20))  # HS_RULES | TARIFF | FTA | POLICY
    version: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(300))  # provenance description / URL / document ref
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


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
