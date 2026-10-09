import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.rbac import Perm, has_perm
from app.core.security import InvalidToken, decode_token
from app.db import get_db
from app.models.case import CustomsCase
from app.models.identity import User


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "Bearer token required"})
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
        subject = uuid.UUID(payload["sub"])  # a signed token with a non-UUID subject is still just an invalid token (401, not 500)
    except (InvalidToken, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": str(exc)}) from exc
    user = db.get(User, subject)
    if not user or not user.is_active or str(user.tenant_id) != payload.get("tid"):
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "inactive or unknown user"})
    return user


def require(perm: Perm) -> Callable[[User], User]:
    def dep(user: User = Depends(current_user)) -> User:
        if not has_perm(user.role, perm):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"role {user.role} lacks {perm.value}"})
        return user

    return dep


def ensure(user: User, perm: Perm) -> None:
    if not has_perm(user.role, perm):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"role {user.role} lacks {perm.value}"})


def load_case(db: Session, user: User, case_id: uuid.UUID, *, for_update: bool = False) -> CustomsCase:
    """Tenant isolation enforced in the query, not by UI filtering."""
    stmt = select(CustomsCase).where(CustomsCase.id == case_id, CustomsCase.tenant_id == user.tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    case = db.execute(stmt).scalar_one_or_none()
    if case is None:
        raise not_found("case")
    return case
