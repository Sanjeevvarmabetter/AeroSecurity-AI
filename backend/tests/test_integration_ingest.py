"""Ingestion against PostGIS. Synthetic fixtures are test data; one test uses real OpenSky data."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ingestion.aircraft_metadata import import_aircraft_metadata
from app.ingestion.airports import import_airports
from app.ingestion.base import ObservationProvider
from app.ingestion.opensky_csv import OpenSkyCsvProvider
from app.ingestion.schema import NormalizedObservation, Rejection
from app.ingestion.service import SourceDisabledError, ingest
from app.models import Aircraft, AircraftObservation, Airport, AuditLog, DataSource

pytestmark = pytest.mark.integration
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeProvider(ObservationProvider):
    name, kind, default_enabled = "fake-test", "dataset", True

    def __init__(self, items: list[NormalizedObservation | Rejection], boom: bool = False) -> None:
        self.items, self.boom = items, boom

    def fetch(self) -> Iterator[NormalizedObservation | Rejection]:
        yield from self.items
        if self.boom:
            raise RuntimeError("failed with api_key=SUPERSECRET")


def obs(icao: str = "a1b2c3", sec: int = 0, **kw: object) -> NormalizedObservation:
    base = {
        "observed_at": T0.replace(second=sec),
        "lat": 51.47,
        "lon": -0.45,
        "velocity_ms": 100.0,
        "origin_country": "Testland",
        "raw": {"issues": ["x"]} if kw.pop("issue", False) else {},
    }
    return NormalizedObservation(icao24=icao, **{**base, **kw})  # type: ignore[arg-type]


def test_ingest_counts_idempotency_provenance_and_audit(db_session: Session) -> None:
    items: list[NormalizedObservation | Rejection] = [
        obs(sec=0),
        obs(sec=1),
        obs(sec=1, issue=True),
        obs("ffffff", 0, lat=None, lon=None),
        Rejection("invalid_icao24", 9),
    ]
    r = ingest(db_session, FakeProvider(items), batch_size=100)
    assert (r.read, r.inserted, r.duplicates, r.aircraft_touched) == (5, 3, 1, 2)
    assert dict(r.rejected) == {"invalid_icao24": 1} and dict(r.field_issues) == {"x": 1}

    ac = db_session.scalar(select(Aircraft).where(Aircraft.icao24 == "a1b2c3"))
    assert (
        ac
        and ac.origin_country == "Testland"
        and ac.first_seen == T0
        and ac.last_seen == T0.replace(second=1)
    )
    no_pos = db_session.scalar(select(AircraftObservation).join(Aircraft).where(Aircraft.icao24 == "ffffff"))
    assert no_pos is not None and no_pos.position is None and no_pos.baro_altitude_m is None
    pt = db_session.execute(
        text(
            "SELECT ST_X(position), ST_Y(position), ST_SRID(position) FROM aircraft_observations o "
            "JOIN aircraft a ON a.id=o.aircraft_id WHERE a.icao24='a1b2c3' LIMIT 1"
        )
    ).one()
    assert pt == (-0.45, 51.47, 4326)

    again = ingest(db_session, FakeProvider(items), batch_size=2)  # multiple batches, same data
    assert again.inserted == 0 and again.duplicates == 4
    assert db_session.scalar(select(func.count()).select_from(AircraftObservation)) == 3

    src = db_session.scalar(select(DataSource).where(DataSource.name == "fake-test"))
    assert src and src.last_success_at and src.last_error is None
    actions = list(db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(src.id))))
    assert actions == ["ingest.completed"] * 2


def test_disabled_source_is_refused(db_session: Session) -> None:
    p = FakeProvider([obs()])
    p.default_enabled = False
    with pytest.raises(SourceDisabledError):
        ingest(db_session, p)
    src = db_session.scalar(select(DataSource).where(DataSource.name == "fake-test"))
    assert src is not None and not src.enabled
    assert db_session.scalar(select(func.count()).select_from(AircraftObservation)) == 0


def test_failure_recorded_and_redacted(db_session: Session) -> None:
    with pytest.raises(RuntimeError):
        ingest(db_session, FakeProvider([obs()], boom=True), batch_size=100)
    src = db_session.scalar(select(DataSource).where(DataSource.name == "fake-test"))
    assert src and src.last_error and "SUPERSECRET" not in src.last_error and src.last_error_at
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "ingest.failed"))
    assert log and "SUPERSECRET" not in str(log.details)


def test_airports_import_validates_and_upserts(db_session: Session, tmp_path: Path) -> None:
    f = tmp_path / "airports.csv"
    f.write_text(
        "ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country,iata_code\n"
        "TSTA,large_airport,Test A,51.47,-0.45,83,GB,tst\n"
        "TSTB,small_airport,Bad,95,0,,GB,\n"
        ",small_airport,NoIdent,1,1,,GB,\n"
    )
    r = import_airports(db_session, f)
    assert (r.read, r.inserted) == (3, 1) and dict(r.rejected) == {
        "invalid_coordinates": 1,
        "invalid_ident": 1,
    }
    a = db_session.scalar(select(Airport).where(Airport.ident == "TSTA"))
    assert a and a.iata_code == "TST" and a.elevation_ft == 83
    import_airports(db_session, f)
    assert db_session.scalar(select(func.count()).select_from(Airport).where(Airport.ident == "TSTA")) == 1


def test_aircraft_metadata_enriches_only_observed_aircraft(db_session: Session, tmp_path: Path) -> None:
    ingest(db_session, FakeProvider([obs("a1b2c3"), obs("bbbbbb")]))
    f = tmp_path / "db.csv"
    f.write_text(
        "'icao24','registration','typecode','manufacturerName','model','operator'\n"
        "'a1b2c3','N1TEST','B738','Boeing','737-800','Test Air'\n"
        "'bbbbbb','','unknow','','',''\n"  # placeholders / blanks must stay NULL
        "'eeeeee','N9NEVER','A320','Airbus','A320','Nobody'\n"  # never observed: must not be created
    )
    r = import_aircraft_metadata(db_session, f)
    assert r.read == 3 and r.inserted == 2
    a = db_session.scalar(select(Aircraft).where(Aircraft.icao24 == "a1b2c3"))
    assert a and (a.registration, a.aircraft_type, a.manufacturer, a.model) == (
        "N1TEST",
        "B738",
        "Boeing",
        "737-800",
    )
    assert a.metadata_source_id is not None
    b = db_session.scalar(select(Aircraft).where(Aircraft.icao24 == "bbbbbb"))
    assert b and b.registration is None and b.aircraft_type is None and b.operator is None
    assert (
        db_session.scalar(select(func.count()).select_from(Aircraft).where(Aircraft.icao24 == "eeeeee")) == 0
    )


REAL = Path(__file__).resolve().parents[2] / "datasets/raw/opensky-fz1073_2026-09-30.tar.gz"


@pytest.mark.skipif(not REAL.exists(), reason="run scripts/fetch_datasets.py first")
def test_real_opensky_incident_dataset_imports(db_session: Session) -> None:
    """Real OpenSky data (CC BY 4.0): flydubai FZ1073, 2026-09-30, icao24 8965d1."""
    r = ingest(db_session, OpenSkyCsvProvider(REAL), batch_size=1000)
    assert r.read == 4402 and r.aircraft_touched == 1 and r.inserted > 1000
    assert r.inserted + r.duplicates + sum(r.rejected.values()) == r.read
    ac = db_session.scalar(select(Aircraft).where(Aircraft.icao24 == "8965d1"))
    assert ac and ac.first_seen and ac.last_seen and ac.first_seen < ac.last_seen
    with_pos = db_session.scalar(
        select(func.count()).select_from(AircraftObservation).where(AircraftObservation.position.is_not(None))
    )
    assert with_pos and with_pos > 1000
    bbox = db_session.execute(
        text(
            "SELECT min(ST_Y(position)), max(ST_Y(position)), min(ST_X(position)), max(ST_X(position)) "
            "FROM aircraft_observations"
        )
    ).one()
    assert 20 < bbox[0] < bbox[1] < 40 and 30 < bbox[2] < bbox[3] < 60  # Gulf -> Tabuk corridor
    assert ingest(db_session, OpenSkyCsvProvider(REAL)).inserted == 0  # idempotent
