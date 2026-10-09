import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.api.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.core.ratelimit import login_limiters
from app.core.rbac import ROLE_PERMISSIONS, Perm, Role
from app.core.security import hash_password, issue_token, verify_password
from app.db import get_db
from app.models.identity import User
from app.services import audit

router = APIRouter(tags=["auth"])
log = logging.getLogger("vip.auth")


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind the stack's own Caddy, so request.client is the real peer there.
    return request.client.host if request.client else "unknown"


def _throttled(retry_after: int) -> JSONResponse:
    return JSONResponse(status_code=429, headers={"Retry-After": str(retry_after)},
                        content={"detail": {"code": "TOO_MANY_ATTEMPTS", "message": "too many failed login attempts; try again later",
                                            "details": {"retry_after_seconds": retry_after}}})


@router.post("/auth/login", response_model=TokenOut, responses={429: {"description": "throttled"}})
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    lims = login_limiters()
    email = body.email.lower()
    ip = _client_ip(request)
    dims = (("pair", lims.pair, f"{ip}|{email}"), ("email", lims.email, email), ("ip", lims.ip, ip))
    for kind, lim, key in dims:  # refused BEFORE any password work (G18D)
        v = lim.check(key)
        if not v.allowed:
            log.warning("login_throttled dimension=%s retry_after=%d", kind, v.retry_after)
            return _throttled(v.retry_after)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        worst, locked = 0, []
        for kind, lim, key in dims:
            r = lim.record_failure(key)
            if r.locked_now:
                locked.append(kind)
                worst = max(worst, r.retry_after)
        if locked:
            log.warning("login_locked dimensions=%s", ",".join(locked))
            if user is not None:  # a known account entering the locked state is a security transition → audit (G18E)
                audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.system(), action="auth.login_locked", entity_type="user",
                             entity_id=user.id, after={"dimensions": locked, "retry_after_seconds": worst},
                             reason="repeated failed login attempts")
                db.commit()
            return _throttled(worst)
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "invalid email or password"})
    lims.pair.record_success(f"{ip}|{email}")
    lims.email.record_success(email)
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
