import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Unit tests need a syntactically valid URL only; integration tests use the real DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/none")
os.environ["ENVIRONMENT"] = "test"
# Hermetic tests: never pick up real credentials from a developer's .env (env vars override the .env file).
for _k in ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET", "OPENROUTER_API_KEY"):
    os.environ[_k] = ""
os.environ["API_TOKEN_VIEWER"] = "test-viewer-token"
os.environ["API_TOKEN_ANALYST"] = "test-analyst-token"
os.environ["API_TOKEN_ADMIN"] = "test-admin-token"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"


def _use_isolated_test_database() -> None:
    """Point tests at `<db>_test` (created and migrated on demand) so they never touch real data."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import SQLAlchemyError

    url = make_url(os.environ["DATABASE_URL"])
    if url.port == 1 or not url.database or url.database.endswith("_test"):
        return  # dummy URL (unit tests only) or already a test database
    test_db = f"{url.database}_test"
    try:
        admin = create_engine(
            url.set(database="postgres"), isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
        )
        with admin.connect() as c:
            if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": test_db}):
                c.execute(text(f'CREATE DATABASE "{test_db}"'))  # name derived from our own config
        admin.dispose()
    except SQLAlchemyError:
        return  # database unavailable: integration tests will skip
    os.environ["DATABASE_URL"] = url.set(database=test_db).render_as_string(hide_password=False)
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")


_use_isolated_test_database()

from app.core.database import get_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Real PostGIS session; every test's writes are rolled back."""
    try:
        conn = get_engine().connect()
    except OperationalError:
        pytest.skip("PostGIS database not available")
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        session.execute(text("SELECT 1 FROM aircraft LIMIT 0"))
    except Exception:
        session.close()
        trans.rollback()
        conn.close()
        pytest.skip("migrations not applied")
    yield session
    session.close()
    trans.rollback()
    conn.close()
