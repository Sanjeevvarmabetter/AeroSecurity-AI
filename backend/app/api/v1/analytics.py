from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Role, require_role
from app.schemas.aviation import TrajectoryResponse
from app.services import analytics as stats_svc
from app.services import aviation as svc

_auth = [Depends(require_role(Role.VIEWER))]
router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=_auth)
Db = Annotated[Session, Depends(get_session)]


def _check_range(start: datetime | None, end: datetime | None) -> None:
    for d in (start, end):
        if d is not None and d.tzinfo is None:
            raise HTTPException(422, "timestamps must include a timezone, e.g. 2026-09-30T04:00:00Z")
    if start and end and start >= end:
        raise HTTPException(422, "start must be earlier than end")


@router.get("/overview")
def overview_stats(db: Db) -> dict[str, object]:
    """Returns platform operations dashboard metrics aggregated from backend data."""
    return stats_svc.get_overview_analytics(db)


@router.get("/fleet")
def fleet_analytics(db: Db) -> dict[str, object]:
    """Returns altitude distributions, speed histograms, and aircraft categories."""
    return stats_svc.get_fleet_analytics(db)


@router.get("/trajectories", response_model=TrajectoryResponse)
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
    try:
        return svc.trajectory(db, icao24, start, end, gap_s)
    except svc.NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except svc.TooLargeError as e:
        raise HTTPException(422, str(e)) from e
