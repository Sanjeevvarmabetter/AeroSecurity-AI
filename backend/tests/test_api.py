from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.main import app


def test_liveness(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_health_reports_down_without_database(client: TestClient) -> None:
    """Unreachable DB (port 1): 503 with a standard payload and no leaked connection details."""
    bad = create_engine("postgresql+psycopg://u:p@127.0.0.1:1/none", connect_args={"connect_timeout": 1})

    def broken_session() -> Iterator[Session]:
        with Session(bad) as s:
            yield s

    app.dependency_overrides[get_session] = broken_session
    try:
        r = client.get("/api/v1/system/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "down" and body["components"]["database"]["status"] == "down"
    assert "127.0.0.1" not in r.text and "u:p" not in r.text


def test_unknown_route_uses_standard_error(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_404"


def test_cors_rejects_unlisted_origin(client: TestClient) -> None:
    r = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_overview_analytics_endpoint(client: TestClient, db_session: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        r = client.get("/api/v1/analytics/overview", headers={"Authorization": "Bearer test-viewer-token"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert "total_aircraft" in body
    assert "total_observations" in body
    assert "by_severity" in body
    assert "data_sources" in body


def test_fleet_analytics_endpoint(client: TestClient, db_session: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        r = client.get("/api/v1/analytics/fleet", headers={"Authorization": "Bearer test-viewer-token"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert "altitude_distribution" in body
    assert "speed_distribution" in body
    assert "category_distribution" in body


def test_detection_rules_endpoints(client: TestClient, db_session: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        # 1. List rules
        r = client.get("/api/v1/detection/rules", headers={"Authorization": "Bearer test-viewer-token"})
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) >= 8
        rule_ids = [rule["id"] for rule in rules]
        assert "DET-001" in rule_ids

        # 2. Get single rule
        r2 = client.get(
            "/api/v1/detection/rules/DET-001", headers={"Authorization": "Bearer test-viewer-token"}
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == "DET-001"
        assert "hard_speed_ceiling_ms" in r2.json()["config"]

        # 3. Patch rule requires analyst/admin
        r_unauth = client.patch(
            "/api/v1/detection/rules/DET-001",
            json={"enabled": True},
            headers={"Authorization": "Bearer test-viewer-token"},
        )
        assert r_unauth.status_code == 403

        r_patch = client.patch(
            "/api/v1/detection/rules/DET-001",
            json={"enabled": True},
            headers={"Authorization": "Bearer test-analyst-token"},
        )
        assert r_patch.status_code == 200
        assert r_patch.json()["enabled"] is True
    finally:
        app.dependency_overrides.clear()


def test_case_management_workflow(client: TestClient, db_session: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        # 1. Create a standalone investigation case
        create_res = client.post(
            "/api/v1/investigations",
            json={
                "title": "Suspicious transponder behavior",
                "description": "Multi-hop observation anomalies detected during descent",
                "severity": "HIGH",
                "initial_note": "Case opened for manual signal triage",
                "claimed_name": "Lead Analyst Smith",
            },
            headers={"Authorization": "Bearer test-analyst-token"},
        )
        assert create_res.status_code == 201
        case = create_res.json()
        case_id = case["id"]
        assert case["title"] == "Suspicious transponder behavior"
        assert case["status"] == "NEW"
        assert len(case["notes"]) == 1
        assert case["notes"][0]["body"] == "Case opened for manual signal triage"

        # 2. Add another note
        note_res = client.post(
            f"/api/v1/investigations/{case_id}/notes",
            json={"body": "Secondary ground radar corroborates target"},
            headers={"Authorization": "Bearer test-analyst-token"},
        )
        assert note_res.status_code == 201
        assert note_res.json()["body"] == "Secondary ground radar corroborates target"

        # 3. Update status
        status_res = client.patch(
            f"/api/v1/investigations/{case_id}/status",
            json={"status": "UNDER_REVIEW", "reason": "Awaiting ATC logs"},
            headers={"Authorization": "Bearer test-analyst-token"},
        )
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "UNDER_REVIEW"

        # 4. Get case detail
        get_res = client.get(
            f"/api/v1/investigations/{case_id}",
            headers={"Authorization": "Bearer test-viewer-token"},
        )
        assert get_res.status_code == 200
        assert get_res.json()["status"] == "UNDER_REVIEW"
        assert len(get_res.json()["notes"]) == 3  # initial + secondary + status change note

        # 5. List cases
        list_res = client.get(
            "/api/v1/investigations/cases",
            headers={"Authorization": "Bearer test-viewer-token"},
        )
        assert list_res.status_code == 200
        items = list_res.json()["items"]
        assert any(c["id"] == case_id for c in items)
    finally:
        app.dependency_overrides.clear()
