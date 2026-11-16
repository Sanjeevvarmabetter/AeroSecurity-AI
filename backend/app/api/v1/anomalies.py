from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Principal, Role, require_role
from app.schemas.anomaly import (
    AnomalyDetail,
    AnomalyOut,
    AnomalyStats,
    EmergencyOut,
    InvestigateRequest,
    InvestigationListItem,
    Me,
    NoteCreate,
    NoteOut,
    Severity,
    Status,
    StatusChange,
)
from app.schemas.common import Page
from app.schemas.investigation import (
    CaseCreate,
    CaseDetail,
    CaseListItem,
    CaseNoteCreate,
    CaseNoteOut,
    CaseStatusUpdate,
)
from app.services import anomalies as svc
from app.services import investigations as wf
from app.services.aviation import NotFoundError

viewer = Depends(require_role(Role.VIEWER))
analyst = require_role(Role.ANALYST)

router = APIRouter(prefix="/anomalies", tags=["anomalies"], dependencies=[viewer])
emergency_router = APIRouter(prefix="/emergencies", tags=["emergencies"], dependencies=[viewer])
investigation_router = APIRouter(prefix="/investigations", tags=["investigations"], dependencies=[viewer])
auth_router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[Session, Depends(get_session)]
AnomalyId = Annotated[str, Path(pattern=r"^ANM-\d{1,9}$", description="Public anomaly id, e.g. ANM-0042")]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def _tz(*values: datetime | None) -> None:
    for v in values:
        if v is not None and v.tzinfo is None:
            raise HTTPException(422, "timestamps must include a timezone, e.g. 2026-09-30T04:00:00Z")
    if len(values) == 2 and values[0] and values[1] and values[0] >= values[1]:
        raise HTTPException(422, "start must be earlier than end")


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except wf.WorkflowError as e:
        raise HTTPException(e.status_code, str(e)) from e


@router.get("", response_model=Page[AnomalyOut])
def list_anomalies(
    db: Db,
    severity: Annotated[list[Severity] | None, Query()] = None,
    status: Annotated[list[Status] | None, Query()] = None,
    detection_type: Annotated[str | None, Query(pattern=r"^[A-Z_]{1,32}$")] = None,
    rule_id: Annotated[str | None, Query(pattern=r"^DET-\d{3}$")] = None,
    icao24: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{1,6}$", description="ICAO24 prefix")] = None,
    airport: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9]{2,8}$")] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    sort: svc.SortField = "detected_at",
    order: Literal["asc", "desc"] = "desc",
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[AnomalyOut]:
    _tz(start, end)
    return svc.list_anomalies(
        db,
        severity=severity,
        status=status,
        detection_type=detection_type,
        rule_id=rule_id,
        icao24=icao24,
        airport=airport,
        min_confidence=min_confidence,
        start=start,
        end=end,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=AnomalyStats)
def stats(db: Db) -> AnomalyStats:
    return svc.anomaly_stats(db)


@router.get("/{anomaly_id}", response_model=AnomalyDetail)
def get_anomaly(db: Db, anomaly_id: AnomalyId) -> AnomalyDetail:
    return _run(lambda: svc.anomaly_detail(db, anomaly_id))


@router.post("/{anomaly_id}/investigate", response_model=AnomalyDetail, status_code=201)
def investigate(
    db: Db,
    anomaly_id: AnomalyId,
    who: Annotated[Principal, Depends(analyst)],
    body: InvestigateRequest | None = None,
) -> AnomalyDetail:
    body = body or InvestigateRequest()
    _run(
        lambda: wf.open_investigation(db, svc.parse_public_id(anomaly_id), body.note, who, body.claimed_name)
    )
    return _run(lambda: svc.anomaly_detail(db, anomaly_id))


@router.patch("/{anomaly_id}/status", response_model=AnomalyDetail)
def change_status(
    db: Db, anomaly_id: AnomalyId, body: StatusChange, who: Annotated[Principal, Depends(analyst)]
) -> AnomalyDetail:
    _run(
        lambda: wf.change_status(
            db, svc.parse_public_id(anomaly_id), body.status, body.reason, who, body.claimed_name
        )
    )
    return _run(lambda: svc.anomaly_detail(db, anomaly_id))


@router.post("/{anomaly_id}/notes", response_model=NoteOut, status_code=201)
def add_note(
    db: Db, anomaly_id: AnomalyId, body: NoteCreate, who: Annotated[Principal, Depends(analyst)]
) -> NoteOut:
    n = _run(lambda: wf.add_note(db, svc.parse_public_id(anomaly_id), body, who))
    return NoteOut(
        id=n.id, author=n.author, claimed_name=n.claimed_name, body=n.body, created_at=n.created_at
    )


@emergency_router.get("", response_model=Page[EmergencyOut])
def list_emergencies(
    db: Db,
    squawk: Annotated[Literal["7500", "7600", "7700"] | None, Query()] = None,
    status: Annotated[list[Status] | None, Query()] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[EmergencyOut]:
    _tz(start, end)
    return svc.list_emergencies(
        db, squawk=squawk, status=status, start=start, end=end, limit=limit, offset=offset
    )


@investigation_router.get("", response_model=Page[InvestigationListItem])
def list_investigations(
    db: Db, status: Annotated[list[Status] | None, Query()] = None, limit: Limit = 50, offset: Offset = 0
) -> Page[InvestigationListItem]:
    return svc.list_investigations(db, status=status, limit=limit, offset=offset)


@investigation_router.get("/cases", response_model=Page[CaseListItem])
def list_cases(
    db: Db,
    status: Annotated[list[str] | None, Query()] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    icao24: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{1,6}$")] = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[CaseListItem]:
    return wf.list_cases(db, status=status, severity=severity, icao24=icao24, limit=limit, offset=offset)


@investigation_router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    db: Db,
    body: CaseCreate,
    who: Annotated[Principal, Depends(analyst)],
) -> CaseDetail:
    inv = wf.create_case(db, body, who)
    return wf.get_case(db, inv.id)


@investigation_router.get("/{inv_id}", response_model=CaseDetail)
def get_case(db: Db, inv_id: int) -> CaseDetail:
    return _run(lambda: wf.get_case(db, inv_id))


@investigation_router.patch("/{inv_id}/status", response_model=CaseDetail)
def update_case_status(
    db: Db,
    inv_id: int,
    body: CaseStatusUpdate,
    who: Annotated[Principal, Depends(analyst)],
) -> CaseDetail:
    return _run(lambda: wf.update_case_status(db, inv_id, body, who))


@investigation_router.post("/{inv_id}/notes", response_model=CaseNoteOut, status_code=201)
def add_case_note(
    db: Db,
    inv_id: int,
    body: CaseNoteCreate,
    who: Annotated[Principal, Depends(analyst)],
) -> CaseNoteOut:
    return _run(lambda: wf.add_case_note(db, inv_id, body.body, who, body.claimed_name))


@auth_router.get("/me", response_model=Me)
def me(who: Annotated[Principal, Depends(require_role(Role.VIEWER))]) -> Me:
    return Me(role=who.role.name.lower(), key_id=who.key_id)
