"""Provider-independent ingestion types."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    """One validated state vector. SI units, UTC. None means the source did not supply a valid value."""

    icao24: str
    observed_at: datetime  # time of the position fix when known, else the state/last-contact time
    last_contact_at: datetime | None = None
    callsign: str | None = None
    lat: float | None = None
    lon: float | None = None
    baro_altitude_m: float | None = None
    geo_altitude_m: float | None = None
    on_ground: bool | None = None
    velocity_ms: float | None = None
    heading_deg: float | None = None
    vertical_rate_ms: float | None = None
    squawk: str | None = None
    position_source: int | None = None
    origin_country: str | None = None
    # Evidence for later detection (DET-006): validation issues, original values we refused to store, extras.
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rejection:
    """A record that cannot be stored at all (no usable identity or time)."""

    reason: str
    row: int | None = None


@dataclass
class ImportReport:
    source: str
    read: int = 0
    inserted: int = 0
    duplicates: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    field_issues: Counter[str] = field(default_factory=Counter)  # stored, but with a field nulled/flagged
    aircraft_touched: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "read": self.read,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "rejected": dict(self.rejected),
            "field_issues": dict(self.field_issues),
            "aircraft_touched": self.aircraft_touched,
        }
