"""Read API against PostGIS. Seeded rows are synthetic test data; the final test uses the real FZ1073 dataset."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.ingestion.opensky_csv import OpenSkyCsvProvider
from app.ingestion.service import ingest
from app.main import app
from app.models import Aircraft, AircraftObservation, Airport, DataSource

pytestmark = pytest.mark.integration
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
H = {"Authorization": "Bearer test-viewer-token"}


@pytest.fixture
def api(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def seed(db: Session) -> None:
    src = DataSource(name="seed-test", kind="dataset", enabled=True)
    meta = DataSource(name="meta-test", kind="dataset", enabled=True)
    db.add_all([src, meta])
    db.flush()
    a = Aircraft(
        icao24="aaaaaa",
        registration="N123AB",
        aircraft_type="B738",
        model="737-800",
        origin_country="Testland",
        first_seen=T0,
        last_seen=T0 + timedelta(seconds=30),
        metadata_source_id=meta.id,
    )
    b = Aircraft(icao24="bbbbbb", origin_country="Testland", first_seen=T0, last_seen=T0)
    c = Aircraft(icao24="cccccc", first_seen=T0, last_seen=T0)
    db.add_all([a, b, c])
    db.flush()

    def o(ac: Aircraft, sec: int, lat: float | None, lon: float | None, **kw: object) -> AircraftObservation:
        return AircraftObservation(
            aircraft_id=ac.id,
            data_source_id=src.id,
            observed_at=T0 + timedelta(seconds=sec),
            position=f"SRID=4326;POINT({lon} {lat})" if lat is not None else None,
            **kw,
        )

    db.add_all(
        [
            o(a, 0, 0.0, 10.0, callsign="TST100", baro_altitude_m=1000.0, velocity_ms=100.0, squawk="1234"),
            o(a, 10, 0.0, 10.01, callsign="TST100", baro_altitude_m=1100.0, velocity_ms=100.0, squawk="1234"),
            o(a, 30, 0.0, 10.03, callsign="TST100", baro_altitude_m=1300.0, velocity_ms=100.0, squawk="7700"),
            o(a, 40, None, None, callsign="TST100", raw={"issues": ["missing_coordinates"]}),  # no position
            o(b, 0, 10.0, 179.9, callsign="ANTI1"),
            o(c, -3600, 50.0, 8.0, callsign="OLD1"),  # an hour before the others
        ]
    )
    db.add(
        Airport(
            ident="TSTA",
            iata_code="TST",
            name="Testville Intl",
            airport_type="large_airport",
            iso_country="TL",
            elevation_ft=10,
            position="SRID=4326;POINT(10 0)",
        )
    )
    db.flush()


def test_requires_auth(api: TestClient) -> None:
    for path in (
        "/aviation/aircraft",
        "/aviation/aircraft/live",
        "/aviation/aircraft/aaaaaa",
        "/aviation/airports",
        "/analytics/trajectories?icao24=aaaaaa",
    ):
        assert api.get(f"/api/v1{path}").status_code == 401, path


def test_search_by_icao_registration_callsign(api: TestClient, db_session: Session) -> None:
    seed(db_session)

    def ids(q: str) -> list[str]:
        r = api.get("/api/v1/aviation/aircraft", params={"q": q}, headers=H)
        assert r.status_code == 200
        return sorted(i["icao24"] for i in r.json()["items"])

    assert ids("aaa") == ["aaaaaa"] and ids("AAAAAA") == ["aaaaaa"]
    assert ids("n123") == ["aaaaaa"]
    assert ids("tst1") == ["aaaaaa"]
    assert ids("zzz") == []
    full = api.get("/api/v1/aviation/aircraft", headers=H).json()
    assert full["total"] == 3 and full["items"][0]["icao24"] == "aaaaaa"  # newest last_seen first
    a = full["items"][0]
    assert a["registration"] == "N123AB" and a["last_callsign"] == "TST100"
    assert a["last_position"] == {
        "lat": 0.0,
        "lon": 10.03,
    }  # latest *positioned* observation, not the null one
    assert full["items"][2]["registration"] is None  # absent stays null


def test_search_rejects_wildcards_and_sql(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    for bad in ("%", "a_", "x' OR '1'='1", "a;DROP TABLE aircraft", "a" * 40):
        assert api.get("/api/v1/aviation/aircraft", params={"q": bad}, headers=H).status_code == 422, bad
    assert api.get("/api/v1/aviation/aircraft", headers=H).json()["total"] == 3  # still intact


def test_pagination_and_sort(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    r = api.get(
        "/api/v1/aviation/aircraft", params={"limit": 2, "offset": 1, "sort": "icao24"}, headers=H
    ).json()
    assert [i["icao24"] for i in r["items"]] == ["bbbbbb", "cccccc"] and r["total"] == 3
    assert api.get("/api/v1/aviation/aircraft", params={"limit": 0}, headers=H).status_code == 422
    assert api.get("/api/v1/aviation/aircraft", params={"sort": "bogus"}, headers=H).status_code == 422


def test_detail_provenance_and_squawks(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    d = api.get("/api/v1/aviation/aircraft/AAAAAA", headers=H).json()
    assert d["observation_count"] == 4 and d["positioned_count"] == 3
    assert d["callsigns"] == ["TST100"] and d["observation_sources"] == ["seed-test"]
    assert d["metadata_source"] == "meta-test" and d["model"] == "737-800"
    assert [s["squawk"] for s in d["squawks"]] == ["1234", "7700"] and d["squawks"][0]["observations"] == 2
    bare = api.get("/api/v1/aviation/aircraft/cccccc", headers=H).json()
    assert bare["metadata_source"] is None and bare["registration"] is None
    assert api.get("/api/v1/aviation/aircraft/ffffff", headers=H).status_code == 404
    assert api.get("/api/v1/aviation/aircraft/xyz", headers=H).status_code == 422


def test_history_range_order_issues(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    url = "/api/v1/aviation/aircraft/aaaaaa/history"
    r = api.get(url, params={"order": "asc"}, headers=H).json()
    assert r["total"] == 4 and r["items"][0]["lat"] == 0.0 and r["items"][0]["lon"] == 10.0
    assert r["items"][-1]["lat"] is None and r["items"][-1]["validation_issues"] == ["missing_coordinates"]
    assert r["items"][0]["source"] == "seed-test"
    rng = api.get(
        url, params={"start": "2026-01-01T12:00:05Z", "end": "2026-01-01T12:00:35Z"}, headers=H
    ).json()
    assert rng["total"] == 2
    assert (
        api.get(
            url, params={"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"}, headers=H
        ).status_code
        == 422
    )
    assert api.get(url, params={"start": "2026-01-01T00:00:00"}, headers=H).status_code == 422  # naive time
    assert api.get(url, params={"start": "not-a-date"}, headers=H).status_code == 422


def test_live_snapshot_bbox_stale_and_antimeridian(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    live = "/api/v1/aviation/aircraft/live"
    at = "2026-01-01T12:00:35Z"
    r = api.get(live, params={"at": at, "max_age_s": 60}, headers=H).json()
    assert {a["icao24"] for a in r["aircraft"]} == {"aaaaaa", "bbbbbb"} and not r["stale"]
    a = next(x for x in r["aircraft"] if x["icao24"] == "aaaaaa")
    assert (
        a["lon"] == 10.03 and a["age_s"] == 5.0 and a["registration"] == "N123AB"
    )  # newest position, not the null row
    box = {"at": at, "max_age_s": 60, "lamin": -1, "lomin": 9, "lamax": 1, "lomax": 11}
    assert [x["icao24"] for x in api.get(live, params=box, headers=H).json()["aircraft"]] == ["aaaaaa"]
    wrap = {
        "at": at,
        "max_age_s": 60,
        "lamin": 5,
        "lomin": 170,
        "lamax": 15,
        "lomax": -170,
    }  # crosses antimeridian
    assert [x["icao24"] for x in api.get(live, params=wrap, headers=H).json()["aircraft"]] == ["bbbbbb"]
    future = api.get(live, params={"at": "2026-06-01T00:00:00Z", "max_age_s": 900}, headers=H).json()
    assert (
        future["aircraft"] == [] and future["stale"] is True and future["latest_observation_at"] is not None
    )
    assert api.get(live, params={"lamin": 1}, headers=H).status_code == 422  # partial bbox
    assert (
        api.get(live, params={"lamin": 5, "lomin": 0, "lamax": 1, "lomax": 1}, headers=H).status_code == 422
    )


def test_live_with_no_data_is_stale_not_fabricated(api: TestClient) -> None:
    r = api.get("/api/v1/aviation/aircraft/live", headers=H).json()
    assert r["aircraft"] == [] and r["stale"] is True


def test_trajectory_derived_values_gaps_and_notes(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    r = api.get("/api/v1/analytics/trajectories", params={"icao24": "aaaaaa", "gap_s": 15}, headers=H).json()
    s, segs = r["summary"], r["segments"]
    assert s["points"] == 3 and s["segments"] == 2 and s["gap_count"] == 1  # the 20 s hop exceeds 15 s
    assert [x["is_gap"] for x in segs] == [False, True]
    assert segs[0]["distance_m"] == pytest.approx(1111.95, rel=1e-3)
    assert (
        segs[0]["derived_speed_ms"] == pytest.approx(111.2, rel=1e-3)
        and segs[0]["reported_speed_ms"] == 100.0
    )
    assert s["observed_distance_m"] == pytest.approx(1111.95, rel=1e-3)  # gap distance excluded
    assert segs[0]["derived_vertical_rate_ms"] == pytest.approx(10.0)
    assert len(r["points"]) == 3 and any("flight plan" in n for n in r["notes"])
    assert (
        api.get("/api/v1/analytics/trajectories", params={"icao24": "ffffff"}, headers=H).status_code == 404
    )
    assert (
        api.get(
            "/api/v1/analytics/trajectories", params={"icao24": "aaaaaa", "gap_s": 0}, headers=H
        ).status_code
        == 422
    )


def test_airports(api: TestClient, db_session: Session) -> None:
    seed(db_session)
    r = api.get("/api/v1/aviation/airports", params={"q": "tst"}, headers=H).json()
    assert [a["ident"] for a in r["items"]] == ["TSTA"] and r["items"][0]["lon"] == 10.0
    assert api.get("/api/v1/aviation/airports/tst", headers=H).json()["name"] == "Testville Intl"
    assert api.get("/api/v1/aviation/airports/NOPE9", headers=H).status_code == 404
    assert api.get("/api/v1/aviation/airports", params={"q": "a%"}, headers=H).status_code == 422


REAL = Path(__file__).resolve().parents[2] / "datasets/raw/opensky-fz1073_2026-09-30.tar.gz"


@pytest.mark.skipif(not REAL.exists(), reason="run scripts/fetch_datasets.py first")
def test_real_dataset_gaps_match_the_raw_data(api: TestClient, db_session: Session) -> None:
    """Gap values were verified independently against the dataset's raw state_vectors AND position_data4 tables:
    positions stop 04:01:28Z and resume 05:15:55Z (4476 s), plus a 553-562 s gap near 05:22-05:31Z.
    NOTE: the dataset README prose quotes 69 min / 252 s, which does not match its own tables (see
    docs/data-sources.md); we assert what the data shows."""
    ingest(db_session, OpenSkyCsvProvider(REAL))
    r = api.get("/api/v1/analytics/trajectories", params={"icao24": "8965d1", "gap_s": 120}, headers=H).json()
    s = r["summary"]
    assert s["points"] > 3000 and s["gap_count"] == 2
    assert s["longest_gap_s"] == pytest.approx(4476.187, abs=1.0)
    assert sorted(round(x["dt_s"]) for x in r["segments"] if x["is_gap"]) == [563, 4476]
    assert 200 < s["max_reported_speed_ms"] < 300
    # Real-data finding: a few sub-second intervals show derived speeds > 300 m/s (max ~1182) because the feed's
    # position timestamps jitter by up to ~1 s. Intervals of >= 1 s are consistent with the reported ~230 m/s.
    # DET-001 must therefore model timestamp uncertainty rather than trust tiny dt values.
    assert s["max_derived_speed_ms"] > 1000
    long_enough = [x["derived_speed_ms"] for x in r["segments"] if not x["is_gap"] and x["dt_s"] >= 1.0]
    assert long_enough and max(long_enough) < 300
    assert all(
        x["dt_s"] < 1.0 for x in r["segments"] if x["derived_speed_ms"] and x["derived_speed_ms"] > 300
    )
    assert api.get("/api/v1/aviation/aircraft", params={"q": "FDB1073"}, headers=H).json()["total"] == 1
