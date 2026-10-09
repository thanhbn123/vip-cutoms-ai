"""B-07: deactivate the acceptance demo users (*@demo.local) without deleting them (G18).

Why deactivate, not delete: audit events, reviewer decisions and case ownership reference
users.id. Deleting the rows would orphan the audit trail (product rule #9) or require a cascade
that destroys history. Setting is_active=false makes login impossible (app/api/auth.py checks
is_active before the password) while every historical action stays attributable.

Safety:
  * targets ONLY e-mails matching ^[a-z0-9._-]+@demo\\.local$ — anything else aborts before any write
  * default is INVENTORY (read-only); writes need --execute AND DEACTIVATE_CONFIRM=demo.local
  * idempotent: already-inactive users are reported and skipped, no duplicate audit events
  * one audit event per deactivated user (SYSTEM actor, action user.deactivated, reason recorded)
  * --verify checks that every demo user is inactive and that at least one non-demo ADMIN remains active in each
    affected tenant (so nobody locks themselves out), exit 1 otherwise

Usage (inside the api container or with the api venv):
    python scripts/deactivate_demo_users.py                       # inventory
    DEACTIVATE_CONFIRM=demo.local python scripts/deactivate_demo_users.py --execute --reason "G18 B-07 after staging acceptance"
    python scripts/deactivate_demo_users.py --verify
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import get_sessionmaker  # noqa: E402
from app.models.identity import Tenant, User  # noqa: E402
from app.services import audit  # noqa: E402

DEMO_EMAIL = re.compile(r"^[a-z0-9._-]+@demo\.local$")
CONFIRM_TOKEN = "demo.local"


def is_demo_email(email: str) -> bool:
    return bool(DEMO_EMAIL.match(email.strip().lower()))


def demo_users(db: Session) -> list[User]:
    users = db.execute(select(User).where(User.email.ilike("%@demo.local")).order_by(User.email)).scalars().all()
    bad = [u.email for u in users if not is_demo_email(u.email)]
    if bad:  # defence in depth: the LIKE and the regex must agree, otherwise refuse to touch anything
        raise SystemExit(f"refusing: non-demo e-mail matched the demo filter: {bad}")
    return list(users)


def inventory(db: Session) -> list[dict]:
    rows = []
    for u in demo_users(db):
        tenant = db.get(Tenant, u.tenant_id)
        rows.append({"email": u.email, "role": u.role, "tenant": tenant.code if tenant else str(u.tenant_id), "is_active": u.is_active})
    return rows


def deactivate(db: Session, *, reason: str) -> dict[str, list[str]]:
    done, skipped = [], []
    for u in demo_users(db):
        if not u.is_active:
            skipped.append(u.email)
            continue
        u.is_active = False
        audit.record(db, tenant_id=u.tenant_id, actor=audit.Actor.system(), action="user.deactivated", entity_type="user", entity_id=u.id,
                     before={"is_active": True}, after={"is_active": False, "email": u.email, "role": u.role}, reason=reason)
        done.append(u.email)
    db.commit()
    return {"deactivated": done, "already_inactive": skipped}


def verify(db: Session) -> list[str]:
    """Problems list; empty = OK."""
    problems = []
    users = demo_users(db)
    for u in users:
        if u.is_active:
            problems.append(f"{u.email} still active")
    for tid in {u.tenant_id for u in users}:
        admins = db.execute(select(User).where(User.tenant_id == tid, User.role == "ADMIN", User.is_active.is_(True))).scalars().all()
        if not any(not is_demo_email(a.email) for a in admins):
            tenant = db.get(Tenant, tid)
            problems.append(f"tenant {tenant.code if tenant else tid}: no active non-demo ADMIN remains (create one before relying on this tenant)")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--execute", action="store_true", help="deactivate (requires DEACTIVATE_CONFIRM=demo.local)")
    ap.add_argument("--verify", action="store_true", help="exit 1 unless every demo user is inactive")
    ap.add_argument("--reason", default="B-07: demo acceptance accounts deactivated after staging acceptance")
    args = ap.parse_args(argv)
    db = get_sessionmaker()()
    try:
        inv = inventory(db)
        print(f"demo users: {len(inv)}")
        for r in inv:
            print(f"  {r['email']:<28} role={r['role']:<16} tenant={r['tenant']:<8} active={r['is_active']}")
        if args.execute:
            if os.environ.get("DEACTIVATE_CONFIRM") != CONFIRM_TOKEN:
                print(f"refusing to execute: set DEACTIVATE_CONFIRM={CONFIRM_TOKEN}", file=sys.stderr)
                return 2
            out = deactivate(db, reason=args.reason)
            print(f"deactivated: {out['deactivated'] or 'none'}; already inactive: {out['already_inactive'] or 'none'}")
        if args.verify or args.execute:
            problems = verify(db)
            if problems:
                print("VERIFY: FAIL")
                for p in problems:
                    print("  - " + p)
                return 1
            print("VERIFY: OK — all demo users inactive, a non-demo ADMIN remains active")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
