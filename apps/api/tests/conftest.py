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
            conn.execute(text("SET session_replication_role = replica"))  # bypass append-only trigger for test cleanup
            conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
            conn.execute(text("SET session_replication_role = origin"))


@pytest.fixture
def client():
    from app.main import create_app

    return TestClient(create_app())
