"""Document ingestion shared by the upload API and the dev seed script."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.case import CustomsCase
from app.models.document import Document
from app.models.identity import User
from app.services import audit
from app.services.workflow import CaseStatus, transition
from app.storage.base import get_storage, sha256

DOC_TYPES = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO", "CONTRACT", "CATALOGUE", "OTHER"}
VERSIONED_TYPES = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO", "CONTRACT"}  # one current version per case
ALLOWED_EXT = {".pdf", ".txt", ".json", ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def safe_filename(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1].strip()
    return "".join(ch for ch in base if ch.isprintable())[:255] or "upload.bin"


def ingest(db: Session, case: CustomsCase, user: User, doc_type: str, filename: str, content_type: str, data: bytes,
           meta: dict | None = None) -> Document:
    filename = safe_filename(filename)
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    digest = sha256(data)
    dup = db.execute(select(Document).where(Document.case_id == case.id, Document.doc_type == doc_type, Document.sha256 == digest,
                                            Document.is_current.is_(True))).scalar()
    if dup:
        raise DomainError("DUPLICATE_DOCUMENT", "identical file already uploaded for this document type", details={"document_id": str(dup.id)})
    previous, version = None, 1
    if doc_type in VERSIONED_TYPES:
        previous = db.execute(select(Document).where(Document.case_id == case.id, Document.doc_type == doc_type, Document.is_current.is_(True))).scalar()
        if previous:
            version = previous.version + 1
            previous.is_current = False
            previous.status = "SUPERSEDED"
    doc_id = uuid.uuid4()
    key = f"{case.tenant_id}/{case.id}/{doc_id}{ext}"
    storage = get_storage()
    storage.put(key, data)
    doc = Document(id=doc_id, tenant_id=case.tenant_id, case_id=case.id, doc_type=doc_type, filename=filename, content_type=content_type,
                   size_bytes=len(data), sha256=digest, storage_backend=storage.name, storage_key=key, version=version, is_current=True,
                   supersedes_id=previous.id if previous else None, status="UPLOADED", uploaded_by=user.id, meta=meta or {}, parse_warnings=[])
    db.add(doc)
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="document.uploaded", entity_type="document", entity_id=doc.id,
                 case_id=case.id, before={"superseded_id": str(previous.id)} if previous else None,
                 after={"doc_type": doc_type, "filename": filename, "sha256": digest, "version": version})
    transition(db, case, CaseStatus.DOCUMENTS_UPLOADED, audit.Actor.user(user), reason=f"{doc_type} v{version} uploaded")
    return doc
