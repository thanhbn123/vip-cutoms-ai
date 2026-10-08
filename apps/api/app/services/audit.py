"""Immutable audit trail: actor / before / after / reason / evidence / timestamp, hash-chained per tenant."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.jsonsafe import to_jsonable
from app.models.audit import AuditEvent
from app.models.base import utcnow


class Actor:
    def __init__(self, type_: str, id_: uuid.UUID | None = None, role: str | None = None):
        self.type = type_
        self.id = id_
        self.role = role

    @classmethod
    def user(cls, user) -> Actor:
        return cls("USER", user.id, user.role)

    @classmethod
    def system(cls) -> Actor:
        return cls("SYSTEM")

    @classmethod
    def ai(cls) -> Actor:
        return cls("AI")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    case_id: uuid.UUID | None = None,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
    evidence: Any = None,
) -> AuditEvent:
    # Serialise chain writers per tenant inside the current transaction.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:t))"), {"t": str(tenant_id)})
    prev = db.execute(
        select(AuditEvent.hash).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.created_at.desc()).limit(1)
    ).scalar()
    ev = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        case_id=case_id,
        actor_id=actor.id,
        actor_type=actor.type,
        actor_role=actor.role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=to_jsonable(before),
        after=to_jsonable(after),
        reason=reason,
        evidence=to_jsonable(evidence),
        created_at=utcnow(),
        prev_hash=prev,
    )
    ev.hash = _digest(
        {
            "id": str(ev.id), "tenant": str(tenant_id), "case": str(case_id) if case_id else None,
            "actor": [actor.type, str(actor.id) if actor.id else None, actor.role], "action": action,
            "entity": [entity_type, ev.entity_id], "before": ev.before, "after": ev.after, "reason": reason,
            "evidence": ev.evidence, "ts": ev.created_at.isoformat(), "prev": prev,
        }
    )
    db.add(ev)
    db.flush()
    return ev


def verify_chain(db: Session, tenant_id: uuid.UUID) -> bool:
    events = db.execute(
        select(AuditEvent).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.created_at)
    ).scalars().all()
    prev = None
    for ev in events:
        if ev.prev_hash != prev:
            return False
        expected = _digest(
            {
                "id": str(ev.id), "tenant": str(tenant_id), "case": str(ev.case_id) if ev.case_id else None,
                "actor": [ev.actor_type, str(ev.actor_id) if ev.actor_id else None, ev.actor_role], "action": ev.action,
                "entity": [ev.entity_type, ev.entity_id], "before": ev.before, "after": ev.after, "reason": ev.reason,
                "evidence": ev.evidence, "ts": ev.created_at.isoformat(), "prev": ev.prev_hash,
            }
        )
        if expected != ev.hash:
            return False
        prev = ev.hash
    return True
