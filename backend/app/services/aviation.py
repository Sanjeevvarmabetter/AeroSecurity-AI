"""Read-side aviation queries. All SQL is parameterised via SQLAlchemy; search terms are pre-validated."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.aviation.aircraft_category import classify_aircraft_category
from app.aviation.trajectory import TrackPoint, build_segments, summarize
from app.models import Aircraft, AircraftObservation, Airport, DataSource
from app.schemas.aviation import (
    AircraftDetail,
    AircraftSummary,
    AirportOut,
    AirportTrafficOut,
    LatLon,
    LiveAircraft,
    LiveResponse,
    ObservationOut,
    SegmentOut,
    SquawkUse,
    TrackPointOut,
    TrajectoryResponse,
    TrajectorySummaryOut,
)
from app.schemas.common import Page

Obs = AircraftObservation
MAX_TRAJECTORY_POINTS = 50_000
LIVE_MAX_AIRCRAFT = 5_000


class NotFoundError(Exception):
    pass


class TooLargeError(Exception):
    pass


def _lat(col: Any) -> Any:
    return func.ST_Y(col)


def _lon(col: Any) -> Any:
    return func.ST_X(col)


# -- aircraft search / detail ------------------------------------------------------------------
def _latest_per_aircraft(session: Session, ids: list[int], *, positioned: bool) -> dict[int, tuple[Any, ...]]:
    q = select(Obs.aircraft_id, Obs.observed_at, Obs.callsign, _lat(Obs.position), _lon(Obs.position)).where(
        Obs.aircraft_id.in_(ids)
    )
    if positioned:
        q = q.where(Obs.position.is_not(None))
    q = q.ext(distinct_on(Obs.aircraft_id)).order_by(Obs.aircraft_id, Obs.observed_at.desc())
    return {r[0]: tuple(r[1:]) for r in session.execute(q)}


def _summaries(session: Session, rows: list[Aircraft]) -> list[AircraftSummary]:
    ids = [a.id for a in rows]
    if not ids:
        return []
    pos = _latest_per_aircraft(session, ids, positioned=True)
    anyobs = _latest_per_aircraft(session, ids, positioned=False)
    out = []
    for a in rows:
        p, o = pos.get(a.id), anyobs.get(a.id)
        out.append(
            AircraftSummary(
                icao24=a.icao24,
                registration=a.registration,
                aircraft_type=a.aircraft_type,
                category=classify_aircraft_category(a.aircraft_type, a.model),
                manufacturer=a.manufacturer,
                model=a.model,
                operator=a.operator,
                origin_country=a.origin_country,
                first_seen=a.first_seen,
                last_seen=a.last_seen,
                last_callsign=(p[1] if p and p[1] else (o[1] if o else None)),
                last_position=LatLon(lat=p[2], lon=p[3]) if p else None,
                last_position_at=p[0] if p else None,
            )
        )
    return out


def search_aircraft(
    session: Session, q: str | None, limit: int, offset: int, sort: Literal["last_seen", "icao24"]
) -> Page[AircraftSummary]:
    """`q` must already be validated as [A-Za-z0-9-]+ (no LIKE wildcards). Prefix match on icao24,
    registration or any observed callsign."""
    stmt = select(Aircraft)
    if q:
        needle = q.lower()
        upper = q.upper()
        callsign_hit = select(Obs.aircraft_id).where(Obs.callsign.like(f"{upper}%")).distinct()
        stmt = stmt.where(
            or_(
                Aircraft.icao24.like(f"{needle}%"),
                Aircraft.registration.like(f"{upper}%"),
                Aircraft.id.in_(callsign_hit),
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = Aircraft.icao24 if sort == "icao24" else Aircraft.last_seen.desc().nulls_last()
    rows = list(session.scalars(stmt.order_by(order, Aircraft.icao24).limit(limit).offset(offset)))
    return Page(items=_summaries(session, rows), total=total, limit=limit, offset=offset)


def _get_aircraft(session: Session, icao24: str) -> Aircraft:
    a = session.scalar(select(Aircraft).where(Aircraft.icao24 == icao24.lower()))
    if a is None:
        raise NotFoundError(f"aircraft {icao24.lower()} not found")
    return a


def aircraft_detail(session: Session, icao24: str) -> AircraftDetail:
    a = _get_aircraft(session, icao24)
    summary = _summaries(session, [a])[0]
    counts = session.execute(
        select(func.count(), func.count(Obs.position)).where(Obs.aircraft_id == a.id)
    ).one()
    callsigns = list(
        session.scalars(
            select(Obs.callsign)
            .where(Obs.aircraft_id == a.id, Obs.callsign.is_not(None))
            .distinct()
            .order_by(Obs.callsign)
            .limit(50)
        )
    )
    squawks = [
        SquawkUse(squawk=r[0], first_seen=r[1], last_seen=r[2], observations=r[3])
        for r in session.execute(
            select(Obs.squawk, func.min(Obs.observed_at), func.max(Obs.observed_at), func.count())
            .where(Obs.aircraft_id == a.id, Obs.squawk.is_not(None))
            .group_by(Obs.squawk)
            .order_by(func.min(Obs.observed_at))
        )
    ]
    sources = list(
        session.scalars(
            select(DataSource.name)
            .where(DataSource.id.in_(select(Obs.data_source_id).where(Obs.aircraft_id == a.id).distinct()))
            .order_by(DataSource.name)
        )
    )
    meta = session.get(DataSource, a.metadata_source_id) if a.metadata_source_id else None
    return AircraftDetail(
        **summary.model_dump(),
        observation_count=counts[0],
        positioned_count=counts[1],
        callsigns=callsigns,
        squawks=squawks,
        observation_sources=sources,
        metadata_source=meta.name if meta else None,
    )


# -- history ------------------------------------------------------------------------------------
def aircraft_history(
    session: Session,
    icao24: str,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    offset: int,
    order: Literal["asc", "desc"],
) -> Page[ObservationOut]:
    a = _get_aircraft(session, icao24)
    cond = [Obs.aircraft_id == a.id]
    if start:
        cond.append(Obs.observed_at >= start)
    if end:
        cond.append(Obs.observed_at <= end)
    total = session.scalar(select(func.count()).select_from(Obs).where(*cond)) or 0
    ordering = Obs.observed_at.asc() if order == "asc" else Obs.observed_at.desc()
    rows = session.execute(
        select(Obs, _lat(Obs.position), _lon(Obs.position), DataSource.name)
        .join(DataSource, DataSource.id == Obs.data_source_id)
        .where(*cond)
        .order_by(ordering, Obs.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        ObservationOut(
            id=o.id,
            observed_at=o.observed_at,
            last_contact_at=o.last_contact_at,
            callsign=o.callsign,
            lat=lat,
            lon=lon,
            baro_altitude_m=o.baro_altitude_m,
            geo_altitude_m=o.geo_altitude_m,
            on_ground=o.on_ground,
            velocity_ms=o.velocity_ms,
            heading_deg=o.heading_deg,
            vertical_rate_ms=o.vertical_rate_ms,
            squawk=o.squawk,
            position_source=o.position_source,
            source=src,
            validation_issues=list((o.raw or {}).get("issues", [])),
        )
        for o, lat, lon, src in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


# -- live / snapshot ------------------------------------------------------------------------------
def live_aircraft(
    session: Session,
    at: datetime | None,
    max_age_s: int,
    bbox: tuple[float, float, float, float] | None,  # lamin, lomin, lamax, lomax
    limit: int,
) -> LiveResponse:
    """Latest known position per aircraft within `max_age_s` before `at` (default: now).

    Passing `at` replays a historical moment, which is how offline datasets are viewed.
    """
    as_of = at or datetime.now(UTC)
    window_start = as_of - timedelta(seconds=max_age_s)
    cond = [Obs.observed_at <= as_of, Obs.observed_at >= window_start, Obs.position.is_not(None)]
    if bbox:
        lamin, lomin, lamax, lomax = bbox
        if lomin <= lomax:
            cond.append(Obs.position.op("&&")(func.ST_MakeEnvelope(lomin, lamin, lomax, lamax, 4326)))
        else:  # box crosses the antimeridian
            cond.append(
                or_(
                    Obs.position.op("&&")(func.ST_MakeEnvelope(lomin, lamin, 180, lamax, 4326)),
                    Obs.position.op("&&")(func.ST_MakeEnvelope(-180, lamin, lomax, lamax, 4326)),
                )
            )
    latest = (
        select(Obs, _lat(Obs.position).label("lat"), _lon(Obs.position).label("lon"))
        .where(and_(*cond))
        .ext(distinct_on(Obs.aircraft_id))
        .order_by(Obs.aircraft_id, Obs.observed_at.desc())
        .subquery()
    )
    rows = session.execute(
        select(
            latest,
            Aircraft.icao24,
            Aircraft.registration,
            Aircraft.aircraft_type,
            Aircraft.model,
            DataSource.name,
        )
        .join(Aircraft, Aircraft.id == latest.c.aircraft_id)
        .join(DataSource, DataSource.id == latest.c.data_source_id)
        .order_by(Aircraft.icao24)
        .limit(limit + 1)
    ).all()
    truncated = len(rows) > limit
    aircraft = [
        LiveAircraft(
            icao24=r.icao24,
            callsign=r.callsign,
            registration=r.registration,
            aircraft_type=r.aircraft_type,
            category=classify_aircraft_category(r.aircraft_type, r.model),
            squawk=r.squawk,
            lat=r.lat,
            lon=r.lon,
            heading_deg=r.heading_deg,
            velocity_ms=r.velocity_ms,
            baro_altitude_m=r.baro_altitude_m,
            vertical_rate_ms=r.vertical_rate_ms,
            on_ground=r.on_ground,
            observed_at=r.observed_at,
            age_s=(as_of - r.observed_at).total_seconds(),
            source=r.name,
        )
        for r in rows[:limit]
    ]
    newest = session.scalar(select(func.max(Obs.observed_at)).where(Obs.observed_at <= as_of))
    return LiveResponse(
        as_of=as_of,
        max_age_s=max_age_s,
        count=len(aircraft),
        truncated=truncated,
        latest_observation_at=newest,
        stale=newest is None or newest < window_start,
        aircraft=aircraft,
    )


# -- trajectory ------------------------------------------------------------------------------------
def trajectory(
    session: Session, icao24: str, start: datetime | None, end: datetime | None, gap_s: float
) -> TrajectoryResponse:
    a = _get_aircraft(session, icao24)
    cond = [Obs.aircraft_id == a.id, Obs.position.is_not(None)]
    if start:
        cond.append(Obs.observed_at >= start)
    if end:
        cond.append(Obs.observed_at <= end)
    rows = session.execute(
        select(
            Obs.observed_at,
            _lat(Obs.position),
            _lon(Obs.position),
            Obs.baro_altitude_m,
            Obs.geo_altitude_m,
            Obs.velocity_ms,
            Obs.vertical_rate_ms,
            Obs.on_ground,
        )
        .where(*cond)
        .order_by(Obs.observed_at)
        .limit(MAX_TRAJECTORY_POINTS + 1)
    ).all()
    if len(rows) > MAX_TRAJECTORY_POINTS:
        raise TooLargeError(f"more than {MAX_TRAJECTORY_POINTS} positions in range; narrow start/end")
    pts = [TrackPoint(*r) for r in rows]
    segs = build_segments(pts, gap_s)
    return TrajectoryResponse(
        icao24=a.icao24,
        start=start,
        end=end,
        gap_threshold_s=gap_s,
        summary=TrajectorySummaryOut(**asdict(summarize(pts, segs))),
        points=[
            TrackPointOut(
                t=p.t,
                lat=p.lat,
                lon=p.lon,
                baro_altitude_m=p.baro_altitude_m,
                geo_altitude_m=p.geo_altitude_m,
                reported_velocity_ms=p.velocity_ms,
            )
            for p in pts
        ],
        segments=[SegmentOut(**asdict(s)) for s in segs],
        notes=[
            "derived_speed_ms is ground displacement divided by elapsed time; reported_speed_ms is the "
            "provider-reported velocity. They are different quantities.",
            "Segments flagged is_gap were not observed; straight-line distance across them is excluded "
            "from observed_distance_m. No flight plan or route is inferred from these positions.",
        ],
    )


# -- airports ---------------------------------------------------------------------------------------
def _airport_out(a: Airport, lat: float, lon: float) -> AirportOut:
    return AirportOut(
        ident=a.ident,
        iata_code=a.iata_code,
        name=a.name,
        airport_type=a.airport_type,
        iso_country=a.iso_country,
        elevation_ft=a.elevation_ft,
        lat=lat,
        lon=lon,
    )


def search_airports(session: Session, q: str | None, limit: int, offset: int) -> Page[AirportOut]:
    """`q` pre-validated as [A-Za-z0-9-]+. Prefix match on ident, exact IATA, or name contains."""
    cond = []
    if q:
        cond.append(
            or_(
                Airport.ident.like(f"{q.upper()}%"),
                Airport.iata_code == q.upper(),
                Airport.name.ilike(f"%{q}%"),
            )
        )
    total = session.scalar(select(func.count()).select_from(Airport).where(*cond)) or 0
    big_first = (Airport.airport_type == "large_airport").desc()
    rows = session.execute(
        select(Airport, _lat(Airport.position), _lon(Airport.position))
        .where(*cond)
        .order_by(big_first, Airport.name, Airport.ident)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page(
        items=[_airport_out(a, la, lo) for a, la, lo in rows], total=total, limit=limit, offset=offset
    )


def get_airport(session: Session, code: str) -> AirportOut:
    c = code.upper()
    row = session.execute(
        select(Airport, _lat(Airport.position), _lon(Airport.position))
        .where(or_(Airport.ident == c, Airport.iata_code == c))
        .order_by(Airport.ident)
        .limit(1)
    ).first()
    if row is None:
        raise NotFoundError(f"airport {c} not found")
    return _airport_out(*row)


def get_airport_traffic(session: Session, code: str, radius_km: float = 25.0) -> AirportTrafficOut:
    c = code.upper()
    row = session.execute(
        select(Airport, _lat(Airport.position), _lon(Airport.position))
        .where(or_(Airport.ident == c, Airport.iata_code == c))
        .order_by(Airport.ident)
        .limit(1)
    ).first()
    if row is None:
        raise NotFoundError(f"airport {c} not found")
    ap, ap_lat, ap_lon = row
    radius_m = radius_km * 1000.0

    # Bounding box degree pre-filter for GiST spatial index, then geography for exact distance
    deg = radius_m / 111_000.0 * 2.5
    obs_rows = session.execute(
        text(
            """
            SELECT o.id, o.aircraft_id, o.observed_at, o.callsign,
                   o.baro_altitude_m, o.velocity_ms,
                   a.icao24, a.aircraft_type,
                   ST_Distance(o.position::geography, ap.position::geography) AS dist_m
            FROM aircraft_observations o
            JOIN aircraft a ON a.id = o.aircraft_id
            JOIN airports ap ON ap.id = :ap_id
            WHERE o.position IS NOT NULL
              AND ST_DWithin(o.position, ap.position, :deg)
              AND ST_DWithin(o.position::geography, ap.position::geography, :radius_m)
            ORDER BY o.observed_at DESC
            LIMIT 1000
            """
        ),
        {"ap_id": ap.id, "deg": deg, "radius_m": radius_m},
    ).all()

    total_obs = len(obs_rows)
    distinct_aircraft = {r.aircraft_id for r in obs_rows}

    # Hourly observation histogram
    hourly: dict[str, int] = {}
    for r in obs_rows:
        hr = r.observed_at.strftime("%Y-%m-%d %H:00")
        hourly[hr] = hourly.get(hr, 0) + 1
    hourly_series = [{"hour": h, "count": cnt} for h, cnt in sorted(hourly.items())]

    # Distinct recent aircraft (latest fix per aircraft)
    seen_ac: set[int] = set()
    recent: list[dict[str, object]] = []
    for r in obs_rows:
        if r.aircraft_id not in seen_ac:
            seen_ac.add(r.aircraft_id)
            recent.append(
                {
                    "icao24": r.icao24,
                    "callsign": r.callsign,
                    "aircraft_type": r.aircraft_type,
                    "baro_altitude_m": r.baro_altitude_m,
                    "velocity_ms": r.velocity_ms,
                    "observed_at": r.observed_at.isoformat(),
                    "distance_km": round(float(r.dist_m) / 1000.0, 1),
                }
            )
            if len(recent) >= 20:
                break

    return AirportTrafficOut(
        ident=ap.ident,
        name=ap.name,
        radius_km=radius_km,
        total_observations=total_obs,
        distinct_aircraft_count=len(distinct_aircraft),
        hourly_series=hourly_series,
        recent_aircraft=recent,
    )
