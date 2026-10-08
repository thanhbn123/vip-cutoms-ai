import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class CustomsCase(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_no"),)
    case_no: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(10), default="IMPORT")  # IMPORT | EXPORT
    declaration_type: Mapped[str] = mapped_column(String(10))  # loại hình, e.g. A11
    customs_office: Mapped[str | None] = mapped_column(String(100))
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL")
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(String(2000))
    row_version: Mapped[int] = mapped_column(Integer, default=1)
