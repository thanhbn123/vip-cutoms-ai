import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdMixin, TenantMixin, TimestampMixin


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))


class User(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "users"
    # E-mail is unique per tenant (G18F, D-042): the same person may hold accounts in several tenants and a tenant
    # ADMIN can no longer learn whether an e-mail exists elsewhere. Login disambiguates by tenant code.
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))  # OPERATOR | REVIEWER | SENIOR_REVIEWER | ADMIN
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # G18G: set on every password change/reset; bearer tokens issued before it are refused (stateless revocation).
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant: Mapped[Tenant] = relationship(Tenant, lazy="joined")

    @property
    def tenant_code(self) -> str | None:
        return self.tenant.code if self.tenant is not None else None


class Customer(IdMixin, TimestampMixin, TenantMixin, Base):
    """Importer / customer of the brokerage (Vietnamese side)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    tax_code: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(500))


class Supplier(IdMixin, TimestampMixin, TenantMixin, Base):
    """Exporter / supplier (foreign side)."""

    __tablename__ = "suppliers"
    name: Mapped[str] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(String(500))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"))
