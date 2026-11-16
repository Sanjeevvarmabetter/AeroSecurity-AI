"""Enrich EXISTING aircraft with registration/type from the OpenSky aircraft database (crowdsourced).

Only aircraft we have already observed are updated; nothing is created. Blank or placeholder
fields stay NULL.
"""

import csv
import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Table, bindparam, select, update
from sqlalchemy.orm import Session

from app.ingestion.schema import ImportReport
from app.ingestion.service import SourceDisabledError
from app.models import Aircraft, AuditLog, DataSource

log = logging.getLogger(__name__)
SOURCE_NAME = "opensky-aircraft-db"
TERMS_URL = "https://opensky-network.org/data/aircraft"
REQUIRED = {"icao24", "registration", "typecode", "manufacturerName", "model", "operator"}
_PLACEHOLDERS = {"", "unknow", "unknown", "n/a", "none"}


def _clean(v: str | None, limit: int) -> str | None:
    s = (v or "").strip()
    return None if s.lower() in _PLACEHOLDERS else s[:limit]


def import_aircraft_metadata(
    session: Session, path: Path, *, max_bytes: int = 256 * 1024 * 1024, actor: str = "system"
) -> ImportReport:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError("aircraft database must be a regular file under the size limit")
    src = session.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if src is None:
        src = DataSource(name=SOURCE_NAME, kind="dataset", terms_url=TERMS_URL, enabled=True)
        session.add(src)
    session.commit()
    if not src.enabled:
        raise SourceDisabledError(f"data source '{SOURCE_NAME}' is disabled")

    known = set(session.scalars(select(Aircraft.icao24)))
    report = ImportReport(source=SOURCE_NAME)
    table = cast(Table, Aircraft.__table__)  # Core update: avoids ORM bulk-by-primary-key semantics
    stmt = (
        update(table)
        .where(table.c.icao24 == bindparam("b_icao24"))
        .values(
            registration=bindparam("registration"),
            aircraft_type=bindparam("aircraft_type"),
            manufacturer=bindparam("manufacturer"),
            model=bindparam("model"),
            operator=bindparam("operator"),
            metadata_source_id=src.id,
        )
    )
    batch: list[dict[str, Any]] = []
    with path.open("rb") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""), quotechar="'")
        if REQUIRED - set(reader.fieldnames or []):
            raise ValueError(f"missing columns: {sorted(REQUIRED - set(reader.fieldnames or []))}")
        for row in reader:
            report.read += 1
            icao = (row.get("icao24") or "").strip().lower()
            if icao not in known:
                continue  # not an aircraft we have observed
            if None in row:  # more fields than header: malformed line
                report.rejected["malformed_row"] += 1
                continue
            batch.append(
                {
                    "b_icao24": icao,
                    "registration": _clean(row["registration"], 16),
                    "aircraft_type": _clean(row["typecode"], 64),
                    "manufacturer": _clean(row["manufacturerName"], 128),
                    "model": _clean(row["model"], 128),
                    "operator": _clean(row["operator"], 128),
                }
            )
    if batch:
        session.execute(stmt, batch)
    report.inserted = len(batch)  # aircraft enriched
    src.last_success_at, src.last_error = datetime.now(UTC), None
    session.add(
        AuditLog(
            actor=actor,
            action="aircraft_metadata.imported",
            entity_type="data_source",
            entity_id=str(src.id),
            details=report.as_dict(),
        )
    )
    session.commit()
    log.info("aircraft metadata: %s", report.as_dict())
    return report
