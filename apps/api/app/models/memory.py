import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import IdMixin, TenantMixin


class ProductMemory(IdMixin, TenantMixin, Base):
    """Enterprise memory built ONLY from reviewer-approved classification decisions (AI_RULES: historical learning)."""

    __tablename__ = "product_memory"
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"))
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"))
    case_no: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("goods_items.id"))
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("classification_decisions.id"), unique=True)
    model: Mapped[str | None] = mapped_column(String(120), index=True)
    model_norm: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text)
    description_vn: Mapped[str | None] = mapped_column(Text)
    hs_code: Mapped[str] = mapped_column(String(12))
    heading: Mapped[str] = mapped_column(String(4))
    unit_price: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(3))
    co_form: Mapped[str | None] = mapped_column(String(10))
    approved_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_by_role: Mapped[str] = mapped_column(String(32))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(20), default="UNKNOWN")  # UNKNOWN | CLEARED | CONSULTATION | DISPUTE | AMENDED
    reusable: Mapped[bool] = mapped_column(Boolean, default=True)  # False → reference only, never auto-copied
    outcome_reason: Mapped[str | None] = mapped_column(Text)
    outcome_set_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
