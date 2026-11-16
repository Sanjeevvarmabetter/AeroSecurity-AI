"""Investigation workflow and full case management lifecycle."""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models import Aircraft, Anomaly, AuditLog, Investigation, InvestigationNote
from app.schemas.anomaly import NoteCreate
from app.schemas.common import Page
from app.schemas.investigation import (
    CaseCreate,
    CaseDetail,
    CaseListItem,
    CaseNoteOut,
    CaseStatusUpdate,
    TimelineEvent,
)
from app.services.anomalies import TRANSITIONS, get_anomaly_row, parse_public_id, public_id
from app.services.aviation import NotFoundError


class WorkflowError(Exception):
    """A request that is valid in shape but not allowed in the current state (HTTP 409/422)."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _audit(
    session: Session,
    who: Principal,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, object],
) -> None:
    session.add(
        AuditLog(
            actor=who.actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )


def _get_investigation_by_anomaly(session: Session, pk: int) -> Investigation | None:
    return session.scalar(select(Investigation).where(Investigation.anomaly_id == pk))


# -- Anomaly-tied legacy workflow support --------------------------------------------------------
def change_status(
    session: Session, pk: int, new: str, reason: str, who: Principal, claimed_name: str | None = None
) -> None:
    a = get_anomaly_row(session, pk, lock=True)
    old = a.status
    inv = _get_investigation_by_anomaly(session, pk)
    if new == old:
        raise WorkflowError(f"{public_id(pk)} is already {old}")
    if new not in TRANSITIONS[old]:
        raise WorkflowError(f"cannot move {old} -> {new}; allowed: {', '.join(TRANSITIONS[old])}")
    if new in ("FALSE_POSITIVE", "RESOLVED") and not reason:
        raise WorkflowError("a reason is required when closing a finding", 422)
    if new == "INVESTIGATING" and inv is None:
        raise WorkflowError("start the investigation first (POST /investigate)")
    a.status = new
    if inv is not None:
        inv.closed_at = datetime.now(UTC) if new in ("FALSE_POSITIVE", "RESOLVED") else None
        inv.status = new
        inv.updated_at = datetime.now(UTC)
    _audit(
        session,
        who,
        "anomaly.status_changed",
        "anomaly",
        str(pk),
        {"from": old, "to": new, "reason": reason, "claimed_name": claimed_name},
    )
    session.commit()


def open_investigation(
    session: Session, pk: int, note: str, who: Principal, claimed_name: str | None
) -> Investigation:
    a = get_anomaly_row(session, pk, lock=True)
    existing = _get_investigation_by_anomaly(session, pk)
    if existing is not None:
        raise WorkflowError(f"{public_id(pk)} already has an investigation")
    if a.status not in ("OPEN",):
        raise WorkflowError(f"only OPEN findings can be investigated (currently {a.status}); reopen it first")
    inv = Investigation(
        anomaly_id=pk,
        aircraft_id=a.aircraft_id,
        title=f"Investigation: {a.title}",
        description=a.description,
        status="IN_PROGRESS",
        severity=a.severity,
        opened_by=who.actor,
        lead_analyst=claimed_name or who.actor,
    )
    session.add(inv)
    session.flush()
    old = a.status
    a.status = "INVESTIGATING"
    _audit(
        session,
        who,
        "investigation.opened",
        "anomaly",
        str(pk),
        {"investigation_id": inv.id, "claimed_name": claimed_name},
    )
    _audit(
        session,
        who,
        "anomaly.status_changed",
        "anomaly",
        str(pk),
        {"from": old, "to": "INVESTIGATING", "reason": "investigation opened", "claimed_name": claimed_name},
    )
    if note.strip():
        session.add(
            InvestigationNote(
                investigation_id=inv.id, author=who.actor, claimed_name=claimed_name, body=note.strip()
            )
        )
    session.commit()
    return inv


def add_note(session: Session, pk: int, payload: NoteCreate, who: Principal) -> InvestigationNote:
    get_anomaly_row(session, pk)
    inv = _get_investigation_by_anomaly(session, pk)
    if inv is None:
        raise WorkflowError("start the investigation before adding notes")
    note = InvestigationNote(
        investigation_id=inv.id, author=who.actor, claimed_name=payload.claimed_name, body=payload.body
    )
    session.add(note)
    inv.updated_at = datetime.now(UTC)
    session.flush()
    _audit(
        session,
        who,
        "anomaly.note_added",
        "anomaly",
        str(pk),
        {"note_id": note.id, "length": len(payload.body), "claimed_name": payload.claimed_name},
    )
    session.commit()
    return note


# -- Standalone Case Management ------------------------------------------------------------------
def create_case(session: Session, body: CaseCreate, who: Principal) -> Investigation:
    ac_id = None
    if body.icao24:
        ac = session.scalar(select(Aircraft).where(Aircraft.icao24 == body.icao24.lower()))
        if ac:
            ac_id = ac.id

    anom_id = None
    if body.anomaly_id:
        anom_pk = parse_public_id(body.anomaly_id)
        a = session.get(Anomaly, anom_pk)
        if a:
            anom_id = a.id
            if ac_id is None:
                ac_id = a.aircraft_id

    inv = Investigation(
        title=body.title.strip(),
        description=body.description.strip() if body.description else None,
        aircraft_id=ac_id,
        anomaly_id=anom_id,
        status="NEW",
        severity=body.severity,
        opened_by=who.actor,
        lead_analyst=body.claimed_name or who.actor,
    )
    session.add(inv)
    session.flush()

    if body.initial_note and body.initial_note.strip():
        session.add(
            InvestigationNote(
                investigation_id=inv.id,
                author=who.actor,
                claimed_name=body.claimed_name,
                body=body.initial_note.strip(),
            )
        )

    _audit(
        session,
        who,
        "investigation.case_created",
        "investigation",
        str(inv.id),
        {"title": inv.title, "aircraft_id": ac_id, "anomaly_id": body.anomaly_id},
    )
    session.commit()
    return inv


def get_case(session: Session, inv_id: int) -> CaseDetail:
    inv = session.get(Investigation, inv_id)
    if inv is None:
        raise NotFoundError(f"investigation {inv_id} not found")

    notes_rows = session.scalars(
        select(InvestigationNote)
        .where(InvestigationNote.investigation_id == inv.id)
        .order_by(InvestigationNote.created_at.asc())
    ).all()
    notes = [
        CaseNoteOut(
            id=n.id,
            author=n.author,
            claimed_name=n.claimed_name,
            body=n.body,
            created_at=n.created_at,
        )
        for n in notes_rows
    ]

    # Timeline from audit logs
    audit_events = session.scalars(
        select(AuditLog)
        .where(
            or_(
                (AuditLog.entity_type == "investigation") & (AuditLog.entity_id == str(inv.id)),
                (AuditLog.entity_type == "anomaly") & (AuditLog.entity_id == str(inv.anomaly_id or -1)),
            )
        )
        .order_by(AuditLog.occurred_at.asc())
    ).all()
    timeline = [
        TimelineEvent(
            timestamp=ev.occurred_at,
            actor=ev.actor,
            action=ev.action,
            details=ev.details or {},
        )
        for ev in audit_events
    ]

    # Aircraft summary if linked
    ac_sum = None
    icao24 = None
    if inv.aircraft_id:
        ac = session.get(Aircraft, inv.aircraft_id)
        if ac:
            icao24 = ac.icao24
            ac_sum = {
                "icao24": ac.icao24,
                "registration": ac.registration,
                "aircraft_type": ac.aircraft_type,
                "manufacturer": ac.manufacturer,
                "model": ac.model,
                "origin_country": ac.origin_country,
            }

    # Anomaly summary if linked
    anom_sum = None
    anom_title = None
    anom_pub_id = None
    if inv.anomaly_id:
        anom = session.get(Anomaly, inv.anomaly_id)
        if anom:
            anom_pub_id = public_id(anom.id)
            anom_title = anom.title
            anom_sum = {
                "anomaly_id": anom_pub_id,
                "rule_id": anom.rule_id,
                "title": anom.title,
                "detection_type": anom.detection_type,
                "severity": anom.severity,
                "confidence": anom.confidence,
                "event_start": anom.event_start.isoformat() if anom.event_start else None,
            }

    return CaseDetail(
        id=inv.id,
        title=inv.title,
        description=inv.description,
        status=inv.status,
        severity=inv.severity,
        opened_by=inv.opened_by,
        lead_analyst=inv.lead_analyst,
        opened_at=inv.opened_at,
        updated_at=inv.updated_at,
        closed_at=inv.closed_at,
        aircraft_id=inv.aircraft_id,
        icao24=icao24,
        anomaly_id=anom_pub_id,
        anomaly_title=anom_title,
        notes_count=len(notes),
        notes=notes,
        timeline=timeline,
        aircraft_summary=ac_sum,
        anomaly_summary=anom_sum,
    )


def update_case_status(session: Session, inv_id: int, body: CaseStatusUpdate, who: Principal) -> CaseDetail:
    inv = session.get(Investigation, inv_id)
    if inv is None:
        raise NotFoundError(f"investigation {inv_id} not found")

    old_status = inv.status
    inv.status = body.status
    inv.updated_at = datetime.now(UTC)
    if body.status in ("CLOSED", "FALSE_POSITIVE"):
        inv.closed_at = datetime.now(UTC)
    else:
        inv.closed_at = None

    if body.reason and body.reason.strip():
        session.add(
            InvestigationNote(
                investigation_id=inv.id,
                author=who.actor,
                claimed_name=body.claimed_name,
                body=f"Status changed to {body.status}: {body.reason.strip()}",
            )
        )

    _audit(
        session,
        who,
        "investigation.status_changed",
        "investigation",
        str(inv.id),
        {"from": old_status, "to": body.status, "reason": body.reason, "claimed_name": body.claimed_name},
    )
    session.commit()
    return get_case(session, inv.id)


def add_case_note(
    session: Session, inv_id: int, body: str, who: Principal, claimed_name: str | None
) -> CaseNoteOut:
    inv = session.get(Investigation, inv_id)
    if inv is None:
        raise NotFoundError(f"investigation {inv_id} not found")

    note = InvestigationNote(
        investigation_id=inv.id,
        author=who.actor,
        claimed_name=claimed_name,
        body=body.strip(),
    )
    session.add(note)
    inv.updated_at = datetime.now(UTC)
    session.flush()

    _audit(
        session,
        who,
        "investigation.note_added",
        "investigation",
        str(inv.id),
        {"note_id": note.id, "length": len(body), "claimed_name": claimed_name},
    )
    session.commit()
    return CaseNoteOut(
        id=note.id,
        author=note.author,
        claimed_name=note.claimed_name,
        body=note.body,
        created_at=note.created_at,
    )


def list_cases(
    session: Session,
    status: list[str] | None = None,
    severity: list[str] | None = None,
    icao24: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[CaseListItem]:
    cond: list[ColumnElement[bool]] = []
    if status:
        cond.append(Investigation.status.in_(status))
    if severity:
        cond.append(Investigation.severity.in_(severity))
    if icao24:
        ac_ids = select(Aircraft.id).where(Aircraft.icao24 == icao24.lower())
        cond.append(Investigation.aircraft_id.in_(ac_ids))

    total = session.scalar(select(func.count(Investigation.id)).where(*cond)) or 0

    nc = (
        select(
            InvestigationNote.investigation_id.label("iid"),
            func.count(InvestigationNote.id).label("n"),
        )
        .group_by(InvestigationNote.investigation_id)
        .subquery()
    )

    rows = session.execute(
        select(Investigation, Aircraft.icao24, Anomaly.id, Anomaly.title, nc.c.n)
        .outerjoin(Aircraft, Aircraft.id == Investigation.aircraft_id)
        .outerjoin(Anomaly, Anomaly.id == Investigation.anomaly_id)
        .outerjoin(nc, nc.c.iid == Investigation.id)
        .where(*cond)
        .order_by(Investigation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        CaseListItem(
            id=i.id,
            title=i.title,
            description=i.description,
            status=i.status,
            severity=i.severity,
            opened_by=i.opened_by,
            lead_analyst=i.lead_analyst,
            opened_at=i.opened_at,
            updated_at=i.updated_at,
            closed_at=i.closed_at,
            aircraft_id=i.aircraft_id,
            icao24=icao,
            anomaly_id=public_id(anom_id) if anom_id else None,
            anomaly_title=anom_title,
            notes_count=n or 0,
        )
        for i, icao, anom_id, anom_title, n in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


__all__ = [
    "NotFoundError",
    "WorkflowError",
    "add_case_note",
    "add_note",
    "change_status",
    "create_case",
    "get_case",
    "list_cases",
    "open_investigation",
    "update_case_status",
]
