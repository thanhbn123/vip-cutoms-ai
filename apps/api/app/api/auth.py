import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.api.schemas import LoginIn, PasswordChangeIn, PasswordResetIn, TokenOut, UserCreate, UserOut, UserUpdate
from app.core.ratelimit import login_limiters
from app.core.rbac import ROLE_PERMISSIONS, Perm, Role
from app.core.security import hash_password, issue_token, verify_password
from app.db import get_db
from app.models.identity import Tenant, User
from app.services import audit

router = APIRouter(tags=["auth"])
log = logging.getLogger("vip.auth")
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind the stack's own Caddy, so request.client is the real peer there.
    return request.client.host if request.client else "unknown"


def _throttled(retry_after: int) -> JSONResponse:
    return JSONResponse(status_code=429, headers={"Retry-After": str(retry_after)},
                        content={"detail": {"code": "TOO_MANY_ATTEMPTS", "message": "too many failed login attempts; try again later",
                                            "details": {"retry_after_seconds": retry_after}}})


def _candidates(db: Session, email: str, tenant_code: str | None) -> list[User]:
    """Active accounts matching the e-mail, optionally narrowed to one tenant (by code, case-insensitive).

    An unknown tenant code yields no candidate and therefore the same generic 401 as a wrong password (no enumeration).
    """
    stmt = select(User).where(User.email == email, User.is_active.is_(True))
    if tenant_code is not None:
        stmt = stmt.join(Tenant, Tenant.id == User.tenant_id).where(func.upper(Tenant.code) == tenant_code.strip().upper())
    return list(db.execute(stmt).scalars().all())


@router.post("/auth/login", response_model=TokenOut, responses={401: {"description": "invalid credentials or tenant required"},
                                                                  429: {"description": "throttled"}})
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    lims = login_limiters()
    email = body.email.lower()
    ip = _client_ip(request)
    # Throttle keys are tenant-agnostic on purpose: naming a tenant must not grant a fresh budget of attempts.
    dims = (("pair", lims.pair, f"{ip}|{email}"), ("email", lims.email, email), ("ip", lims.ip, ip))
    for kind, lim, key in dims:  # refused BEFORE any password work (G18D)
        v = lim.check(key)
        if not v.allowed:
            log.warning("login_throttled dimension=%s retry_after=%d", kind, v.retry_after)
            return _throttled(v.retry_after)
    candidates = _candidates(db, email, body.tenant)
    # G18F: the password is checked against every active account holding this e-mail (bounded by the number of tenants),
    # so an unauthenticated caller learns nothing about which tenants know the address.
    matched = [u for u in candidates if verify_password(body.password, u.password_hash)]
    if not candidates:
        verify_password(body.password, _DUMMY_HASH)  # keep timing comparable for unknown e-mails
    if len(matched) != 1:
        worst, locked = 0, []
        for kind, lim, key in dims:
            r = lim.record_failure(key)
            if r.locked_now:
                locked.append(kind)
                worst = max(worst, r.retry_after)
        if locked:
            log.warning("login_locked dimensions=%s", ",".join(locked))
            # A known account entering the locked state is a security transition → audit (G18E). The pair/e-mail keys are
            # tenant-agnostic, so every account holding the e-mail is affected — audit all of them even when the attempts
            # named a wrong tenant code (G18F-2).
            affected = candidates if body.tenant is None else _candidates(db, email, None)
            for u in affected:
                audit.record(db, tenant_id=u.tenant_id, actor=audit.Actor.system(), action="auth.login_locked", entity_type="user",
                             entity_id=u.id, after={"dimensions": locked, "retry_after_seconds": worst, "tenant_code_given": body.tenant is not None},
                             reason="repeated failed login attempts")
            if affected:
                db.commit()
            return _throttled(worst)
        if len(matched) > 1:
            # Only reachable with a password valid in ≥2 tenants, i.e. by the account holder: asking for the tenant code
            # discloses nothing to a guesser. Counted as a failed attempt above so it cannot be used to probe either.
            raise HTTPException(status_code=401, detail={"code": "TENANT_REQUIRED",
                                                         "message": "this e-mail is used in several tenants; provide the tenant code",
                                                         "details": {"tenants": sorted(u.tenant_code or "" for u in matched)}})
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "invalid email, tenant or password"})
    user = matched[0]
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
    # Scoped to the admin's own tenant (G18F): the same e-mail in another tenant is neither visible nor a conflict.
    if db.execute(select(User).where(User.tenant_id == admin.tenant_id, User.email == body.email.lower())).scalar_one_or_none():
        raise HTTPException(status_code=409, detail={"code": "DUPLICATE", "message": "email already exists in this tenant"})
    u = User(tenant_id=admin.tenant_id, email=body.email.lower(), full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action="user.created", entity_type="user",
                 entity_id=u.id, after={"email": u.email, "role": u.role})
    db.commit()
    return u


def _target_user(db: Session, admin: User, user_id: uuid.UUID) -> User:
    """A user of the admin's own tenant, locked for update. Other tenants' users look non-existent (no leak)."""
    u = db.execute(select(User).where(User.id == user_id, User.tenant_id == admin.tenant_id).with_for_update(of=User)).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "user not found"})
    return u


def _other_active_admins(db: Session, u: User) -> int:
    return db.execute(select(func.count()).select_from(User).where(User.tenant_id == u.tenant_id, User.id != u.id, User.role == Role.ADMIN.value,
                                                                   User.is_active.is_(True))).scalar_one()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, admin: User = Depends(require(Perm.USER_MANAGE)), db: Session = Depends(get_db)):
    """G18G: rename, change role, deactivate/reactivate — inside the admin's tenant, audited, never self-locking."""
    u = _target_user(db, admin, user_id)
    if body.full_name is None and body.role is None and body.is_active is None:
        raise HTTPException(status_code=422, detail={"code": "NO_CHANGE", "message": "nothing to update"})
    if u.id == admin.id and (body.is_active is False or (body.role is not None and body.role != u.role)):
        raise HTTPException(status_code=409, detail={"code": "SELF_CHANGE_FORBIDDEN", "message": "an admin cannot deactivate or re-role their own account"})
    loses_admin = u.role == Role.ADMIN.value and u.is_active and (body.is_active is False or (body.role is not None and body.role != Role.ADMIN.value))
    if loses_admin and _other_active_admins(db, u) == 0:
        raise HTTPException(status_code=409, detail={"code": "LAST_ADMIN", "message": "the tenant must keep at least one active ADMIN"})
    before = {"full_name": u.full_name, "role": u.role, "is_active": u.is_active}
    if body.full_name is not None:
        u.full_name = body.full_name
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    after = {"full_name": u.full_name, "role": u.role, "is_active": u.is_active}
    if before == after:
        raise HTTPException(status_code=422, detail={"code": "NO_CHANGE", "message": "nothing to update"})
    action = "user.updated"
    if before["is_active"] and not after["is_active"]:
        action = "user.deactivated"
    elif not before["is_active"] and after["is_active"]:
        action = "user.reactivated"
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action=action, entity_type="user", entity_id=u.id,
                 before=before, after=after, reason=body.reason)
    db.commit()
    db.refresh(u)
    return u


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(user_id: uuid.UUID, body: PasswordResetIn, admin: User = Depends(require(Perm.USER_MANAGE)), db: Session = Depends(get_db)):
    """G18G: ADMIN sets a new password for a colleague of the same tenant; all of that user's tokens become void."""
    u = _target_user(db, admin, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=409, detail={"code": "SELF_CHANGE_FORBIDDEN", "message": "use /auth/change-password for your own account"})
    u.password_hash = hash_password(body.password)
    u.password_changed_at = datetime.now(UTC)
    audit.record(db, tenant_id=admin.tenant_id, actor=audit.Actor.user(admin), action="user.password_reset", entity_type="user", entity_id=u.id,
                 after={"by": str(admin.id)}, reason=body.reason)
    db.commit()
    return None


@router.post("/auth/change-password", response_model=TokenOut)
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """G18G: self-service password change; the current password is required and wrong guesses count against the login throttle.
    Returns a fresh token because every token issued before the change is void."""
    lims = login_limiters()
    ip = _client_ip(request)
    keys = (("pair", lims.pair, f"{ip}|{user.email}"), ("email", lims.email, user.email))
    for _kind, lim, key in keys:
        v = lim.check(key)
        if not v.allowed:
            return _throttled(v.retry_after)
    if not verify_password(body.current_password, user.password_hash):
        worst = max((lim.record_failure(key).retry_after for _k, lim, key in keys), default=0)
        if any(not lim.check(key).allowed for _k, lim, key in keys):
            return _throttled(worst)
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "current password is wrong"})
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail={"code": "SAME_PASSWORD", "message": "the new password must differ from the current one"})
    locked = db.execute(select(User).where(User.id == user.id).with_for_update(of=User)).scalar_one()
    locked.password_hash = hash_password(body.new_password)
    locked.password_changed_at = datetime.now(UTC)
    audit.record(db, tenant_id=user.tenant_id, actor=audit.Actor.user(user), action="auth.password_changed", entity_type="user", entity_id=user.id,
                 reason="self-service password change")
    db.commit()
    for _k, lim, key in keys:
        lim.record_success(key)
    db.refresh(locked)
    return TokenOut(access_token=issue_token(str(locked.id), str(locked.tenant_id), locked.role), user=UserOut.model_validate(locked))
