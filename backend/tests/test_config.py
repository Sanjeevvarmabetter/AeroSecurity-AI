import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_wildcard_cors_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://u:p@h/d", cors_origins=["*"])


def test_database_url_is_secret() -> None:
    s = Settings(database_url="postgresql+psycopg://u:topsecret@h/d")
    assert "topsecret" not in repr(s) and "topsecret" not in str(s.model_dump())


def test_database_url_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
