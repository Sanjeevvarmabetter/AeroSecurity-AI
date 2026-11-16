from app.core.logging import redact


def test_redacts_url_credentials() -> None:
    out = redact("connect postgresql+psycopg://aerosec:hunter2@db:5432/x")
    assert "hunter2" not in out and "aerosec:***@db" in out


def test_redacts_key_value_secrets() -> None:
    for raw in ("api_key=abc123", "Authorization: Bearer", "password: s3cret", '"token": "xyz"'):
        out = redact(raw)
        assert "abc123" not in out and "s3cret" not in out and "xyz" not in out
