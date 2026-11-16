"""Read side for anomalies, emergencies and investigations."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, case, func, select
from sqlalchemy.orm import Session

from app.models import (
    Aircraft,
    Anomaly,
    AuditLog,
    DetectionRule,
    Evidence,
    Investigation,
    InvestigationNote,
)
from app.schemas.anomaly import (
    AnomalyDetail,
    AnomalyOut,
    AnomalyStats,
    EmergencyOut,
    EvidenceOut,
    InvestigationListItem,
    InvestigationOut,
    NoteOut,
    RuleInfo,
    TimelineEntry,
)
from app.schemas.common import Page
from app.services.aviation import NotFoundError

TRANSITIONS: dict[str, list[str]] = {
    "OPEN": ["INVESTIGATING", "FALSE_POSITIVE"],
    "INVESTIGATING": ["OPEN", "FALSE_POSITIVE", "RESOLVED"],
    "FALSE_POSITIVE": ["OPEN"],
    "RESOLVED": ["OPEN"],
}
SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
SortField = Literal["detected_at", "event_start", "severity", "confidence"]


def public_id(pk: int) -> str:
    return f"ANM-{pk:04d}"


def parse_public_id(anomaly_id: str) -> int:
    if not anomaly_id.startswith("ANM-") or not anomaly_id[4:].isdigit():
        raise NotFoundError(f"anomaly {anomaly_id} not found")
    return int(anomaly_id[4:])


def _notes_count_subq() -> Any:
    return (
        select(
            Investigation.anomaly_id,
            func.count(InvestigationNote.id).label("n"),
            Investigation.id.label("inv"),
        )
        .outerjoin(InvestigationNote, InvestigationNote.investigation_id == Investigation.id)
        .group_by(Investigation.id)
        .subquery()
    )


def _base_query() -> tuple[Select[Any], Any]:
    nc = _notes_count_subq()
    q = (
        select(Anomaly, DetectionRule.name, Aircraft.icao24, Aircraft.registration, nc.c.inv, nc.c.n)
        .join(DetectionRule, DetectionRule.id == Anomaly.rule_id)
        .outerjoin(Aircraft, Aircraft.id == Anomaly.aircraft_id)
        .outerjoin(nc, nc.c.anomaly_id == Anomaly.id)
    )
    return q, nc


def _to_out(
    a: Anomaly, rule_name: str, icao24: str | None, reg: str | None, inv: int | None, n: int | None
) -> AnomalyOut:
    return AnomalyOut(
        anomaly_id=public_id(a.id),
        id=a.id,
        rule_id=a.rule_id,
        rule_name=rule_name,
        rule_version=a.rule_version,
        detection_type=a.detection_type,
        title=a.title,
        severity=a.severity,
        confidence=a.confidence,
        data_quality=a.data_quality,
        status=a.status,
        icao24=icao24,
        registration=reg,
        airport_ident=a.airport_ident,
        event_start=a.event_start,
        event_end=a.event_end,
        detected_at=a.detected_at,
        source_refs=list(a.source_refs or []),
        has_investigation=inv is not None,
        notes_count=n or 0,
    )


def list_anomalies(
    session: Session,
    *,
    severity: Sequence[str] | None,
    status: Sequence[str] | None,
    detection_type: str | None,
    rule_id: str | None,
    icao24: str | None,
    airport: str | None,
    min_confidence: float | None,
    start: datetime | None,
    end: datetime | None,
    sort: SortField,
    order: Literal["asc", "desc"],
    limit: int,
    offset: int,
) -> Page[AnomalyOut]:
    q, _ = _base_query()
    cond: list[ColumnElement[bool]] = []
    if severity:
        cond.append(Anomaly.severity.in_(severity))
    if status:
        cond.append(Anomaly.status.in_(status))
    if detection_type:
        cond.append(Anomaly.detection_type == detection_type)
    if rule_id:
        cond.append(Anomaly.rule_id == rule_id)
    if icao24:
        cond.append(Aircraft.icao24.like(f"{icao24.lower()}%"))  # pattern-validated: hex only
    if airport:
        cond.append(Anomaly.airport_ident == airport.upper())
    if min_confidence is not None:
        cond.append(Anomaly.confidence >= min_confidence)
    if start:
        cond.append(Anomaly.event_end >= start)  # overlaps the requested window
    if end:
        cond.append(Anomaly.event_start <= end)
    total = (
        session.scalar(
            select(func.count())
            .select_from(Anomaly)
            .outerjoin(Aircraft, Aircraft.id == Anomaly.aircraft_id)
            .where(*cond)
        )
        or 0
    )
    sev_rank = case(*[(Anomaly.severity == k, v) for k, v in SEVERITY_RANK.items()], else_=0)
    col = {
        "detected_at": Anomaly.detected_at,
        "event_start": Anomaly.event_start,
        "severity": sev_rank,
        "confidence": Anomaly.confidence,
    }[sort]
    ordering = col.asc() if order == "asc" else col.desc()
    rows = session.execute(
        q.where(*cond).order_by(ordering, Anomaly.id.desc()).limit(limit).offset(offset)
    ).all()
    return Page(items=[_to_out(*r) for r in rows], total=total, limit=limit, offset=offset)


def anomaly_stats(session: Session) -> AnomalyStats:
    def count(col: Any) -> dict[str, int]:
        return {k: n for k, n in session.execute(select(col, func.count()).group_by(col))}

    by_sev = count(Anomaly.severity)
    return AnomalyStats(
        total=sum(by_sev.values()),
        by_severity=by_sev,
        by_status=count(Anomaly.status),
        by_type=count(Anomaly.detection_type),
        by_rule=count(Anomaly.rule_id),
    )


def get_anomaly_row(session: Session, pk: int, *, lock: bool = False) -> Anomaly:
    q = select(Anomaly).where(Anomaly.id == pk)
    if lock:
        q = q.with_for_update()
    a = session.scalar(q)
    if a is None:
        raise NotFoundError(f"anomaly {public_id(pk)} not found")
    return a


def anomaly_detail(session: Session, anomaly_id: str) -> AnomalyDetail:
    pk = parse_public_id(anomaly_id)
    q, _ = _base_query()
    row = session.execute(q.where(Anomaly.id == pk)).first()
    if row is None:
        raise NotFoundError(f"anomaly {public_id(pk)} not found")
    a, rule_name, icao, reg, inv_id, n = row
    out = _to_out(a, rule_name, icao, reg, inv_id, n)
    rule = session.get(DetectionRule, a.rule_id)
    if rule is None:  # the FK makes this impossible; fail loudly rather than serve a partial record
        raise RuntimeError(f"anomaly {a.id} references missing rule {a.rule_id}")
    evidence = [
        EvidenceOut(ordinal=e.ordinal, kind=e.kind, observation_id=e.observation_id, payload=e.payload)
        for e in session.scalars(select(Evidence).where(Evidence.anomaly_id == pk).order_by(Evidence.ordinal))
    ]
    inv = session.scalar(select(Investigation).where(Investigation.anomaly_id == pk))
    notes = (
        [
            NoteOut(
                id=x.id, author=x.author, claimed_name=x.claimed_name, body=x.body, created_at=x.created_at
            )
            for x in session.scalars(
                select(InvestigationNote)
                .where(InvestigationNote.investigation_id == inv.id)
                .order_by(InvestigationNote.created_at, InvestigationNote.id)
            )
        ]
        if inv
        else []
    )
    summary = dict(a.summary or {})
    alternatives = list(summary.pop("alternative_explanations", []))
    return AnomalyDetail(
        **out.model_dump(),
        description=a.description,
        summary=summary,
        alternatives=alternatives,
        rule=RuleInfo(id=rule.id, name=rule.name, description=rule.description, version=rule.version),
        evidence=evidence,
        investigation=InvestigationOut(
            id=inv.id, opened_by=inv.opened_by, opened_at=inv.opened_at, closed_at=inv.closed_at
        )
        if inv
        else None,
        notes=notes,
        timeline=_timeline(session, a, inv, notes),
        allowed_transitions=TRANSITIONS[a.status],
    )


def _timeline(
    session: Session, a: Anomaly, inv: Investigation | None, notes: list[NoteOut]
) -> list[TimelineEntry]:
    t = [
        TimelineEntry(
            at=a.detected_at,
            kind="detected",
            actor="engine",
            text=f"Detected by {a.rule_id} v{a.rule_version}",
            data={"severity": a.severity},
        )
    ]
    if inv:
        t.append(
            TimelineEntry(
                at=inv.opened_at,
                kind="investigation_opened",
                actor=inv.opened_by,
                text="Investigation opened",
            )
        )
    for log in session.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "anomaly",
            AuditLog.entity_id == str(a.id),
            AuditLog.action == "anomaly.status_changed",
        )
        .order_by(AuditLog.occurred_at, AuditLog.id)
    ):
        d = log.details or {}
        t.append(
            TimelineEntry(
                at=log.occurred_at,
                kind="status_changed",
                actor=log.actor,
                text=f"Status {d.get('from')} -> {d.get('to')}"
                + (f": {d['reason']}" if d.get("reason") else ""),
                data={"from": d.get("from"), "to": d.get("to")},
            )
        )
    t += [
        TimelineEntry(at=n.created_at, kind="note", actor=n.author, text=n.body, data={"note_id": n.id})
        for n in notes
    ]
    return sorted(t, key=lambda e: e.at)


# -- emergencies ------------------------------------------------------------------------------------
def list_emergencies(
    session: Session,
    *,
    squawk: str | None,
    status: Sequence[str] | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    offset: int,
) -> Page[EmergencyOut]:
    cond = [Anomaly.rule_id == "DET-005"]
    if squawk:
        cond.append(Anomaly.summary["squawk"].astext == squawk)
    if status:
        cond.append(Anomaly.status.in_(status))
    if start:
        cond.append(Anomaly.event_end >= start)
    if end:
        cond.append(Anomaly.event_start <= end)
    total = session.scalar(select(func.count()).select_from(Anomaly).where(*cond)) or 0
    rows = session.execute(
        select(Anomaly, Aircraft.icao24, Aircraft.registration)
        .join(Aircraft, Aircraft.id == Anomaly.aircraft_id)
        .where(*cond)
        .order_by(Anomaly.event_start.desc(), Anomaly.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    ids = [a.id for a, _, _ in rows]
    callsigns: dict[int, str | None] = {}
    if ids:
        for aid, payload in session.execute(
            select(Evidence.anomaly_id, Evidence.payload).where(
                Evidence.anomaly_id.in_(ids), Evidence.kind == "context"
            )
        ):
            callsigns[aid] = payload.get("callsign")
    items = []
    for a, icao, reg in rows:
        s = a.summary or {}
        items.append(
            EmergencyOut(
                anomaly_id=public_id(a.id),
                icao24=icao,
                registration=reg,
                callsign=callsigns.get(a.id),
                squawk=s.get("squawk", ""),
                meaning=s.get("meaning", ""),
                severity=a.severity,
                status=a.status,
                confidence=a.confidence,
                transient=bool(s.get("transient")),
                first_seen=a.event_start,
                last_seen=a.event_end,
                duration_s=float(s.get("duration_s", 0.0)),
                observations=int(s.get("observations", 0)),
                last_known_position=s.get("last_known_position"),
                sources=list(a.source_refs or []),
            )
        )
    return Page(items=items, total=total, limit=limit, offset=offset)


# -- investigations ----------------------------------------------------------------------------------
def list_investigations(
    session: Session, *, status: Sequence[str] | None, limit: int, offset: int
) -> Page[InvestigationListItem]:
    nc = (
        select(
            InvestigationNote.investigation_id.label("iid"),
            func.count().label("n"),
            func.max(InvestigationNote.created_at).label("last_note"),
        )
        .group_by(InvestigationNote.investigation_id)
        .subquery()
    )
    cond: list[ColumnElement[bool]] = [Anomaly.status.in_(status)] if status else []
    total = (
        session.scalar(
            select(func.count())
            .select_from(Investigation)
            .join(Anomaly, Anomaly.id == Investigation.anomaly_id)
            .where(*cond)
        )
        or 0
    )
    rows = session.execute(
        select(Investigation, Anomaly, Aircraft.icao24, nc.c.n, nc.c.last_note)
        .join(Anomaly, Anomaly.id == Investigation.anomaly_id)
        .outerjoin(Aircraft, Aircraft.id == Anomaly.aircraft_id)
        .outerjoin(nc, nc.c.iid == Investigation.id)
        .where(*cond)
        .order_by(
            func.greatest(
                Investigation.opened_at, func.coalesce(nc.c.last_note, Investigation.opened_at)
            ).desc()
        )
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        InvestigationListItem(
            id=i.id,
            anomaly_id=public_id(a.id),
            anomaly_title=a.title,
            severity=a.severity,
            status=a.status,
            icao24=icao,
            opened_by=i.opened_by,
            opened_at=i.opened_at,
            closed_at=i.closed_at,
            notes_count=n or 0,
            last_activity=max(i.opened_at, last or i.opened_at),
        )
        for i, a, icao, n, last in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
