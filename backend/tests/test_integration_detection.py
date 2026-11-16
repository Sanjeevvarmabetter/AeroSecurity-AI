"""Engine against PostGIS. Synthetic observations are test data; the last tests use the real OpenSky extracts."""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.detection.engine import run_detection, sync_rule_registry
from app.ingestion.opensky_csv import OpenSkyCsvProvider
from app.ingestion.service import ingest
from app.models import Aircraft, AircraftObservation, Anomaly, AuditLog, DataSource, Evidence
from tests.detection.helpers import T0

pytestmark = pytest.mark.integration
RAW = Path(__file__).resolve().parents[2] / "datasets/raw"


def seed(
    db: Session, icao: str = "abc123", squawk_obs: int = 5, source_name: str = "eng-test"
) -> tuple[Aircraft, DataSource]:
    src = db.scalar(select(DataSource).where(DataSource.name == source_name)) or DataSource(
        name=source_name, kind="dataset", enabled=True
    )
    db.add(src)
    ac = Aircraft(icao24=icao, aircraft_type="B738")
    db.add(ac)
    db.flush()
    for i in range(squawk_obs):
        db.add(
            AircraftObservation(
                aircraft_id=ac.id,
                data_source_id=src.id,
                observed_at=T0 + timedelta(seconds=i),
                position=f"SRID=4326;POINT({20 + i * 0.001} 10)",
                squawk="7700",
                baro_altitude_m=3000.0,
                velocity_ms=200.0,
                callsign="TST1",
            )
        )
    db.flush()
    return ac, src


def test_run_persists_anomaly_with_evidence_and_audit(db_session: Session) -> None:
    ac, _ = seed(db_session)
    rep = run_detection(db_session, rule_ids=["DET-005"], icao24="abc123", actor="test")
    assert rep.rules["DET-005"].created == 1 and rep.aircraft_processed == 1
    a = db_session.scalar(select(Anomaly).where(Anomaly.aircraft_id == ac.id))
    assert (
        a
        and a.rule_id == "DET-005"
        and a.rule_version == "1.0.0"
        and a.severity == "HIGH"
        and a.status == "OPEN"
    )
    assert a.detection_type == "EMERGENCY_SQUAWK" and a.source_refs == ["eng-test"] and 0 < a.confidence <= 1
    assert a.summary["alternative_explanations"] and a.summary["squawk"] == "7700"
    ev = list(
        db_session.scalars(select(Evidence).where(Evidence.anomaly_id == a.id).order_by(Evidence.ordinal))
    )
    assert [e.ordinal for e in ev] == list(range(len(ev))) and ev[-1].kind == "context"
    obs_ids = {o for o in db_session.scalars(select(AircraftObservation.id))}
    assert all(
        e.observation_id in obs_ids for e in ev if e.kind == "observation"
    )  # evidence links to real rows
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "detection.run"))
    assert log and log.actor == "test" and log.details is not None
    assert log.details["rules"]["DET-005"]["created"] == 1


def test_rerun_is_idempotent(db_session: Session) -> None:
    seed(db_session)
    run_detection(db_session, rule_ids=["DET-005"])
    again = run_detection(db_session, rule_ids=["DET-005"])
    assert (again.rules["DET-005"].created, again.rules["DET-005"].unchanged) == (0, 1)
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) == 1


def test_growing_episode_updates_the_same_open_anomaly(db_session: Session) -> None:
    ac, src = seed(db_session)
    run_detection(db_session, rule_ids=["DET-005"])
    first = db_session.scalar(select(Anomaly))
    assert first is not None
    before_end, before_conf = first.event_end, first.confidence
    for i in range(5, 40):
        db_session.add(
            AircraftObservation(
                aircraft_id=ac.id, data_source_id=src.id, observed_at=T0 + timedelta(seconds=i), squawk="7700"
            )
        )
    db_session.flush()
    rep = run_detection(db_session, rule_ids=["DET-005"])
    assert (rep.rules["DET-005"].updated, rep.rules["DET-005"].created) == (1, 0)
    db_session.refresh(first)
    assert first.event_end > before_end and first.confidence >= before_conf
    assert db_session.scalar(select(func.count()).select_from(Anomaly)) == 1


def test_analyst_closed_findings_are_never_rewritten(db_session: Session) -> None:
    ac, src = seed(db_session)
    run_detection(db_session, rule_ids=["DET-005"])
    a = db_session.scalar(select(Anomaly))
    assert a is not None
    a.status = "FALSE_POSITIVE"
    for i in range(5, 12):
        db_session.add(
            AircraftObservation(
                aircraft_id=ac.id, data_source_id=src.id, observed_at=T0 + timedelta(seconds=i), squawk="7700"
            )
        )
    db_session.flush()
    end_before = a.event_end
    rep = run_detection(db_session, rule_ids=["DET-005"])
    db_session.refresh(a)
    assert rep.rules["DET-005"].unchanged == 1 and a.status == "FALSE_POSITIVE" and a.event_end == end_before


def test_disabled_rule_is_skipped_and_config_override_applies(db_session: Session) -> None:
    seed(db_session)
    reg = sync_rule_registry(db_session)
    reg["DET-005"].enabled = False
    db_session.commit()
    assert "DET-005" not in run_detection(db_session, rule_ids=["DET-005"]).rules
    reg["DET-005"].enabled = True
    reg["DET-005"].config = {"min_observations": 50}  # 5 observations now counts as a transient single event
    db_session.commit()
    run_detection(db_session, rule_ids=["DET-005"])
    anomaly = db_session.scalar(select(Anomaly))
    assert anomaly is not None and anomaly.summary["transient"] is True


def test_bad_inputs_rejected(db_session: Session) -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        run_detection(db_session, rule_ids=["DET-999"])
    seed(db_session)
    reg = sync_rule_registry(db_session)
    reg["DET-005"].config = {"typo_setting": 1}
    db_session.commit()
    with pytest.raises(Exception):  # noqa: B017,PT011
        run_detection(db_session, rule_ids=["DET-005"])


# ---- real data ----------------------------------------------------------------------------------
INCIDENTS = sorted(RAW.glob("incident-*.tar.gz")) + sorted(RAW.glob("opensky-fz1073*.tar.gz"))


@pytest.mark.skipif(len(INCIDENTS) < 5, reason="run scripts/fetch_datasets.py first")
def test_real_incident_data_detection_results(db_session: Session) -> None:
    for f in INCIDENTS:
        ingest(db_session, OpenSkyCsvProvider(f))
    run_detection(db_session)
    rows = db_session.execute(
        select(
            Aircraft.icao24,
            Anomaly.rule_id,
            Anomaly.severity,
            Anomaly.summary,
            Anomaly.event_start,
            Anomaly.event_end,
        ).join(Aircraft, Aircraft.id == Anomaly.aircraft_id)
    ).all()
    by_rule: dict[str, list] = {}  # type: ignore[type-arg]
    for r in rows:
        by_rule.setdefault(r.rule_id, []).append(r)

    # Austrian Airlines OS82 (diverted after a bomb threat) squawked 7700 for several minutes.
    (sq,) = [r for r in by_rule["DET-005"]]
    assert sq.icao24 == "440604" and sq.severity == "HIGH" and sq.summary["squawk"] == "7700"
    assert sq.summary["observations"] > 150 and 300 < sq.summary["duration_s"] < 600
    assert sq.summary["last_known_position"] is not None

    # Regression: ~1 s timestamp jitter in real data must NOT look like an impossible transition,
    # and one source can never produce an identity conflict.
    assert "DET-001" not in by_rule and "DET-004" not in by_rule

    # A 440 m/s velocity glitch on an A320 and the Learjet's barometric/geometric divergence are both reported.
    assert any(r.icao24 == "440604" and r.summary.get("peak_ms", 0) > 400 for r in by_rule["DET-002"])
    assert any(
        r.icao24 == "a9ab17" and r.summary.get("check") == "baro_geo_divergence" for r in by_rule["DET-003"]
    )
    assert {r.icao24 for r in by_rule["DET-006"]} >= {"0d086e", "8965d1"}
    # Nothing in this data warrants CRITICAL, and every finding is a data statement with alternatives.
    assert all(r.severity != "CRITICAL" for r in rows)
    assert all(r.summary.get("alternative_explanations") for r in rows)
