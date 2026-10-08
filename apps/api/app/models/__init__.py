"""ORM models. Import side-effect registers every table on Base.metadata."""

from app.models.assessment import Assessment  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401
from app.models.case import CustomsCase  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.draft import DeclarationDraft  # noqa: F401
from app.models.extraction import CaseField, ExtractedField  # noqa: F401
from app.models.goods import ClassificationDecision, GoodsItem, HsCandidate  # noqa: F401
from app.models.identity import Customer, Supplier, Tenant, User  # noqa: F401
from app.models.issue import Issue  # noqa: F401
from app.models.knowledge import HsRule, KnowledgeDataset  # noqa: F401
