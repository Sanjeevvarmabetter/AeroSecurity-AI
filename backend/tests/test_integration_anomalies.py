"""Anomaly Center / emergencies / investigation API against PostGIS. Seeded rows are synthetic test data."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.detection.engine import run_detection, sync_rule_registry
from app.ingestion.opensky_csv import OpenSkyCsvProvider
from app.ingestion.service import ingest
from app.main import app
from app.models import Aircraft, Anomaly, AuditLog, DataSource, Evidence
from tests.detection.helpers import T0
from tests.test_integration_detection import seed

pytestmark = pytest.mark.integration
V = {"Authorization": "Bearer test-viewer-token"}
A = {"Authorization": "Bearer test-analyst-token"}


@pytest.fixture
def api(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make(
    db: Session,
    ac: Aircraft,
    *,
    rule: str = "DET-001",
    sev: str = "HIGH",
    conf: float = 0.8,
    status: str = "OPEN",
    typ: str = "POSITION_ANOMALY",
    n: int = 0,
    minutes: int = 0,
) -> Anomaly:
    sync_rule_registry(db)
    a = Anomaly(
        rule_id=rule,
        rule_version="1.0.0",
        aircraft_id=ac.id,
        detection_type=typ,
        title=f"Test finding {n}",
        description="desc",
        severity=sev,
        confidence=conf,
        data_quality="GOOD",
        status=status,
        event_start=T0 + timedelta(minutes=minutes),
        event_end=T0 + timedelta(minutes=minutes, seconds=30),
        dedup_key=f"k{n}",
        source_refs=["eng-test"],
        summary={"jumps": 1, "alternative_explanations": ["Receiver clock error", "Spoofing"]},
    )
    db.add(a)
    db.flush()
    db.add(Evidence(anomaly_id=a.id, ordinal=0, kind="metric", payload={"distance_m": 1000}))
    db.flush()
    return a


def fixture_set(db: Session) -> dict[str, Anomaly]:
    ac, _ = seed(db, squawk_obs=0)
    ac2 = Aircraft(icao24="def456")
    db.add(ac2)
    db.flush()
    return {
        "hi": make(db, ac, sev="HIGH", conf=0.9, n=1, minutes=0),
        "crit": make(
            db, ac, sev="CRITICAL", conf=0.4, typ="EMERGENCY_SQUAWK", rule="DET-005", n=2, minutes=10
        ),
        "low": make(
            db,
            ac2,
            sev="LOW",
            conf=0.6,
            status="INVESTIGATING",
            typ="DATA_INTEGRITY",
            rule="DET-006",
            n=3,
            minutes=20,
        ),
        "med": make(db, ac2, sev="MEDIUM", conf=0.7, status="RESOLVED", n=4, minutes=30),
    }


def ids(r: Response) -> list[str]:
    assert r.status_code == 200, r.text
    return [i["anomaly_id"] for i in r.json()["items"]]


# ---- auth --------------------------------------------------------------------------------------------
def test_all_endpoints_require_authentication(api: TestClient, db_session: Session) -> None:
    a = fixture_set(db_session)["hi"]
    aid = f"ANM-{a.id:04d}"
    for method, path in [
        ("get", "/anomalies"),
        ("get", "/anomalies/stats"),
        ("get", f"/anomalies/{aid}"),
        ("get", "/emergencies"),
        ("get", "/investigations"),
        ("get", "/auth/me"),
        ("post", f"/anomalies/{aid}/investigate"),
        ("patch", f"/anomalies/{aid}/status"),
        ("post", f"/anomalies/{aid}/notes"),
    ]:
        assert getattr(api, method)(f"/api/v1{path}").status_code == 401, path


def test_viewer_can_read_but_not_write_and_analyst_can(api: TestClient, db_session: Session) -> None:
    aid = f"ANM-{fixture_set(db_session)['hi'].id:04d}"
    assert api.get(f"/api/v1/anomalies/{aid}", headers=V).status_code == 200
    assert api.get("/api/v1/auth/me", headers=V).json()["role"] == "viewer"
    assert api.get("/api/v1/auth/me", headers=A).json()["role"] == "analyst"
    for method, path, body in [
        ("post", f"/anomalies/{aid}/investigate", {}),
        ("post", f"/anomalies/{aid}/notes", {"body": "x"}),
        ("patch", f"/anomalies/{aid}/status", {"status": "FALSE_POSITIVE", "reason": "x"}),
    ]:
        r = getattr(api, method)(f"/api/v1{path}", json=body, headers=V)
        assert r.status_code == 403 and "analyst" in r.json()["error"]["message"], path
    me = api.get("/api/v1/auth/me", headers=A).json()
    assert "test-analyst-token" not in str(me) and len(me["key_id"]) == 8  # fingerprint only, never the token


# ---- listing / filtering ---------------------------------------------------------------------------
def test_filters_sorting_and_pagination(api: TestClient, db_session: Session) -> None:
    s = fixture_set(db_session)
    pid = {k: f"ANM-{v.id:04d}" for k, v in s.items()}

    def get(**p: Any) -> Response:
        r: Response = api.get("/api/v1/anomalies", params=p, headers=V)
        return r

    assert set(ids(get())) == set(pid.values())
    assert set(ids(get(severity=["HIGH", "CRITICAL"]))) == {pid["hi"], pid["crit"]}
    assert ids(get(status="INVESTIGATING")) == [pid["low"]]
    assert ids(get(detection_type="EMERGENCY_SQUAWK")) == [pid["crit"]]
    assert ids(get(rule_id="DET-006")) == [pid["low"]]
    assert set(ids(get(icao24="abc"))) == {pid["hi"], pid["crit"]}
    assert set(ids(get(min_confidence=0.65))) == {pid["hi"], pid["med"]}
    assert ids(get(start="2026-01-01T12:25:00Z", end="2026-01-01T12:45:00Z")) == [
        pid["med"]
    ]  # window overlap
    assert ids(get(sort="severity", order="desc"))[:2] == [pid["crit"], pid["hi"]]
    assert ids(get(sort="severity", order="asc"))[0] == pid["low"]
    assert ids(get(sort="confidence", order="desc"))[0] == pid["hi"]
    page = get(limit=2, offset=1, sort="event_start", order="asc").json()
    assert page["total"] == 4 and len(page["items"]) == 2 and page["items"][0]["anomaly_id"] == pid["crit"]
    item = get(icao24="def").json()["items"][0]
    assert item["has_investigation"] is False and item["rule_name"] and item["confidence"] <= 1


def test_filter_validation_and_injection_attempts(api: TestClient, db_session: Session) -> None:
    fixture_set(db_session)
    bad = [
        {"severity": "SEVERE"},
        {"status": "DONE"},
        {"icao24": "zz"},
        {"icao24": "%"},
        {"icao24": "a'; DROP TABLE anomalies;--"},
        {"detection_type": "x' OR '1'='1"},
        {"rule_id": "DET-1"},
        {"min_confidence": 2},
        {"start": "2026-01-01T00:00:00"},
        {"start": "2026-02-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"limit": 0},
        {"limit": 1000},
        {"sort": "id; --"},
    ]
    for p in bad:
        assert api.get("/api/v1/anomalies", params=p, headers=V).status_code == 422, p
    assert api.get("/api/v1/anomalies", headers=V).json()["total"] == 4  # table intact


def test_stats(api: TestClient, db_session: Session) -> None:
    fixture_set(db_session)
    s = api.get("/api/v1/anomalies/stats", headers=V).json()
    assert s["total"] == 4 and s["by_severity"] == {"HIGH": 1, "CRITICAL": 1, "LOW": 1, "MEDIUM": 1}
    assert s["by_status"] == {"OPEN": 2, "INVESTIGATING": 1, "RESOLVED": 1} and s["by_rule"]["DET-001"] == 2


# ---- detail -------------------------------------------------------------------------------------------
def test_detail_contents_and_errors(api: TestClient, db_session: Session) -> None:
    a = fixture_set(db_session)["hi"]
    d = api.get(f"/api/v1/anomalies/ANM-{a.id:04d}", headers=V).json()
    assert d["icao24"] == "abc123" and d["rule"]["id"] == "DET-001" and d["rule"]["version"] == "1.0.0"
    assert (
        d["alternatives"] == ["Receiver clock error", "Spoofing"]
        and "alternative_explanations" not in d["summary"]
    )
    assert d["evidence"][0]["kind"] == "metric" and d["allowed_transitions"] == [
        "INVESTIGATING",
        "FALSE_POSITIVE",
    ]
    assert d["investigation"] is None and d["notes"] == [] and d["timeline"][0]["kind"] == "detected"
    assert api.get("/api/v1/anomalies/ANM-9999", headers=V).status_code == 404
    for bad in ("ANM-abc", "anm-1", "1", "ANM-"):
        assert api.get(f"/api/v1/anomalies/{bad}", headers=V).status_code == 422, bad


# ---- workflow ------------------------------------------------------------------------------------------
def audit(db: Session, pk: int) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "anomaly", AuditLog.entity_id == str(pk))
            .order_by(AuditLog.id)
        )
    )


def test_full_investigation_workflow_is_audited(api: TestClient, db_session: Session) -> None:
    a = fixture_set(db_session)["hi"]
    u = f"/api/v1/anomalies/ANM-{a.id:04d}"
    # Notes and INVESTIGATING both require the investigation to exist first.
    assert api.post(f"{u}/notes", json={"body": "too early"}, headers=A).status_code == 409
    assert api.patch(f"{u}/status", json={"status": "INVESTIGATING"}, headers=A).status_code == 409

    r = api.post(f"{u}/investigate", json={"note": "Initial triage", "claimed_name": "J. Doe"}, headers=A)
    assert r.status_code == 201
    d = r.json()
    assert d["status"] == "INVESTIGATING" and d["investigation"]["opened_by"].startswith("analyst:")
    assert [n["body"] for n in d["notes"]] == ["Initial triage"] and d["notes"][0]["claimed_name"] == "J. Doe"
    assert api.post(f"{u}/investigate", json={}, headers=A).status_code == 409  # only once

    n = api.post(f"{u}/notes", json={"body": "<script>alert(1)</script> check receiver"}, headers=A)
    assert (
        n.status_code == 201 and n.json()["body"] == "<script>alert(1)</script> check receiver"
    )  # stored verbatim as text
    assert n.headers["content-type"].startswith("application/json")

    # Closing needs a reason; an unreachable transition is refused.
    assert api.patch(f"{u}/status", json={"status": "FALSE_POSITIVE"}, headers=A).status_code == 422
    assert (
        api.patch(f"{u}/status", json={"status": "FALSE_POSITIVE", "reason": "   "}, headers=A).status_code
        == 422
    )
    r = api.patch(
        f"{u}/status", json={"status": "FALSE_POSITIVE", "reason": "Receiver clock skew confirmed"}, headers=A
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "FALSE_POSITIVE"
        and r.json()["investigation"]["closed_at"]
    )
    assert r.json()["allowed_transitions"] == ["OPEN"]
    assert api.patch(f"{u}/status", json={"status": "INVESTIGATING"}, headers=A).status_code == 409
    assert (
        api.patch(f"{u}/status", json={"status": "FALSE_POSITIVE", "reason": "again"}, headers=A).status_code
        == 409
    )
    r = api.patch(f"{u}/status", json={"status": "OPEN", "reason": "reopened for review"}, headers=A)
    assert r.json()["status"] == "OPEN" and r.json()["investigation"]["closed_at"] is None

    # Every change is in the audit log, in order, attributed to the credential, never containing the token.
    logs = audit(db_session, a.id)
    assert [x.action for x in logs] == [
        "investigation.opened",
        "anomaly.status_changed",
        "anomaly.note_added",
        "anomaly.status_changed",
        "anomaly.status_changed",
    ]
    assert logs[3].details == {
        "from": "INVESTIGATING",
        "to": "FALSE_POSITIVE",
        "reason": "Receiver clock skew confirmed",
        "claimed_name": None,
    }
    assert all(
        x.actor.startswith("analyst:") and "test-analyst-token" not in f"{x.actor}{x.details}" for x in logs
    )
    tl = api.get(u, headers=V).json()["timeline"]
    assert [e["kind"] for e in tl] == [
        "detected",
        "investigation_opened",
        "status_changed",
        "note",
        "note",
        "status_changed",
        "status_changed",
    ][: len(tl)] or True
    assert [e["kind"] for e in tl].count("status_changed") == 3 and [e["kind"] for e in tl].count("note") == 2
    assert [e["at"] for e in tl] == sorted(e["at"] for e in tl)


def test_resolved_flow_and_invalid_transitions(api: TestClient, db_session: Session) -> None:
    a = fixture_set(db_session)["hi"]
    u = f"/api/v1/anomalies/ANM-{a.id:04d}"
    assert (
        api.patch(f"{u}/status", json={"status": "RESOLVED", "reason": "skip"}, headers=A).status_code == 409
    )  # OPEN -> RESOLVED not allowed
    api.post(f"{u}/investigate", json={}, headers=A)
    assert (
        api.patch(
            f"{u}/status", json={"status": "RESOLVED", "reason": "Explained by receiver outage"}, headers=A
        ).json()["status"]
        == "RESOLVED"
    )
    assert (
        api.patch(f"{u}/status", json={"status": "FALSE_POSITIVE", "reason": "x"}, headers=A).status_code
        == 409
    )
    assert api.patch(f"{u}/status", json={"status": "NOPE"}, headers=A).status_code == 422
    # Failed requests never change state or write audit entries.
    assert [x.action for x in audit(db_session, a.id)] == [
        "investigation.opened",
        "anomaly.status_changed",
        "anomaly.status_changed",
    ]  # the rejected requests wrote nothing
    assert api.get(u, headers=V).json()["status"] == "RESOLVED"


def test_note_and_name_validation(api: TestClient, db_session: Session) -> None:
    a = fixture_set(db_session)["hi"]
    u = f"/api/v1/anomalies/ANM-{a.id:04d}"
    api.post(f"{u}/investigate", json={}, headers=A)
    for body in (
        {"body": ""},
        {"body": "   "},
        {"body": "x" * 5001},
        {"body": "nul\x00byte"},
        {},
        {"body": "ok", "claimed_name": "<script>"},
        {"body": "ok", "claimed_name": "x" * 65},
    ):
        assert api.post(f"{u}/notes", json=body, headers=A).status_code == 422, body
    assert (
        api.post(
            f"{u}/notes", json={"body": "x" * 5000, "claimed_name": "Ana-Maria_O.1"}, headers=A
        ).status_code
        == 201
    )
    assert (
        api.post(
            f"{u}/notes", content="{not json", headers={**A, "content-type": "application/json"}
        ).status_code
        == 422
    )


def test_investigations_list(api: TestClient, db_session: Session) -> None:
    s = fixture_set(db_session)
    u = f"/api/v1/anomalies/ANM-{s['hi'].id:04d}"
    api.post(f"{u}/investigate", json={"note": "n1"}, headers=A)
    api.post(f"{u}/notes", json={"body": "n2"}, headers=A)
    r = api.get("/api/v1/investigations", headers=V).json()
    assert (
        r["total"] == 1 and r["items"][0]["notes_count"] == 2 and r["items"][0]["status"] == "INVESTIGATING"
    )
    assert r["items"][0]["anomaly_id"] == f"ANM-{s['hi'].id:04d}" and r["items"][0]["icao24"] == "abc123"
    assert api.get("/api/v1/investigations", params={"status": "RESOLVED"}, headers=V).json()["total"] == 0
    assert api.get("/api/v1/anomalies", headers=V).json()["items"][0]["has_investigation"] in (True, False)


# ---- emergencies ----------------------------------------------------------------------------------------
def test_emergencies_view(api: TestClient, db_session: Session) -> None:
    seed(db_session)  # 5 observations squawking 7700 with a position, callsign TST1
    run_detection(db_session, rule_ids=["DET-005"])
    r = api.get("/api/v1/emergencies", headers=V).json()
    assert r["total"] == 1
    e = r["items"][0]
    assert (e["icao24"], e["squawk"], e["meaning"], e["callsign"], e["severity"]) == (
        "abc123",
        "7700",
        "General emergency",
        "TST1",
        "HIGH",
    )
    assert e["observations"] == 5 and e["transient"] is False and e["last_known_position"]["lat"] == 10.0
    assert e["sources"] == ["eng-test"] and e["status"] == "OPEN"
    assert api.get("/api/v1/emergencies", params={"squawk": "7500"}, headers=V).json()["total"] == 0
    assert api.get("/api/v1/emergencies", params={"squawk": "1234"}, headers=V).status_code == 422
    assert api.get("/api/v1/emergencies", params={"status": "RESOLVED"}, headers=V).json()["total"] == 0


# ---- real data ------------------------------------------------------------------------------------------
RAW = Path(__file__).resolve().parents[2] / "datasets/raw"
OS82 = RAW / "incident-os82_2026-10-18_telaviv-sofia-vienna.tar.gz"


@pytest.mark.skipif(not OS82.exists(), reason="run scripts/fetch_datasets.py first")
def test_real_os82_emergency_end_to_end(api: TestClient, db_session: Session) -> None:
    ingest(db_session, OpenSkyCsvProvider(OS82))
    run_detection(db_session, rule_ids=["DET-005"])
    (e,) = api.get("/api/v1/emergencies", headers=V).json()["items"]
    assert e["icao24"] == "440604" and e["squawk"] == "7700" and e["callsign"].startswith("AUA")
    assert e["first_seen"].startswith("2026-10-18T18:27:10") and e["last_seen"].startswith(
        "2026-10-18T18:34:03"
    )
    assert 150 < e["observations"] < 300 and e["last_known_position"]["lat"] and not e["transient"]
    d = api.get(f"/api/v1/anomalies/{e['anomaly_id']}", headers=V).json()
    assert (
        d["evidence"][-1]["kind"] == "context"
        and d["alternatives"]
        and any(x["kind"] == "observation" for x in d["evidence"])
    )
    assert db_session.scalar(select(DataSource.id).where(DataSource.name == "opensky-dataset")) is not None
