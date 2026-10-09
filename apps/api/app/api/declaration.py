import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import load_case, require
from app.core.rbac import Perm
from app.db import get_db
from app.models.identity import User
from app.services import declaration, release

router = APIRouter(tags=["declaration"])


@router.get("/cases/{case_id}/declaration")
def get_declaration(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    return declaration.build(db, load_case(db, user, case_id))


@router.get("/cases/{case_id}/release-gate")
def release_gate(case_id: uuid.UUID, user: User = Depends(require(Perm.CASE_READ)), db: Session = Depends(get_db)):
    return release.gate(db, load_case(db, user, case_id))
