import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Status = Literal["OPEN", "INVESTIGATING", "FALSE_POSITIVE", "RESOLVED"]
DataQuality = Literal["GOOD", "PARTIAL", "DEGRADED"]

_NAME = re.compile(r"^[A-Za-z0-9 ._@-]{1,64}$")


def _check_name(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not _NAME.match(v):
        raise ValueError("claimed_name may contain letters, digits, space and . _ @ -")
    return v


class AnomalyOut(BaseModel):
    anomaly_id: str  # "ANM-0001"
    id: int
    rule_id: str
    rule_name: str
    rule_version: str
    detection_type: str
    title: str
    severity: Severity
    confidence: float  # confidence in the data pattern, NOT a probability of malicious activity
    data_quality: DataQuality
    status: Status
    icao24: str | None
    registration: str | None
    airport_ident: str | None
    event_start: datetime
    event_end: datetime
    detected_at: datetime
    source_refs: list[str]
    has_investigation: bool
    notes_count: int


class EvidenceOut(BaseModel):
    ordinal: int
    kind: str
    observation_id: int | None
    payload: dict[str, Any]


class NoteOut(BaseModel):
    id: int
    author: str
    claimed_name: str | None  # self-asserted, unauthenticated
    body: str  # plain text; never render as HTML
    created_at: datetime


class InvestigationOut(BaseModel):
    id: int
    opened_by: str
    opened_at: datetime
    closed_at: datetime | None


class TimelineEntry(BaseModel):
    at: datetime
    kind: Literal["detected", "investigation_opened", "status_changed", "note"]
    actor: str | None
    text: str
    data: dict[str, Any] = Field(default_factory=dict)


class RuleInfo(BaseModel):
    id: str
    name: str
    description: str
    version: str


class AnomalyDetail(AnomalyOut):
    description: str
    summary: dict[str, Any]
    alternatives: list[str]
    rule: RuleInfo
    evidence: list[EvidenceOut]
    investigation: InvestigationOut | None
    notes: list[NoteOut]
    timeline: list[TimelineEntry]
    allowed_transitions: list[Status]


class AnomalyStats(BaseModel):
    total: int
    by_severity: dict[str, int]
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_rule: dict[str, int]


class StatusChange(BaseModel):
    status: Status
    reason: Annotated[str, Field(max_length=1000)] = ""
    claimed_name: str | None = None

    @field_validator("claimed_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _check_name(v)

    @field_validator("reason")
    @classmethod
    def _strip(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("invalid character")
        return v.strip()


class NoteCreate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=5000)]
    claimed_name: str | None = None

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = v.strip()
        if not v or "\x00" in v:
            raise ValueError("note must contain text")
        return v

    @field_validator("claimed_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _check_name(v)


class InvestigateRequest(BaseModel):
    note: Annotated[str, Field(max_length=5000)] = ""
    claimed_name: str | None = None

    @field_validator("claimed_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _check_name(v)


class InvestigationListItem(BaseModel):
    id: int
    anomaly_id: str
    anomaly_title: str
    severity: Severity
    status: Status
    icao24: str | None
    opened_by: str
    opened_at: datetime
    closed_at: datetime | None
    notes_count: int
    last_activity: datetime


class EmergencyOut(BaseModel):
    anomaly_id: str
    icao24: str
    registration: str | None
    callsign: str | None
    squawk: str
    meaning: str
    severity: Severity
    status: Status
    confidence: float
    transient: bool  # single observation: possibly a code passing through while being dialled
    first_seen: datetime
    last_seen: datetime
    duration_s: float
    observations: int
    last_known_position: dict[str, float] | None
    sources: list[str]


class Me(BaseModel):
    role: str
    key_id: str
