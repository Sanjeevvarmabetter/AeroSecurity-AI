"""OurAirports CSV importer (https://ourairports.com/data/, public domain)."""

import csv
import io
import logging
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ingestion.schema import ImportReport
from app.ingestion.service import SourceDisabledError
from app.models import Airport, AuditLog, DataSource

log = logging.getLogger(__name__)
SOURCE_NAME = "ourairports"
TERMS_URL = "https://ourairports.com/data/"
REQUIRED = {"ident", "name", "latitude_deg", "longitude_deg"}


def _parse(row: dict[str, str], source_id: int) -> dict[str, Any] | str:
    ident = (row.get("ident") or "").strip()
    if not ident or len(ident) > 16:
        return "invalid_ident"
    try:
        lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
    except (ValueError, KeyError):
        return "invalid_coordinates"
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return "invalid_coordinates"
    elev = row.get("elevation_ft", "").strip()
    iata = (row.get("iata_code") or "").strip().upper()
    return {
        "ident": ident,
        "iata_code": iata if len(iata) == 3 else None,
        "name": (row.get("name") or "").strip()[:256],
        "airport_type": (row.get("type") or "").strip()[:32] or None,
        "iso_country": (row.get("iso_country") or "").strip()[:2] or None,
        "elevation_ft": int(float(elev)) if elev.replace("-", "", 1).replace(".", "", 1).isdigit() else None,
        "position": f"SRID=4326;POINT({lon} {lat})",
        "data_source_id": source_id,
    }


def import_airports(
    session: Session, path: Path, *, max_bytes: int = 64 * 1024 * 1024, actor: str = "system"
) -> ImportReport:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError("airports file must be a regular file under the size limit")
    src = session.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if src is None:
        src = DataSource(name=SOURCE_NAME, kind="dataset", terms_url=TERMS_URL, enabled=True)
        session.add(src)
        session.flush()
    if not src.enabled:
        raise SourceDisabledError(f"data source '{SOURCE_NAME}' is disabled")

    report = ImportReport(source=SOURCE_NAME)
    rejected: Counter[str] = report.rejected
    with path.open("rb") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))
        if REQUIRED - set(reader.fieldnames or []):
            raise ValueError(f"missing columns: {sorted(REQUIRED - set(reader.fieldnames or []))}")
        batch: list[dict[str, Any]] = []

        def flush() -> None:
            if not batch:
                return
            stmt = pg_insert(Airport).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Airport.ident],
                set_={
                    c: stmt.excluded[c]
                    for c in (
                        "iata_code",
                        "name",
                        "airport_type",
                        "iso_country",
                        "elevation_ft",
                        "position",
                        "data_source_id",
                    )
                },
            )
            session.execute(stmt)
            report.inserted += len(batch)
            batch.clear()

        for row in reader:
            report.read += 1
            parsed = _parse(row, src.id)
            if isinstance(parsed, str):
                rejected[parsed] += 1
                continue
            batch.append(parsed)
            if len(batch) >= 2000:
                flush()
        flush()
    src.last_success_at, src.last_error = datetime.now(UTC), None
    session.add(
        AuditLog(
            actor=actor,
            action="airports.imported",
            entity_type="data_source",
            entity_id=str(src.id),
            details=report.as_dict(),
        )
    )
    session.commit()
    return report
