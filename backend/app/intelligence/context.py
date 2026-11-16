"""Builds the bounded, sanitised context handed to the model, plus the evidence references it may cite.

Everything that originated outside this system (callsigns, free text, provider payloads) is untrusted: control
characters are removed, angle brackets are neutralised so data cannot close the <data> block, and lengths are
capped. The context carries only what the analysis needs (no tokens, no user identities)."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.models import Aircraft, AircraftObservation, Airport, Anomaly, DataSource
from app.schemas.anomaly import AnomalyDetail
from app.schemas.aviation import TrajectoryResponse
from app.services.anomalies import anomaly_detail, public_id
from app.services.aviation import NotFoundError, aircraft_detail, trajectory

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_EVIDENCE = 30
MAX_ANOMALIES = 15
MAX_AIRPORTS = 3
NEARBY_AIRPORT_RADIUS_M = 100_000


@dataclass(frozen=True, slots=True)
class AIContext:
    data: dict[str, Any]
    allowed_refs: frozenset[str]
    text: str  # compact JSON actually sent to the model

    @property
    def chars(self) -> int:
        return len(self.text)


def clean(value: Any, limit: int = 200) -> Any:
    """Recursively sanitise untrusted values for inclusion in the model prompt."""
    if isinstance(value, str):
        v = _CTRL.sub("", value).replace("<", "‹").replace(">", "›").strip()
        return v[:limit] + ("…" if len(v) > limit else "")
    if isinstance(value, dict):
        return {str(clean(k, 60)): clean(v, limit) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [clean(v, limit) for v in value[:60]]
    if isinstance(value, float):
        return round(value, 4)
    return value


def _fit(data: dict[str, Any], max_chars: int, shrinkable: list[str]) -> str:
    """Serialise, dropping trailing items of the named list fields until under the budget."""
    text = json.dumps(data, separators=(",", ":"), default=str)
    for key in shrinkable:
        while len(text) > max_chars and isinstance(data.get(key), list) and len(data[key]) > 1:
            data[key] = data[key][:-1]
            data["truncated"] = True
            text = json.dumps(data, separators=(",", ":"), default=str)
    if len(text) > max_chars:
        raise NotFoundError("context too large to analyse within the configured limit")
    return text


def build_anomaly_context(
    session: Session, anomaly_id: str, max_chars: int
) -> tuple[AIContext, AnomalyDetail]:
    d = anomaly_detail(session, anomaly_id)
    evidence = [
        {"ref": f"E{e.ordinal}", "kind": e.kind, "data": clean(e.payload, 120)}
        for e in d.evidence[:MAX_EVIDENCE]
    ]
    allowed = {"RULE", "AC"} | {e["ref"] for e in evidence}
    data: dict[str, Any] = {
        "RULE": clean(
            {
                "id": d.rule.id,
                "name": d.rule.name,
                "description": d.rule.description,
                "version": d.rule.version,
            }
        ),
        "detection": clean(
            {
                "anomaly_id": d.anomaly_id,
                "title": d.title,
                "description": d.description,
                "severity": d.severity,
                "confidence_in_data_pattern": d.confidence,
                "data_quality": d.data_quality,
                "event_start": d.event_start.isoformat(),
                "event_end": d.event_end.isoformat(),
                "sources": d.source_refs,
                "metrics": d.summary,
            }
        ),
        "detection_notes": "severity and confidence come from a deterministic rule and must not be changed",
        "known_alternatives_from_rule": clean(d.alternatives),
        "AC": clean({"icao24": d.icao24, "registration": d.registration}) if d.icao24 else None,
        "evidence": evidence,
    }
    if d.icao24:
        others = session.execute(
            select(Anomaly, Aircraft.icao24)
            .join(Aircraft, Aircraft.id == Anomaly.aircraft_id)
            .where(Aircraft.icao24 == d.icao24, Anomaly.id != d.id)
            .order_by(Anomaly.event_start)
            .limit(MAX_ANOMALIES)
        ).all()
        related = []
        for i, (a, _) in enumerate(others, start=1):
            related.append(
                clean(
                    {
                        "ref": f"A{i}",
                        "anomaly_id": public_id(a.id),
                        "title": a.title,
                        "severity": a.severity,
                        "event_start": a.event_start.isoformat(),
                        "rule": a.rule_id,
                    }
                )
            )
            allowed.add(f"A{i}")
        data["other_detections_for_this_aircraft"] = related
    text = _fit(data, max_chars, ["other_detections_for_this_aircraft", "evidence"])
    allowed = {r for r in allowed if r in text}  # drop refs for items trimmed away
    return AIContext(data, frozenset(allowed), text), d


def _nearest_airports(
    session: Session, lat: float, lon: float, label: str, start: int
) -> list[dict[str, Any]]:
    pt = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    dist = func.ST_Distance(cast(Airport.position, Geography), cast(pt, Geography))
    rows = session.execute(
        select(Airport.ident, Airport.iata_code, Airport.name, Airport.airport_type, dist.label("d"))
        .where(
            Airport.airport_type.in_(("large_airport", "medium_airport", "small_airport")),
            func.ST_DWithin(Airport.position, pt, 1.2),
        )
        .order_by("d")
        .limit(MAX_AIRPORTS)
    ).all()
    out = []
    for i, r in enumerate(rows):
        if r.d <= NEARBY_AIRPORT_RADIUS_M:
            out.append(
                clean(
                    {
                        "ref": f"AP{start + i}",
                        "near": label,
                        "ident": r.ident,
                        "iata": r.iata_code,
                        "name": r.name,
                        "type": r.airport_type,
                        "distance_km": round(r.d / 1000, 1),
                    }
                )
            )
    return out


def build_aircraft_context(session: Session, icao24: str, max_chars: int) -> tuple[AIContext, int]:
    ac = aircraft_detail(session, icao24)  # raises NotFoundError
    row = session.scalar(select(Aircraft).where(Aircraft.icao24 == icao24.lower()))
    if row is None:
        raise NotFoundError(f"aircraft {icao24.lower()} not found")
    traj: TrajectoryResponse = trajectory(session, icao24, None, None, 120.0)
    s = traj.summary
    anomalies = (
        session.execute(
            select(Anomaly)
            .where(Anomaly.aircraft_id == row.id)
            .order_by(Anomaly.event_start)
            .limit(MAX_ANOMALIES)
        )
        .scalars()
        .all()
    )
    allowed = {"AC", "TRAJ", "SRC"}
    related = []
    for i, a in enumerate(anomalies, start=1):
        related.append(
            clean(
                {
                    "ref": f"A{i}",
                    "anomaly_id": public_id(a.id),
                    "rule": a.rule_id,
                    "title": a.title,
                    "severity": a.severity,
                    "confidence_in_data_pattern": a.confidence,
                    "status": a.status,
                    "event_start": a.event_start.isoformat(),
                    "event_end": a.event_end.isoformat(),
                    "metrics": a.summary
                    and {k: v for k, v in a.summary.items() if k != "alternative_explanations"},
                }
            )
        )
        allowed.add(f"A{i}")
    airports: list[dict[str, Any]] = []
    if traj.points:
        airports += _nearest_airports(
            session, traj.points[0].lat, traj.points[0].lon, "first observed position", 1
        )
        airports += _nearest_airports(
            session, traj.points[-1].lat, traj.points[-1].lon, "last observed position", len(airports) + 1
        )
    allowed |= {a["ref"] for a in airports}
    sources = list(
        session.scalars(
            select(DataSource.name).where(
                DataSource.id.in_(
                    select(AircraftObservation.data_source_id)
                    .where(AircraftObservation.aircraft_id == row.id)
                    .distinct()
                )
            )
        )
    )
    data: dict[str, Any] = {
        "AC": clean(
            {
                "icao24": ac.icao24,
                "registration": ac.registration,
                "type": ac.aircraft_type,
                "manufacturer": ac.manufacturer,
                "model": ac.model,
                "operator": ac.operator,
                "country": ac.origin_country,
                "first_seen": _iso(ac.first_seen),
                "last_seen": _iso(ac.last_seen),
                "callsigns": ac.callsigns,
                "observation_count": ac.observation_count,
                "squawks_seen": [f"{q.squawk} x{q.observations}" for q in ac.squawks],
                "note": "null/missing fields are unknown; do not infer them",
            }
        ),
        "SRC": {"observation_sources": sources, "metadata_source": ac.metadata_source},
        "TRAJ": {
            "positions": s.points,
            "start": _iso(s.start),
            "end": _iso(s.end),
            "duration_s": round(s.duration_s),
            "observed_distance_km": round(s.observed_distance_m / 1000, 1),
            "observation_gaps": s.gap_count,
            "total_gap_s": round(s.gap_total_s),
            "longest_gap_s": round(s.longest_gap_s),
            "median_interval_s": s.median_interval_s,
            "baro_altitude_range_m": [s.min_baro_altitude_m, s.max_baro_altitude_m],
            "max_reported_speed_ms": s.max_reported_speed_ms,
            "first_position": traj.points[0].model_dump(mode="json", include={"lat", "lon"})
            if traj.points
            else None,
            "last_position": traj.points[-1].model_dump(mode="json", include={"lat", "lon"})
            if traj.points
            else None,
            "caveat": "derived speed from consecutive positions is unreliable for intervals under 1 s",
        },
        "detections": related,
        "airports": airports,
    }
    text = _fit(data, max_chars, ["detections", "airports"])
    return AIContext(
        data, frozenset(r for r in allowed if r in ("AC", "TRAJ", "SRC") or f'"{r}"' in text), text
    ), row.id


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None
