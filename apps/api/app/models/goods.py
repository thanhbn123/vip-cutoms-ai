import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class GoodsItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "goods_items"
    __table_args__ = (UniqueConstraint("case_id", "line_no"),)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)  # as on invoice
    description_vn: Mapped[str | None] = mapped_column(Text)  # customs description (proposed/edited)
    description_vn_status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")
    model: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[str | None] = mapped_column(String(40))
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[str | None] = mapped_column(String(40))
    amount: Mapped[str | None] = mapped_column(String(40))
    packages: Mapped[str | None] = mapped_column(String(40))
    origin_criterion: Mapped[str | None] = mapped_column(String(20))  # from C/O line
    co_line_matched: Mapped[bool | None] = mapped_column(Boolean)
    attributes: Mapped[Any] = mapped_column(JSONType, default=dict)  # technical attributes {name: {value, source, source_ref}}
    attribute_sources: Mapped[Any] = mapped_column(JSONType, default=list)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id"))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    manual_fields: Mapped[Any] = mapped_column(JSONType, default=list)  # fields edited by humans (never overwritten by re-map)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    hs_code: Mapped[str | None] = mapped_column(String(12))  # approved 8-digit code
    hs_status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")  # NEEDS_REVIEW | BLOCKED | APPROVED
    hs_confidence: Mapped[float | None] = mapped_column(Float)
    hs_decision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class HsCandidate(IdMixin, TenantMixin, Base):
    __tablename__ = "hs_candidates"
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("goods_items.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    rank: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(300))
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[Any] = mapped_column(JSONType)  # list[str]
    matched_keywords: Mapped[Any] = mapped_column(JSONType, default=list)
    missing_attributes: Mapped[Any] = mapped_column(JSONType, default=list)
    evidence: Mapped[Any] = mapped_column(JSONType, default=list)  # document refs
    history_refs: Mapped[Any] = mapped_column(JSONType, default=list)  # approved-memory references (G10)
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("knowledge_datasets.id"))
    dataset_version: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")  # PROPOSED | APPROVED | REJECTED | SUPERSEDED
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClassificationDecision(IdMixin, TenantMixin, Base):
    """Reviewer decision on an item's HS. Immutable record; the item points at the latest APPROVE."""

    __tablename__ = "classification_decisions"
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("goods_items.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("hs_candidates.id"))
    decision: Mapped[str] = mapped_column(String(10))  # APPROVE | REJECT
    hs_code: Mapped[str | None] = mapped_column(String(12))
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Any] = mapped_column(JSONType, default=list)
    decided_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by_role: Mapped[str] = mapped_column(String(32))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[Any] = mapped_column(JSONType)  # item description/model/attributes at decision time
