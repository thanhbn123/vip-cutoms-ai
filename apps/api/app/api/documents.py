import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.core.config import get_settings
from app.core.errors import DomainError, not_found
from app.core.rbac import Perm
from app.db import get_db
from app.models.document import Document
from app.models.identity import User
from app.services import audit
from app.services.workflow import CaseStatus, transition
from app.storage.base import get_storage, sha256

router = APIRouter(tags=["documents"])

DOC_TYPES = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO", "CONTRACT", "CATALOGUE", "OTHER"}
# One current version per case for these; CATALOGUE/OTHER are additive.
VERSIONED_TYPES = {"INVOICE", "PACKING_LIST", "BILL_OF_LADING", "CO", "CONTRACT"}
ALLOWED_EXT = {".pdf", ".txt", ".json", ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class DocumentOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    doc_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    version: int
    is_current: bool
    supersedes_id: uuid.UUID | None
    status: str
    uploaded_by: uuid.UUID
    meta: dict
    parse_provider: str | None
    parse_provider_version: str | None
    parse_confidence: float | None
    parse_warnings: list
    created_at: object

    model_config = {"from_attributes": True}


def _safe_filename(name: str) -> str:
    base = name.replace("\\", "/").split("/")[-1].strip()
    return "".join(ch for ch in base if ch.isprintable())[:255] or "upload.bin"


@router.post("/cases/{case_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    case_id: uuid.UUID,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    document_no: str | None = Form(default=None, max_length=100),
    issuer: str | None = Form(default=None, max_length=255),
    user: User = Depends(require(Perm.DOC_UPLOAD)),
    db: Session = Depends(get_db),
):
    doc_type = doc_type.upper()
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=422, detail={"code": "INVALID_DOC_TYPE", "message": f"doc_type must be one of {sorted(DOC_TYPES)}"})
    filename = _safe_filename(file.filename or "")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=422, detail={"code": "INVALID_FILE_TYPE", "message": f"extension {ext or '(none)'} not allowed"})
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail={"code": "FILE_TOO_LARGE", "message": "file exceeds upload limit"})
    if not data:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_FILE", "message": "file is empty"})

    case = load_case(db, user, case_id, for_update=True)
    digest = sha256(data)
    dup = db.execute(select(Document).where(Document.case_id == case.id, Document.doc_type == doc_type,
                                            Document.sha256 == digest, Document.is_current.is_(True))).scalar()
    if dup:
        raise DomainError("DUPLICATE_DOCUMENT", "identical file already uploaded for this document type", details={"document_id": str(dup.id)})

    previous = None
    version = 1
    if doc_type in VERSIONED_TYPES:
        previous = db.execute(select(Document).where(Document.case_id == case.id, Document.doc_type == doc_type,
                                                     Document.is_current.is_(True))).scalar()
        if previous:
            version = previous.version + 1
            previous.is_current = False
            previous.status = "SUPERSEDED"

    doc_id = uuid.uuid4()
    key = f"{case.tenant_id}/{case.id}/{doc_id}{ext}"
    storage = get_storage()
    storage.put(key, data)
    doc = Document(id=doc_id, tenant_id=case.tenant_id, case_id=case.id, doc_type=doc_type, filename=filename,
                   content_type=file.content_type or "application/octet-stream", size_bytes=len(data), sha256=digest,
                   storage_backend=storage.name, storage_key=key, version=version, is_current=True,
                   supersedes_id=previous.id if previous else None, status="UPLOADED", uploaded_by=user.id,
                   meta={k: v for k, v in {"document_no": document_no, "issuer": issuer}.items() if v}, parse_warnings=[])
    db.add(doc)
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="document.uploaded", entity_type="document",
                 entity_id=doc.id, case_id=case.id, before={"superseded_id": str(previous.id)} if previous else None,
                 after={"doc_type": doc_type, "filename": filename, "sha256": digest, "version": version})
    transition(db, case, CaseStatus.DOCUMENTS_UPLOADED, audit.Actor.user(user), reason=f"{doc_type} v{version} uploaded")
    db.commit()
    return doc


@router.get("/cases/{case_id}/documents", response_model=list[DocumentOut])
def list_documents(case_id: uuid.UUID, include_superseded: bool = False, user: User = Depends(require(Perm.CASE_READ)),
                   db: Session = Depends(get_db)):
    load_case(db, user, case_id)
    stmt = select(Document).where(Document.case_id == case_id, Document.tenant_id == user.tenant_id)
    if not include_superseded:
        stmt = stmt.where(Document.is_current.is_(True))
    return db.execute(stmt.order_by(Document.doc_type, Document.version)).scalars().all()


def load_document(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    doc = db.execute(select(Document).where(Document.id == doc_id, Document.tenant_id == user.tenant_id)).scalar()
    if not doc:
        raise not_found("document")
    return doc


@router.get("/documents/{doc_id}/content")
def download_document(doc_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    doc = load_document(db, user, doc_id)
    data = get_storage().get(doc.storage_key)
    return Response(content=data, media_type=doc.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{doc.filename}"', "Cache-Control": "private, no-store"})
