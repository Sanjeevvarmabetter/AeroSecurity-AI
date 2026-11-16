import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import RateLimitMiddleware, Role, resolve_role
from app.main import app
from app.models import DataSource

URL = "/api/v1/data-sources"


def auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_unauthenticated_rejected(client: TestClient) -> None:
    r = client.get(URL)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert client.get(URL, headers=auth("wrong")).status_code == 401
    assert client.get(URL, headers={"Authorization": "Basic dGVzdA=="}).status_code == 401


def test_roles_resolve_and_empty_token_never_matches() -> None:
    s = get_settings()
    assert resolve_role("test-admin-token", s) == Role.ADMIN
    assert resolve_role("test-viewer-token", s) == Role.VIEWER
    assert resolve_role("", s) is None and resolve_role(None, s) is None


def test_unconfigured_roles_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    s = Settings(database_url="postgresql+psycopg://u:p@h/d")
    monkeypatch.setattr(s, "api_token_admin", s.api_token_admin.__class__(""))
    assert resolve_role("anything", s) is None or resolve_role("anything", s) is not Role.ADMIN


def test_rate_limit_returns_429_with_standard_envelope() -> None:
    mini = FastAPI()
    mini.add_middleware(RateLimitMiddleware, limit_per_minute=3)

    @mini.get("/x")
    def x() -> dict[str, int]:
        return {"ok": 1}

    c = TestClient(mini)
    assert [c.get("/x").status_code for _ in range(4)] == [200, 200, 200, 429]
    r = c.get("/x")
    assert r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    # separate token => separate bucket
    assert c.get("/x", headers=auth("other")).status_code == 200


@pytest.mark.integration
def test_authorised_viewer_lists_sources(db_session: Session) -> None:
    db_session.add(DataSource(name="sec-test", kind="dataset", last_error="boom"))
    db_session.flush()
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        r = TestClient(app).get(URL, headers=auth("test-viewer-token"))
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert "sec-test" in [d["name"] for d in r.json()]
    assert db_session.scalar(select(DataSource.id).limit(1)) is not None
