import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.audit import JSONType
from app.models.base import IdMixin, TenantMixin


class CopilotMessage(IdMixin, TenantMixin, Base):
    __tablename__ = "copilot_messages"
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(5))  # USER | AI
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(30))
    sources: Mapped[Any] = mapped_column(JSONType, default=list)
    reasoning: Mapped[Any] = mapped_column(JSONType, default=list)
    provider: Mapped[str | None] = mapped_column(String(50))
    provider_version: Mapped[str | None] = mapped_column(String(50))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    meta: Mapped[Any] = mapped_column(JSONType, default=dict)  # confidence, recommended_actions, requires_review, dropped_sources
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Proposal(IdMixin, TenantMixin, Base):
    """AI-proposed change. Nothing is applied until a reviewer (not the requester) approves."""

    __tablename__ = "proposals"
    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("cases.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(30))  # ITEM_DESCRIPTION_VN
    target_ref: Mapped[str] = mapped_column(String(80))  # item id
    current_value: Mapped[str | None] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[Any] = mapped_column(JSONType, default=list)
    sources: Mapped[Any] = mapped_column(JSONType, default=list)
    provider: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(10), default="PROPOSED")  # PROPOSED | APPROVED | REJECTED
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
