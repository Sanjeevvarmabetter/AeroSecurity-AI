"""Pure data types shared by detection rules. Rules never touch the database."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}


class DataQuality(StrEnum):
    GOOD = "GOOD"  # every field the rule relied on was present and unflagged
    PARTIAL = "PARTIAL"  # some inputs were missing, from a lower-quality source, or across a gap
    DEGRADED = "DEGRADED"  # the finding is itself about defective data


@dataclass(frozen=True, slots=True)
class Obs:
    """One stored observation as seen by rules. SI units, UTC."""

    id: int
    t: datetime
    lat: float | None = None
    lon: float | None = None
    baro_altitude_m: float | None = None
    geo_altitude_m: float | None = None
    on_ground: bool | None = None
    velocity_ms: float | None = None
    heading_deg: float | None = None
    vertical_rate_ms: float | None = None
    squawk: str | None = None
    callsign: str | None = None
    position_source: int | None = None  # OpenSky: 0 ADS-B, 1 ASTERIX, 2 MLAT, 3 FLARM
    source: str = "unknown"
    last_contact: datetime | None = None
    ingested_at: datetime | None = None
    issues: tuple[str, ...] = ()  # validation issues recorded at ingestion

    @property
    def ts(self) -> float:
        return self.t.timestamp()

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass(frozen=True, slots=True)
class AircraftInfo:
    icao24: str
    registration: str | None = None
    aircraft_type: str | None = None


@dataclass(frozen=True, slots=True)
class AirportTraffic:
    ident: str
    name: str
    hourly: dict[datetime, int]  # hour start (UTC) -> distinct aircraft observed within the radius


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    kind: str  # "observation" | "metric" | "context"
    payload: dict[str, Any]
    observation_id: int | None = None


@dataclass(slots=True)
class Finding:
    """A rule's structured output. `confidence` is confidence that the *data pattern* is real as described;
    it is NOT a probability of malicious activity."""

    rule_id: str
    detection_type: str
    severity: Severity
    confidence: float
    title: str
    description: str
    event_start: datetime
    event_end: datetime
    dedup_key: str
    data_quality: DataQuality = DataQuality.GOOD
    icao24: str | None = None
    airport_ident: str | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    sources: tuple[str, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    alternatives: tuple[str, ...] = ()  # benign / non-malicious explanations, always listed
