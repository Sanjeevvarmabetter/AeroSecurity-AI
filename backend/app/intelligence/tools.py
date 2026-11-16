"""The ONLY capabilities the chat assistant has. Strict allowlist; every tool is read-only; arguments are validated
by Pydantic (extra keys rejected); result sizes are capped; each result lists the record ids it exposes so that the
final answer can be checked for grounded citations. The model never sees or writes SQL."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.security import Role
from app.intelligence.context import clean
from app.models import Anomaly
from app.services import anomalies as anomaly_svc
from app.services import aviation as aviation_svc
from app.services.aviation import NotFoundError
from app.threat_intel import service as intel_svc

ICAO = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{6}$")]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Status = Literal["OPEN", "INVESTIGATING", "FALSE_POSITIVE", "RESOLVED"]


class ToolError(Exception):
    """Reported back to the model as a tool result so it can correct itself. Never a server error."""


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _TimeRange(_Args):
    start: datetime | None = None
    end: datetime | None = None

    @field_validator("start", "end")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must include a timezone, e.g. 2026-10-18T18:00:00Z")
        return v


class SearchAircraftArgs(_Args):
    q: Annotated[
        str, Field(pattern=r"^[A-Za-z0-9-]{1,16}$", description="ICAO24, registration or callsign prefix")
    ]
    limit: Annotated[int, Field(ge=1, le=10)] = 5


class AircraftHistoryArgs(_TimeRange):
    icao24: ICAO
    limit: Annotated[int, Field(ge=1, le=30)] = 15
    order: Literal["asc", "desc"] = "desc"


class AircraftAnomaliesArgs(_Args):
    icao24: ICAO
    severity: list[Severity] | None = None
    status: list[Status] | None = None
    limit: Annotated[int, Field(ge=1, le=20)] = 10


class SearchAnomaliesArgs(_Args):
    severity: list[Severity] | None = None
    status: list[Status] | None = None
    rule_id: Annotated[str | None, Field(pattern=r"^DET-\d{3}$")] = None
    limit: Annotated[int, Field(ge=1, le=20)] = 10


class EmergencyArgs(_Args):
    squawk: Literal["7500", "7600", "7700"] | None = None
    status: list[Status] | None = None
    limit: Annotated[int, Field(ge=1, le=15)] = 10


class AirportStatsArgs(_Args):
    airport_code: Annotated[str, Field(pattern=r"^[A-Za-z0-9]{2,8}$")]
    radius_km: Annotated[int, Field(ge=5, le=100)] = 25


class TrajectoryArgs(_TimeRange):
    icao24: ICAO
    gap_s: Annotated[float, Field(gt=0, le=3600)] = 120.0


class InvestigationSummaryArgs(_Args):
    icao24: ICAO | None = None
    anomaly_id: Annotated[str | None, Field(pattern=r"^ANM-\d{1,9}$")] = None

    @model_validator(mode="after")
    def _one(self) -> "InvestigationSummaryArgs":
        if self.icao24 is None and self.anomaly_id is None:
            raise ValueError("provide icao24 or anomaly_id")
        return self


class ThreatIntelArgs(_Args):
    query: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 .\-+]{1,99}$")]
    limit: Annotated[int, Field(ge=1, le=5)] = 3


@dataclass
class ToolResult:
    data: dict[str, Any]
    refs: set[str] = field(default_factory=set)  # record ids exposed to the model, usable as citations


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    args: type[_Args]
    run: Callable[[Session, Any], ToolResult]
    min_role: Role = Role.VIEWER


def _ac(icao: object) -> str:
    return f"AC:{str(icao).lower()}"


# -- executors ----------------------------------------------------------------------------------------
def _search_aircraft(s: Session, a: SearchAircraftArgs) -> ToolResult:
    page = aviation_svc.search_aircraft(s, a.q, a.limit, 0, "last_seen")
    items = [
        {
            "icao24": x.icao24,
            "registration": x.registration,
            "type": x.aircraft_type,
            "callsign": x.last_callsign,
            "first_seen": _iso(x.first_seen),
            "last_seen": _iso(x.last_seen),
        }
        for x in page.items
    ]
    return ToolResult({"total_matches": page.total, "aircraft": items}, {_ac(x["icao24"]) for x in items})


def _history(s: Session, a: AircraftHistoryArgs) -> ToolResult:
    page = aviation_svc.aircraft_history(s, a.icao24, a.start, a.end, a.limit, 0, a.order)
    rows = [
        {
            "t": _iso(o.observed_at),
            "lat": _r(o.lat),
            "lon": _r(o.lon),
            "baro_alt_m": _r(o.baro_altitude_m, 0),
            "speed_ms": _r(o.velocity_ms, 1),
            "squawk": o.squawk,
            "callsign": o.callsign,
            "issues": o.validation_issues or None,
        }
        for o in page.items
    ]
    return ToolResult(
        {
            "icao24": a.icao24.lower(),
            "total_observations_in_range": page.total,
            "returned": len(rows),
            "order": a.order,
            "observations": rows,
        },
        {_ac(a.icao24), f"OBS:{a.icao24.lower()}"},
    )


def _anomalies(s: Session, a: AircraftAnomaliesArgs) -> ToolResult:
    p = anomaly_svc.list_anomalies(
        s,
        severity=a.severity,
        status=a.status,
        detection_type=None,
        rule_id=None,
        icao24=a.icao24,
        airport=None,
        min_confidence=None,
        start=None,
        end=None,
        sort="severity",
        order="desc",
        limit=a.limit,
        offset=0,
    )
    items: list[dict[str, Any]] = [_anomaly_row(x) for x in p.items if (x.icao24 or "") == a.icao24.lower()]
    return ToolResult(
        {"icao24": a.icao24.lower(), "total": len(items), "anomalies": items},
        {x["anomaly_id"] for x in items} | {_ac(a.icao24)},
    )


def _search_anomalies(s: Session, a: SearchAnomaliesArgs) -> ToolResult:
    p = anomaly_svc.list_anomalies(
        s,
        severity=a.severity,
        status=a.status,
        detection_type=None,
        rule_id=a.rule_id,
        icao24=None,
        airport=None,
        min_confidence=None,
        start=None,
        end=None,
        sort="severity",
        order="desc",
        limit=a.limit,
        offset=0,
    )
    items: list[dict[str, Any]] = [
        {**_anomaly_row(x), "icao24": x.icao24, "registration": x.registration} for x in p.items
    ]
    refs = {str(x["anomaly_id"]) for x in items} | {_ac(x["icao24"]) for x in items if x["icao24"]}
    return ToolResult({"total_matching": p.total, "returned": len(items), "anomalies": items}, refs)


def _emergencies(s: Session, a: EmergencyArgs) -> ToolResult:
    p = anomaly_svc.list_emergencies(
        s, squawk=a.squawk, status=a.status, start=None, end=None, limit=a.limit, offset=0
    )
    items = [
        {
            "anomaly_id": e.anomaly_id,
            "icao24": e.icao24,
            "registration": e.registration,
            "callsign": e.callsign,
            "squawk": e.squawk,
            "meaning": e.meaning,
            "severity": e.severity,
            "status": e.status,
            "first_seen": _iso(e.first_seen),
            "last_seen": _iso(e.last_seen),
            "duration_s": round(e.duration_s),
            "observations": e.observations,
            "transient": e.transient,
            "last_known_position": e.last_known_position,
        }
        for e in p.items
    ]
    return ToolResult(
        {"total": p.total, "events": items},
        {str(e["anomaly_id"]) for e in items} | {_ac(e["icao24"]) for e in items},
    )


def _airport_stats(s: Session, a: AirportStatsArgs) -> ToolResult:
    ap = aviation_svc.get_airport(s, a.airport_code)
    radius = a.radius_km * 1000
    rows = s.execute(
        text(
            """
        SELECT date_trunc('hour', o.observed_at) AS hour, count(DISTINCT o.aircraft_id) AS aircraft, count(*) AS obs
        FROM aircraft_observations o
        WHERE ST_DWithin(o.position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :deg)
          AND ST_DWithin(o.position::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :m)
        GROUP BY 1 ORDER BY 3 DESC LIMIT 24
        """
        ),
        {"lon": ap.lon, "lat": ap.lat, "deg": radius / 111_000 * 3, "m": radius},
    ).all()
    distinct = s.execute(
        text(
            """SELECT count(DISTINCT aircraft_id) FROM aircraft_observations
           WHERE ST_DWithin(position, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :deg)
             AND ST_DWithin(position::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :m)"""
        ),
        {"lon": ap.lon, "lat": ap.lat, "deg": radius / 111_000 * 3, "m": radius},
    ).scalar_one()
    flagged = (
        s.scalar(select(func.count()).select_from(Anomaly).where(Anomaly.airport_ident == ap.ident)) or 0
    )
    return ToolResult(
        {
            "airport": {
                "ident": ap.ident,
                "iata": ap.iata_code,
                "name": ap.name,
                "type": ap.airport_type,
                "country": ap.iso_country,
                "elevation_ft": ap.elevation_ft,
                "lat": _r(ap.lat),
                "lon": _r(ap.lon),
            },
            "radius_km": a.radius_km,
            "distinct_aircraft_observed_nearby": distinct,
            "busiest_hours": [{"hour": _iso(h), "aircraft": n, "observations": o} for h, n, o in rows],
            "traffic_anomalies_flagged": flagged,
            "caveat": "Counts only reflect aircraft in the stored data and receiver coverage; sparse data means low counts, "
            "not low real traffic. Arrivals/departures are not inferred.",
        },
        {f"AP:{ap.ident}"},
    )


def _trajectory(s: Session, a: TrajectoryArgs) -> ToolResult:
    t = aviation_svc.trajectory(s, a.icao24, a.start, a.end, a.gap_s)
    sm = t.summary
    gaps = [
        {"from": _iso(x.start), "to": _iso(x.end), "seconds": round(x.dt_s)} for x in t.segments if x.is_gap
    ][:10]
    return ToolResult(
        {
            "icao24": a.icao24.lower(),
            "positions": sm.points,
            "start": _iso(sm.start),
            "end": _iso(sm.end),
            "duration_s": round(sm.duration_s),
            "observed_distance_km": round(sm.observed_distance_m / 1000, 1),
            "gap_count": sm.gap_count,
            "longest_gap_s": round(sm.longest_gap_s),
            "gaps": gaps,
            "median_interval_s": sm.median_interval_s,
            "max_reported_speed_ms": sm.max_reported_speed_ms,
            "baro_altitude_range_m": [sm.min_baro_altitude_m, sm.max_baro_altitude_m],
            "first_position": _pos(t.points[0]) if t.points else None,
            "last_position": _pos(t.points[-1]) if t.points else None,
            "notes": t.notes,
        },
        {f"TRAJ:{a.icao24.lower()}", _ac(a.icao24)},
    )


def _summary(s: Session, a: InvestigationSummaryArgs) -> ToolResult:
    """Deterministic dossier (no LLM involved)."""
    if a.anomaly_id:
        d = anomaly_svc.anomaly_detail(s, a.anomaly_id)
        icao = d.icao24
        head: dict[str, Any] = {
            "anomaly": {
                "anomaly_id": d.anomaly_id,
                "title": d.title,
                "severity": d.severity,
                "status": d.status,
                "confidence_in_data_pattern": d.confidence,
                "rule": f"{d.rule.id} v{d.rule.version}",
                "event_start": _iso(d.event_start),
                "event_end": _iso(d.event_end),
                "metrics": d.summary,
                "alternatives": d.alternatives,
            }
        }
        refs = {d.anomaly_id}
    else:
        icao, head, refs = a.icao24, {}, set()
    out: dict[str, Any] = {**head}
    if icao:
        ac = aviation_svc.aircraft_detail(s, icao)
        out["aircraft"] = {
            "icao24": ac.icao24,
            "registration": ac.registration,
            "type": ac.aircraft_type,
            "operator": ac.operator,
            "observations": ac.observation_count,
            "first_seen": _iso(ac.first_seen),
            "last_seen": _iso(ac.last_seen),
            "callsigns": ac.callsigns,
            "sources": ac.observation_sources,
        }
        refs.add(_ac(icao))
        lst = _anomalies(s, AircraftAnomaliesArgs(icao24=icao, limit=10))
        out["detections"] = lst.data["anomalies"]
        refs |= lst.refs
        out["trajectory"] = _trajectory(s, TrajectoryArgs(icao24=icao)).data
    return ToolResult(out, refs)


def _intel(s: Session, a: ThreatIntelArgs) -> ToolResult:
    items, total = intel_svc.search(s, a.query, a.limit, 0)
    docs = [
        {
            "ref": f"DOC:{i.id}",
            "title": i.title,
            "authors": i.authors,
            "published": str(i.publication_date or "unknown"),
            "source": i.source_name,
            "url": i.source_url,
            "excerpt": i.excerpt[:700],
            "reliability": i.reliability_notes,
        }
        for i in items
    ]
    return ToolResult(
        {
            "total_matches": total,
            "documents": docs,
            "note": "external research context only; not evidence about this platform's data",
        },
        {str(d["ref"]) for d in docs},
    )


def _anomaly_row(x: Any) -> dict[str, Any]:
    return {
        "anomaly_id": x.anomaly_id,
        "rule": x.rule_id,
        "title": x.title,
        "severity": x.severity,
        "status": x.status,
        "confidence_in_data_pattern": x.confidence,
        "event_start": _iso(x.event_start),
        "event_end": _iso(x.event_end),
    }


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _r(v: float | None, n: int = 4) -> float | None:
    return None if v is None else round(v, n)


def _pos(p: Any) -> dict[str, float]:
    return {"lat": round(p.lat, 4), "lon": round(p.lon, 4)}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "search_aircraft",
            "Find aircraft by ICAO24, registration or callsign prefix.",
            SearchAircraftArgs,
            _search_aircraft,
        ),
        Tool(
            "get_aircraft_history",
            "Recent/ranged observations of one aircraft (compact rows).",
            AircraftHistoryArgs,
            _history,
        ),
        Tool(
            "get_aircraft_anomalies",
            "Detections recorded for one aircraft.",
            AircraftAnomaliesArgs,
            _anomalies,
        ),
        Tool(
            "search_anomalies",
            "Search detections across ALL aircraft by severity, status or rule (use for fleet-wide questions).",
            SearchAnomaliesArgs,
            _search_anomalies,
        ),
        Tool(
            "get_emergency_events", "Emergency squawk (7500/7600/7700) events.", EmergencyArgs, _emergencies
        ),
        Tool(
            "get_airport_statistics",
            "Stored traffic near an airport (counts only; no arrival/departure inference).",
            AirportStatsArgs,
            _airport_stats,
        ),
        Tool(
            "get_flight_trajectory",
            "Trajectory summary and observation gaps for one aircraft.",
            TrajectoryArgs,
            _trajectory,
        ),
        Tool(
            "generate_investigation_summary",
            "Deterministic dossier for an aircraft or an anomaly (no AI involved).",
            InvestigationSummaryArgs,
            _summary,
        ),
        Tool(
            "search_threat_intel", "Search stored public research/intel documents.", ThreatIntelArgs, _intel
        ),
    )
}


def catalog() -> str:
    """Human/model readable tool list with JSON schemas, included in the system prompt."""
    import json

    return "\n".join(
        f"- {t.name}: {t.description} arguments schema: {json.dumps(t.args.model_json_schema().get('properties', {}))}"
        for t in TOOLS.values()
    )


def execute(session: Session, name: str, raw_args: dict[str, Any], role: Role, max_chars: int) -> ToolResult:
    """Validate and run an allowlisted tool. Raises ToolError (safe to show the model) on any problem."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"unknown tool '{name}'; allowed tools: {', '.join(TOOLS)}")
    if role < tool.min_role:
        raise ToolError(f"tool '{name}' is not permitted for your role")
    try:
        args = tool.args.model_validate(raw_args)
    except ValidationError as exc:
        msg = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()[:4]
        )
        raise ToolError(f"invalid arguments: {msg}") from exc
    try:
        res = tool.run(session, args)
    except NotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except aviation_svc.TooLargeError as exc:
        raise ToolError(str(exc)) from exc
    res.data = clean(res.data, 400)
    import json

    if len(json.dumps(res.data, default=str)) > max_chars:  # hard cap: shrink the biggest list until it fits
        for k in sorted(res.data, key=lambda k: -len(json.dumps(res.data[k], default=str))):
            while (
                isinstance(res.data.get(k), list)
                and len(res.data[k]) > 1
                and len(json.dumps(res.data, default=str)) > max_chars
            ):
                res.data[k] = res.data[k][:-1]
                res.data["truncated"] = True
    return res
