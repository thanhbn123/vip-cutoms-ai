import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://vip_customs:vip_customs@localhost:5432/vip_customs_test"
)
os.environ.setdefault("APP_SECRET_KEY", "test-only-secret-key-not-for-any-real-environment-000")
os.environ.setdefault("AI_PROVIDER", "mock")

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import Base, get_engine  # noqa: E402

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def migrated_db(tmp_path_factory):
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path_factory.mktemp("uploads"))
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(API_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
    command.upgrade(cfg, "head")
    yield engine


@pytest.fixture(autouse=True)
def clean_tables(migrated_db):
    yield
    tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
    if tables:
        with migrated_db.begin() as conn:
            # A test that leaks a session with an open transaction would block this ALTER forever; fail loudly instead (G18C).
            conn.execute(text("SET LOCAL lock_timeout = '10s'"))
            # Test-only cleanup: the table owner temporarily disables the append-only trigger.
            conn.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
            conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
            conn.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))


@pytest.fixture
def client():
    from app.main import create_app

    return TestClient(create_app())


class World:
    """Two isolated tenants with one user per role, a customer and a supplier."""

    def __init__(self, client):
        from app.core.security import hash_password, issue_token
        from app.db import get_sessionmaker
        from app.models.identity import Customer, Supplier, Tenant, User

        self.client = client
        db = get_sessionmaker()()
        pw = hash_password("correct-horse-battery")
        self.tokens = {}
        self.users = {}
        for code in ("T1", "T2"):
            t = Tenant(code=code, name=f"Tenant {code}")
            db.add(t)
            db.flush()
            for role in ("OPERATOR", "REVIEWER", "SENIOR_REVIEWER", "ADMIN"):
                u = User(tenant_id=t.id, email=f"{role.lower()}@{code.lower()}.test", full_name=f"{role} {code}", role=role,
                         password_hash=pw)
                db.add(u)
                db.flush()
                self.users[(code, role)] = u
                self.tokens[(code, role)] = issue_token(str(u.id), str(t.id), role)
            c = Customer(tenant_id=t.id, code=f"MP-{code}", name="CÔNG TY TNHH MINH PHÁT", tax_code="0100000000")
            db.add(c)
            db.flush()
            s = Supplier(tenant_id=t.id, name="GUANGZHOU ABC TRADING CO., LTD.", country="CN", customer_id=c.id)
            db.add(s)
            db.flush()
            setattr(self, f"customer_{code}", c)
            setattr(self, f"supplier_{code}", s)
            setattr(self, f"tenant_{code}", t)
        db.commit()
        db.close()

    def h(self, role="OPERATOR", tenant="T1"):
        return {"Authorization": f"Bearer {self.tokens[(tenant, role)]}"}

    def create_case(self, tenant="T1", role="OPERATOR", **kw):
        body = {"customer_id": str(getattr(self, f"customer_{tenant}").id),
                "supplier_id": str(getattr(self, f"supplier_{tenant}").id),
                "declaration_type": "A11", "customs_office": "Bắc Ninh"} | kw
        r = self.client.post("/api/v1/cases", json=body, headers=self.h(role, tenant))
        assert r.status_code == 201, r.text
        return r.json()


@pytest.fixture
def world(client):
    return World(client)


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "minh_phat")
FIXTURE_FILES = {
    "INVOICE": "invoice.txt",
    "PACKING_LIST": "packing_list.txt",
    "BILL_OF_LADING": "bill_of_lading.txt",
    "CO": "form_e.txt",
}


def upload(client, headers, case_id, doc_type, filename, content=None):
    if content is None:
        with open(os.path.join(FIXTURES, filename), "rb") as fh:
            content = fh.read()
    return client.post(f"/api/v1/cases/{case_id}/documents", data={"doc_type": doc_type},
                       files={"file": (filename, content, "text/plain")}, headers=headers)
