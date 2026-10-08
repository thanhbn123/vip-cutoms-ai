"""Dev/staging-acceptance seed: demo tenant, one user per role, master data, demo knowledge datasets and the V12 reference case.

Refuses to run outside development/test. Password must be supplied (env SEED_DEMO_PASSWORD) — nothing secret lives in the repo.
Usage: SEED_DEMO_PASSWORD='...' python scripts/seed_demo.py [--with-case]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.models.identity import Customer, Supplier, Tenant, User  # noqa: E402
from app.services.knowledge import seed_demo  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "minh_phat"
USERS = [("operator@demo.local", "Operator Demo", "OPERATOR"), ("reviewer@demo.local", "Reviewer Demo", "REVIEWER"),
         ("senior@demo.local", "Senior Reviewer Demo", "SENIOR_REVIEWER"), ("admin@demo.local", "Admin Demo", "ADMIN")]


def main() -> None:
    s = get_settings()
    if not s.is_development:
        raise SystemExit("seed_demo refuses to run outside development/test")
    pw = os.environ.get("SEED_DEMO_PASSWORD")
    if not pw or len(pw) < 10:
        raise SystemExit("set SEED_DEMO_PASSWORD (>= 10 chars); demo credentials are never stored in the repo")
    db = get_sessionmaker()()
    tenant = db.execute(select(Tenant).where(Tenant.code == "DEMO")).scalar()
    if not tenant:
        tenant = Tenant(code="DEMO", name="VIP Customs Demo Tenant")
        db.add(tenant)
        db.flush()
    users = {}
    for email, name, role in USERS:
        u = db.execute(select(User).where(User.email == email)).scalar()
        if not u:
            u = User(tenant_id=tenant.id, email=email, full_name=name, role=role, password_hash=hash_password(pw))
            db.add(u)
            db.flush()
        users[role] = u
    customer = db.execute(select(Customer).where(Customer.tenant_id == tenant.id, Customer.code == "MINHPHAT")).scalar()
    if not customer:
        customer = Customer(tenant_id=tenant.id, code="MINHPHAT", name="CÔNG TY TNHH MINH PHÁT", tax_code="0100000000 (demo)", address="Bắc Ninh, Việt Nam")
        db.add(customer)
        db.flush()
    supplier = db.execute(select(Supplier).where(Supplier.tenant_id == tenant.id, Supplier.name.like("GUANGZHOU ABC%"))).scalar()
    if not supplier:
        supplier = Supplier(tenant_id=tenant.id, name="GUANGZHOU ABC TRADING CO., LTD.", country="CN", address="No. 88 Huangpu Road, Guangzhou", customer_id=customer.id)
        db.add(supplier)
        db.flush()
    created = seed_demo(db)
    db.commit()
    print(f"tenant DEMO ready; users: {', '.join(e for e, _, _ in USERS)}; datasets seeded: {created or 'already present'}")

    if "--with-case" in sys.argv:
        from app.api.pipeline import run_pipeline
        from app.models.case import CustomsCase
        from app.services import audit
        from app.services.documents import ingest
        from app.services.workflow import CaseStatus

        op = users["OPERATOR"]
        case = CustomsCase(tenant_id=tenant.id, case_no="VIP-HQ-261008-001", direction="IMPORT", declaration_type="A11", customs_office="Bắc Ninh",
                           customer_id=customer.id, supplier_id=supplier.id, status=CaseStatus.NEW.value, priority="HIGH", owner_id=op.id,
                           reviewer_id=users["REVIEWER"].id, notes="DEMO reference case (fixture documents)")
        if db.execute(select(CustomsCase).where(CustomsCase.tenant_id == tenant.id, CustomsCase.case_no == case.case_no)).scalar():
            print("demo case already exists")
            return
        db.add(case)
        db.flush()
        audit.record(db, tenant_id=tenant.id, actor=audit.Actor.user(op), action="case.created", entity_type="case", entity_id=case.id, case_id=case.id,
                     after={"case_no": case.case_no, "seed": True})
        for doc_type, fn in (("INVOICE", "invoice.txt"), ("PACKING_LIST", "packing_list.txt"), ("BILL_OF_LADING", "bill_of_lading.txt"), ("CO", "form_e.txt")):
            ingest(db, case, op, doc_type, fn, "text/plain", (FIXTURES / fn).read_bytes())
        out = run_pipeline(db, case, op)
        db.commit()
        print(f"demo case {case.case_no}: {out}")


if __name__ == "__main__":
    main()
