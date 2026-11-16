"""Requires migrated PostGIS (DATABASE_URL). Skipped otherwise."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.main import app
from app.models import Aircraft, AircraftObservation, DataSource

pytestmark = pytest.mark.integration


def test_health_ok_with_database(db_session: Session) -> None:
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        r = TestClient(app).get("/api/v1/system/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["components"]["postgis"]["status"] == "ok"


def test_icao24_format_enforced(db_session: Session) -> None:
    db_session.add(Aircraft(icao24="ZZZZZZ"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_observation_roundtrip_and_dedup(db_session: Session) -> None:
    src = DataSource(name="test-fixture", kind="dataset")
    ac = Aircraft(icao24="a1b2c3")
    db_session.add_all([src, ac])
    db_session.flush()
    t = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.add(
        AircraftObservation(
            aircraft_id=ac.id,
            data_source_id=src.id,
            observed_at=t,
            position="SRID=4326;POINT(-0.4543 51.4700)",
        )
    )
    db_session.flush()
    lat = db_session.execute(text("SELECT ST_Y(position) FROM aircraft_observations")).scalar_one()
    assert round(lat, 2) == 51.47
    assert db_session.scalar(select(AircraftObservation.velocity_ms)) is None  # absent stays NULL

    db_session.add(AircraftObservation(aircraft_id=ac.id, data_source_id=src.id, observed_at=t))
    with pytest.raises(IntegrityError):
        db_session.flush()
