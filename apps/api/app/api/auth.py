from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.api.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.core.rbac import ROLE_PERMISSIONS, Perm, Role
from app.core.security import hash_password, issue_token, verify_password
from app.db import get_db
from app.models.identity import User
from app.services import audit

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "invalid email or password"})
    return TokenOut(access_token=issue_token(str(user.id), str(user.tenant_id), user.role), user=UserOut.model_validate(user))


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"user": UserOut.model_validate(user), "permissions": sorted(p.value for p in ROLE_PERMISSIONS[Role(user.role)])}


@router.get("/users", response_model=list[UserOut])
def list_users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Everyone in the tenant may see colleagues (needed for reviewer assignment).
    return db.execute(select(User).where(User.tenant_id == user.tenant_id).order_by(User.email)).scalars().all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, admin: User = Depends(require(Perm.USER_MANAGE)), db: Session = Depends(get_db)):
    if db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE", "message": "email already exists"})
    u = User(tenant_id=admin.tenant_id, email=body.email.lower(), full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action="user.created", entity_type="user",
                 entity_id=u.id, after={"email": u.email, "role": u.role})
    db.commit()
    return u
