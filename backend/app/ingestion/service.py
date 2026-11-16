"""Ingestion orchestration: provider -> validated batches -> PostgreSQL, with provenance and audit."""

import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from itertools import islice
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.ingestion.base import ObservationProvider
from app.ingestion.schema import ImportReport, NormalizedObservation, Rejection
from app.models import Aircraft, AircraftObservation, AuditLog, DataSource

log = logging.getLogger(__name__)


class SourceDisabledError(Exception):
    """The data source is registered but not enabled by an operator."""


def get_or_register_source(session: Session, provider: ObservationProvider) -> DataSource:
    src = session.scalar(select(DataSource).where(DataSource.name == provider.name))
    if src is None:
        src = DataSource(
            name=provider.name,
            kind=provider.kind,
            terms_url=provider.terms_url,
            enabled=provider.default_enabled,
        )
        session.add(src)
        session.flush()
    return src


def _batches(it: Iterable[Any], size: int) -> Iterator[list[Any]]:
    iterator = iter(it)
    while batch := list(islice(iterator, size)):
        yield batch


def _upsert_aircraft(session: Session, obs: list[NormalizedObservation]) -> dict[str, int]:
    seen: dict[str, dict[str, Any]] = {}
    for o in obs:
        a = seen.setdefault(
            o.icao24,
            {
                "icao24": o.icao24,
                "first_seen": o.observed_at,
                "last_seen": o.observed_at,
                "origin_country": o.origin_country,
            },
        )
        a["first_seen"] = min(a["first_seen"], o.observed_at)
        a["last_seen"] = max(a["last_seen"], o.observed_at)
        a["origin_country"] = a["origin_country"] or o.origin_country
    stmt = pg_insert(Aircraft).values(list(seen.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=[Aircraft.icao24],
        set_={
            "first_seen": func.least(Aircraft.first_seen, stmt.excluded.first_seen),
            "last_seen": func.greatest(Aircraft.last_seen, stmt.excluded.last_seen),
            "origin_country": func.coalesce(Aircraft.origin_country, stmt.excluded.origin_country),
        },
    )
    return {icao: aid for icao, aid in session.execute(stmt.returning(Aircraft.icao24, Aircraft.id))}


def _insert_observations(
    session: Session, obs: list[NormalizedObservation], aircraft_ids: dict[str, int], source_id: int
) -> int:
    rows = [
        {
            "aircraft_id": aircraft_ids[o.icao24],
            "data_source_id": source_id,
            "observed_at": o.observed_at,
            "last_contact_at": o.last_contact_at,
            "callsign": o.callsign,
            "position": f"SRID=4326;POINT({o.lon} {o.lat})"
            if o.lat is not None and o.lon is not None
            else None,
            "baro_altitude_m": o.baro_altitude_m,
            "geo_altitude_m": o.geo_altitude_m,
            "on_ground": o.on_ground,
            "velocity_ms": o.velocity_ms,
            "heading_deg": o.heading_deg,
            "vertical_rate_ms": o.vertical_rate_ms,
            "squawk": o.squawk,
            "position_source": o.position_source,
            "raw": o.raw or None,
        }
        for o in obs
    ]
    stmt = pg_insert(AircraftObservation).on_conflict_do_nothing(constraint="uq_observation_identity")
    result = session.execute(stmt.returning(AircraftObservation.id), rows)
    return len(result.all())


def ingest(
    session: Session, provider: ObservationProvider, *, batch_size: int = 5000, actor: str = "system"
) -> ImportReport:
    """Run one provider to completion. Idempotent: re-running inserts nothing new."""
    source = get_or_register_source(session, provider)
    session.commit()  # persist the registration first so failures can always be recorded against it
    if not source.enabled:
        raise SourceDisabledError(f"data source '{source.name}' is disabled")

    report = ImportReport(source=source.name)
    touched: set[str] = set()
    try:
        for batch in _batches(provider.fetch(), batch_size):
            good: list[NormalizedObservation] = []
            for item in batch:
                report.read += 1
                if isinstance(item, Rejection):
                    report.rejected[item.reason] += 1
                else:
                    good.append(item)
                    for issue in item.raw.get("issues", ()):
                        report.field_issues[issue] += 1
            if good:
                ids = _upsert_aircraft(session, good)
                inserted = _insert_observations(session, good, ids, source.id)
                report.inserted += inserted
                report.duplicates += len(good) - inserted
                touched.update(ids)
            session.commit()
    except Exception as exc:
        session.rollback()
        _record_failure(session, source.id, actor, exc, report)
        raise
    report.aircraft_touched = len(touched)
    source.last_success_at, source.last_error = datetime.now(UTC), None
    session.add(
        AuditLog(
            actor=actor,
            action="ingest.completed",
            entity_type="data_source",
            entity_id=str(source.id),
            details=report.as_dict(),
        )
    )
    session.commit()
    log.info("ingest %s: %s", source.name, report.as_dict())
    return report


def _record_failure(
    session: Session, source_id: int, actor: str, exc: Exception, report: ImportReport
) -> None:
    msg = redact(f"{type(exc).__name__}: {exc}")[:500]
    src = session.get(DataSource, source_id)
    if src is not None:
        src.last_error_at, src.last_error = datetime.now(UTC), msg
    session.add(
        AuditLog(
            actor=actor,
            action="ingest.failed",
            entity_type="data_source",
            entity_id=str(source_id),
            details={"error": msg, "partial": report.as_dict()},
        )
    )
    session.commit()
    log.error("ingest failed for source %s: %s", source_id, msg)
