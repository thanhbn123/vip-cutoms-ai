"""ORM models. Import side-effect registers every table on Base.metadata."""

from app.models.audit import AuditEvent  # noqa: F401
from app.models.case import CustomsCase  # noqa: F401
from app.models.identity import Customer, Supplier, Tenant, User  # noqa: F401
