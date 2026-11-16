"""Importer for OpenSky `state_vectors_data4` CSV extracts (plain .csv, or a member of a .tar.gz).

Archives are streamed, never extracted to disk, so member names cannot cause path traversal. Only a member
whose basename ends with `state_vectors_data4.csv` is read; size is capped.
"""

import csv
import io
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

from app.core.config import get_settings
from app.ingestion.base import ObservationProvider
from app.ingestion.schema import NormalizedObservation, Rejection
from app.ingestion.validation import normalize

MEMBER_SUFFIX = "state_vectors_data4.csv"
REQUIRED_COLUMNS = {"time", "icao24", "lat", "lon", "lastcontact"}


class DatasetError(Exception):
    """The dataset file is unsafe or not in the expected format."""


class OpenSkyCsvProvider(ObservationProvider):
    name = "opensky-dataset"
    kind = "dataset"
    terms_url = "https://opensky-network.org/data/scientific"
    default_enabled = True  # offline research data; licence (CC BY 4.0) is recorded with the dataset

    def __init__(self, path: Path, *, max_bytes: int | None = None, max_rows: int | None = None) -> None:
        s = get_settings()
        self.path = path
        self.max_bytes = max_bytes or s.ingest_max_file_bytes
        self.max_rows = max_rows or s.ingest_max_rows

    def _open(self) -> Iterator[IO[bytes]]:
        if not self.path.is_file() or self.path.is_symlink():
            raise DatasetError(f"not a regular file: {self.path.name}")
        if self.path.stat().st_size > self.max_bytes:
            raise DatasetError("file exceeds configured size limit")
        if tarfile.is_tarfile(self.path):
            with tarfile.open(self.path, "r:*") as tar:
                members = [m for m in tar if m.isfile() and Path(m.name).name.endswith(MEMBER_SUFFIX)]
                if len(members) != 1:
                    raise DatasetError(f"expected exactly one *{MEMBER_SUFFIX} member, found {len(members)}")
                if members[0].size > self.max_bytes:
                    raise DatasetError("archive member exceeds configured size limit")
                f = tar.extractfile(members[0])
                if f is None:
                    raise DatasetError("cannot read archive member")
                yield f
        else:
            with self.path.open("rb") as f:
                yield f

    def fetch(self) -> Iterator[NormalizedObservation | Rejection]:
        for binary in self._open():
            reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise DatasetError(f"missing required columns: {sorted(missing)}")
            for n, row in enumerate(reader, start=2):  # header is line 1
                if n - 1 > self.max_rows:
                    raise DatasetError("row limit exceeded")
                yield normalize(self._canonical(row), n)

    @staticmethod
    def _canonical(row: dict[str, str]) -> dict[str, Any]:
        lastpos = row.get("lastposupdate")
        return {
            "icao24": row.get("icao24"),
            # Position-fix time when available (so identical re-emitted fixes de-duplicate), else sample time.
            "observed_at": lastpos if lastpos else row.get("time"),
            "last_contact": row.get("lastcontact"),
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "baro_altitude_m": row.get("baroaltitude"),
            "geo_altitude_m": row.get("geoaltitude"),
            "on_ground": row.get("onground"),
            "velocity_ms": row.get("velocity"),
            "heading_deg": row.get("heading"),
            "vertical_rate_ms": row.get("vertrate"),
            "squawk": row.get("squawk"),
            "callsign": row.get("callsign"),
            "extra": {
                "sample_time": row.get("time"),
                "alert": row.get("alert"),
                "spi": row.get("spi"),
                "serials": (row.get("serials") or "")[:128],
            },
        }
