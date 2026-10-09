import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.core.config import get_settings
from app.core.errors import not_found
from app.core.http import content_disposition
from app.core.rbac import Perm
from app.db import get_db
from app.models.document import Document
from app.models.identity import User
from app.storage.base import get_storage

router = APIRouter(tags=["documents"])

from app.services.documents import ALLOWED_EXT, DOC_TYPES, ingest, safe_filename  # noqa: E402


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
    filename = safe_filename(file.filename or "")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=422, detail={"code": "INVALID_FILE_TYPE", "message": f"extension {ext or '(none)'} not allowed"})
    data = await file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail={"code": "FILE_TOO_LARGE", "message": "file exceeds upload limit"})
    if not data:
        raise HTTPException(status_code=422, detail={"code": "EMPTY_FILE", "message": "file is empty"})

    case = load_case(db, user, case_id, for_update=True)
    doc = ingest(db, case, user, doc_type, filename, file.content_type or "application/octet-stream", data,
                 meta={k: v for k, v in {"document_no": document_no, "issuer": issuer}.items() if v})
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
                    headers={"Content-Disposition": content_disposition(doc.filename), "Cache-Control": "private, no-store"})
