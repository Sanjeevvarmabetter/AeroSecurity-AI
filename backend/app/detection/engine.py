"""Runs rules over stored data and persists findings. Re-running is idempotent and reproducible."""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.detection.rules import AIRCRAFT_RULES, AIRPORT_RULES, ALL_RULES
from app.detection.types import AircraftInfo, AirportTraffic, Finding, Obs
from app.models import Aircraft, AircraftObservation, Anomaly, AuditLog, DataSource, DetectionRule, Evidence

log = logging.getLogger(__name__)
_OPEN_STATES = ("OPEN", "INVESTIGATING")


@dataclass
class RuleStats:
    findings: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class RunReport:
    aircraft_processed: int = 0
    airports_processed: int = 0
    observations_read: int = 0
    rules: dict[str, RuleStats] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "aircraft_processed": self.aircraft_processed,
            "airports_processed": self.airports_processed,
            "observations_read": self.observations_read,
            "rules": {k: vars(v) for k, v in sorted(self.rules.items())},
        }


def sync_rule_registry(session: Session) -> dict[str, DetectionRule]:
    """Ensure every implemented rule has a registry row. Operator-set `config`/`enabled` are preserved."""
    rows = {r.id: r for r in session.scalars(select(DetectionRule))}
    for rid, cls in ALL_RULES.items():
        row = rows.get(rid)
        if row is None:
            row = DetectionRule(
                id=rid, name=cls.name, description=cls.description, version=cls.version, config={}
            )
            session.add(row)
            rows[rid] = row
        else:
            row.name, row.description, row.version = cls.name, cls.description, cls.version
    session.commit()
    return rows


def _config_for(row: DetectionRule, cls: Any) -> BaseModel:
    """Defaults merged with the operator's JSONB overrides; unknown keys are rejected (extra=forbid)."""
    return cls.config_model.model_validate(row.config or {})  # type: ignore[no-any-return]


def load_observations(
    session: Session, aircraft_id: int, start: datetime | None = None, end: datetime | None = None
) -> list[Obs]:
    Ob = AircraftObservation  # noqa: N806
    q = (
        select(Ob, func.ST_Y(Ob.position), func.ST_X(Ob.position), DataSource.name)
        .join(DataSource, DataSource.id == Ob.data_source_id)
        .where(Ob.aircraft_id == aircraft_id)
        .order_by(Ob.observed_at, Ob.id)
    )
    if start:
        q = q.where(Ob.observed_at >= start)
    if end:
        q = q.where(Ob.observed_at <= end)
    return [
        Obs(
            id=o.id,
            t=o.observed_at,
            lat=lat,
            lon=lon,
            baro_altitude_m=o.baro_altitude_m,
            geo_altitude_m=o.geo_altitude_m,
            on_ground=o.on_ground,
            velocity_ms=o.velocity_ms,
            heading_deg=o.heading_deg,
            vertical_rate_ms=o.vertical_rate_ms,
            squawk=o.squawk,
            callsign=o.callsign,
            position_source=o.position_source,
            source=src,
            last_contact=o.last_contact_at,
            ingested_at=o.created_at,
            issues=tuple((o.raw or {}).get("issues", ())),
        )
        for o, lat, lon, src in session.execute(q)
    ]


def load_airport_traffic(session: Session, radius_m: float) -> list[AirportTraffic]:
    """Distinct aircraft per hour within radius of each (non-heliport) airport. The degree pre-filter uses the
    GiST index; the geography test makes it exact."""
    rows = session.execute(
        text(
            """
            SELECT ap.ident, ap.name, date_trunc('hour', o.observed_at) AS hour,
                   count(DISTINCT o.aircraft_id) AS n
            FROM aircraft_observations o
            JOIN airports ap
              ON ST_DWithin(o.position, ap.position, :deg)
             AND ST_DWithin(o.position::geography, ap.position::geography, :m)
            WHERE ap.airport_type IN ('large_airport', 'medium_airport', 'small_airport')
            GROUP BY 1, 2, 3
            """
        ),
        {"deg": radius_m / 111_000 * 3, "m": radius_m},
    )
    by_airport: dict[str, tuple[str, dict[datetime, int]]] = {}
    for ident, name, hour, n in rows:
        by_airport.setdefault(ident, (name, {}))[1][hour] = n
    return [AirportTraffic(i, nm, h) for i, (nm, h) in by_airport.items()]


def _fingerprint(f: Finding, summary: dict[str, Any]) -> tuple[Any, ...]:
    return (f.event_end, f.severity.value, round(f.confidence, 3), f.description, summary)


def persist(
    session: Session, f: Finding, rule: DetectionRule, aircraft_id: int | None, stats: RuleStats
) -> None:
    existing = session.scalar(
        select(Anomaly).where(
            Anomaly.rule_id == rule.id, Anomaly.rule_version == rule.version, Anomaly.dedup_key == f.dedup_key
        )
    )
    summary = {**f.summary, "alternative_explanations": list(f.alternatives)}
    stats.findings += 1
    if existing is not None:
        same = (
            existing.event_end,
            existing.severity,
            round(existing.confidence, 3),
            existing.description,
            existing.summary,
        ) == _fingerprint(f, summary)
        if same or existing.status not in _OPEN_STATES:
            stats.unchanged += 1  # never rewrite a finding an analyst has closed
            return
        existing.event_end, existing.severity, existing.confidence = (
            f.event_end,
            f.severity.value,
            f.confidence,
        )
        existing.description, existing.summary, existing.data_quality = (
            f.description,
            summary,
            f.data_quality.value,
        )
        session.query(Evidence).where(Evidence.anomaly_id == existing.id).delete()
        _add_evidence(session, existing.id, f)
        stats.updated += 1
        return
    a = Anomaly(
        rule_id=rule.id,
        rule_version=rule.version,
        aircraft_id=aircraft_id,
        airport_ident=f.airport_ident,
        detection_type=f.detection_type,
        title=f.title[:200],
        description=f.description,
        severity=f.severity.value,
        confidence=f.confidence,
        data_quality=f.data_quality.value,
        status="OPEN",
        event_start=f.event_start,
        event_end=f.event_end,
        dedup_key=f.dedup_key,
        source_refs=list(f.sources),
        summary=summary,
    )
    session.add(a)
    session.flush()
    _add_evidence(session, a.id, f)
    stats.created += 1


def _add_evidence(session: Session, anomaly_id: int, f: Finding) -> None:
    session.add_all(
        Evidence(
            anomaly_id=anomaly_id, ordinal=i, kind=e.kind, observation_id=e.observation_id, payload=e.payload
        )
        for i, e in enumerate(f.evidence)
    )


def run_detection(
    session: Session,
    *,
    rule_ids: list[str] | None = None,
    icao24: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    actor: str = "system",
) -> RunReport:
    registry = sync_rule_registry(session)
    selected = [r for r in (rule_ids or list(ALL_RULES)) if r in ALL_RULES and registry[r].enabled]
    unknown = set(rule_ids or []) - set(ALL_RULES)
    if unknown:
        raise ValueError(f"unknown rule(s): {sorted(unknown)}")
    report = RunReport(rules={r: RuleStats() for r in selected})

    air_rules = {
        r: AIRCRAFT_RULES[r](_config_for(registry[r], AIRCRAFT_RULES[r]))
        for r in selected
        if r in AIRCRAFT_RULES
    }
    if air_rules:
        q = select(Aircraft).order_by(Aircraft.icao24)
        if icao24:
            q = q.where(Aircraft.icao24 == icao24.lower())
        for ac in list(session.scalars(q)):
            obs = load_observations(session, ac.id, start, end)
            if not obs:
                continue
            report.aircraft_processed += 1
            report.observations_read += len(obs)
            info = AircraftInfo(ac.icao24, ac.registration, ac.aircraft_type)
            for rid, rule in air_rules.items():
                for finding in rule.detect(info, obs):
                    persist(session, finding, registry[rid], ac.id, report.rules[rid])
            session.commit()

    for rid in (r for r in selected if r in AIRPORT_RULES):
        arule = AIRPORT_RULES[rid](_config_for(registry[rid], AIRPORT_RULES[rid]))
        radius = float(getattr(arule.cfg, "radius_m", 10_000.0))
        for traffic in load_airport_traffic(session, radius):
            report.airports_processed += 1
            for finding in arule.detect(traffic):
                persist(session, finding, registry[rid], None, report.rules[rid])
        session.commit()

    session.add(
        AuditLog(
            actor=actor,
            action="detection.run",
            entity_type="detection",
            details={"selected": selected, "icao24": icao24, **report.as_dict()},
        )
    )
    session.commit()
    log.info("detection run: %s", report.as_dict())
    return report


def summarize_anomalies(session: Session) -> dict[str, Counter[str]]:
    out: dict[str, Counter[str]] = {"by_rule": Counter(), "by_severity": Counter()}
    for rule_id, sev in session.execute(select(Anomaly.rule_id, Anomaly.severity)):
        out["by_rule"][rule_id] += 1
        out["by_severity"][sev] += 1
    return out


__all__ = ["RunReport", "run_detection", "summarize_anomalies", "sync_rule_registry"]
