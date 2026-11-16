from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Role, require_role
from app.schemas.aviation import (
    AircraftDetail,
    AircraftSummary,
    AirportOut,
    AirportTrafficOut,
    LiveResponse,
    ObservationOut,
    TrajectoryResponse,
)
from app.schemas.common import Page
from app.services import aviation as svc

_auth = [Depends(require_role(Role.VIEWER))]
router = APIRouter(prefix="/aviation", tags=["aviation"], dependencies=_auth)
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=_auth)

Db = Annotated[Session, Depends(get_session)]
IcaoPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{6}$", description="6-hex-digit ICAO 24-bit address")]
SearchTerm = Annotated[
    str | None,
    Query(pattern=r"^[A-Za-z0-9-]{1,16}$", description="Prefix of ICAO24, registration or callsign"),
]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def _check_range(start: datetime | None, end: datetime | None) -> None:
    for d in (start, end):
        if d is not None and d.tzinfo is None:
            raise HTTPException(422, "timestamps must include a timezone, e.g. 2026-09-30T04:00:00Z")
    if start and end and start >= end:
        raise HTTPException(422, "start must be earlier than end")


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except svc.NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except svc.TooLargeError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/aircraft", response_model=Page[AircraftSummary])
def list_aircraft(
    db: Db,
    q: SearchTerm = None,
    limit: Limit = 50,
    offset: Offset = 0,
    sort: Literal["last_seen", "icao24"] = "last_seen",
) -> Page[AircraftSummary]:
    return svc.search_aircraft(db, q, limit, offset, sort)


@router.get("/aircraft/live", response_model=LiveResponse)
def live_aircraft(
    db: Db,
    at: Annotated[
        datetime | None, Query(description="Snapshot time (default: now). Replays offline data.")
    ] = None,
    max_age_s: Annotated[int, Query(ge=1, le=86_400)] = 900,
    lamin: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lomin: Annotated[float | None, Query(ge=-180, le=180)] = None,
    lamax: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lomax: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=svc.LIVE_MAX_AIRCRAFT)] = 2000,
) -> LiveResponse:
    _check_range(at, None)
    bbox = None
    if any(v is not None for v in (lamin, lomin, lamax, lomax)):
        if lamin is None or lomin is None or lamax is None or lomax is None:
            raise HTTPException(422, "bbox requires lamin, lomin, lamax and lomax together")
        if lamin > lamax:
            raise HTTPException(422, "lamin must not exceed lamax")
        bbox = (lamin, lomin, lamax, lomax)
    return svc.live_aircraft(db, at, max_age_s, bbox, limit)


@router.get("/aircraft/{icao24}", response_model=AircraftDetail)
def aircraft_detail(db: Db, icao24: IcaoPath) -> AircraftDetail:
    return _run(lambda: svc.aircraft_detail(db, icao24))


@router.get("/aircraft/{icao24}/history", response_model=Page[ObservationOut])
def aircraft_history(
    db: Db,
    icao24: IcaoPath,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Offset = 0,
    order: Literal["asc", "desc"] = "desc",
) -> Page[ObservationOut]:
    _check_range(start, end)
    return _run(lambda: svc.aircraft_history(db, icao24, start, end, limit, offset, order))


@router.get("/airports", response_model=Page[AirportOut])
def list_airports(
    db: Db,
    q: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9 -]{1,40}$")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[AirportOut]:
    return svc.search_airports(db, q, limit, offset)


@router.get("/airports/{airport_code}", response_model=AirportOut)
def airport(db: Db, airport_code: Annotated[str, Path(pattern=r"^[A-Za-z0-9]{2,8}$")]) -> AirportOut:
    return _run(lambda: svc.get_airport(db, airport_code))


@router.get("/airports/{airport_code}/traffic", response_model=AirportTrafficOut)
def airport_traffic(
    db: Db,
    airport_code: Annotated[str, Path(pattern=r"^[A-Za-z0-9]{2,8}$")],
    radius_km: Annotated[float, Query(ge=1.0, le=100.0)] = 25.0,
) -> AirportTrafficOut:
    return _run(lambda: svc.get_airport_traffic(db, airport_code, radius_km))


@analytics_router.get("/trajectories", response_model=TrajectoryResponse)
def trajectories(
    db: Db,
    icao24: Annotated[str, Query(pattern=r"^[0-9a-fA-F]{6}$")],
    start: datetime | None = None,
    end: datetime | None = None,
    gap_s: Annotated[
        float, Query(gt=0, le=86_400, description="dt above which a segment is an observation gap")
    ] = 120.0,
) -> TrajectoryResponse:
    _check_range(start, end)
    return _run(lambda: svc.trajectory(db, icao24, start, end, gap_s))
