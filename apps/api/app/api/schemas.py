import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=255)
    role: Literal["OPERATOR", "REVIEWER", "SENIOR_REVIEWER", "ADMIN"]
    password: str = Field(min_length=10, max_length=255)


class CustomerIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    tax_code: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=500)


class CustomerOut(ORM, CustomerIn):
    id: uuid.UUID


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    address: str | None = Field(default=None, max_length=500)
    customer_id: uuid.UUID | None = None


class SupplierOut(ORM, SupplierIn):
    id: uuid.UUID


DECLARATION_TYPES = {"A11", "A12", "A21", "A31", "A41", "E11", "E21", "E31", "B11", "B13", "G11", "G12"}


class CaseCreate(BaseModel):
    customer_id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    direction: Literal["IMPORT", "EXPORT"] = "IMPORT"
    declaration_type: str = Field(min_length=3, max_length=3, description="Mã loại hình (e.g. A11)")
    customs_office: str | None = Field(default=None, max_length=100)
    priority: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    reviewer_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("declaration_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        v = v.upper()
        if v not in DECLARATION_TYPES:
            raise ValueError(f"unknown declaration type {v}")
        return v


class CaseUpdate(BaseModel):
    customs_office: str | None = Field(default=None, max_length=100)
    priority: Literal["LOW", "NORMAL", "HIGH"] | None = None
    reviewer_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CaseOut(ORM):
    id: uuid.UUID
    case_no: str
    direction: str
    declaration_type: str
    customs_office: str | None
    customer_id: uuid.UUID
    supplier_id: uuid.UUID | None
    status: str
    priority: str
    owner_id: uuid.UUID
    reviewer_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AuditOut(ORM):
    id: uuid.UUID
    case_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_type: str
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    before: Any
    after: Any
    reason: str | None
    evidence: Any
    created_at: datetime
    hash: str
    prev_hash: str | None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    evidence: list[str] | None = None
