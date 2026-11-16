from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

InvestigationStatus = Literal["NEW", "IN_PROGRESS", "UNDER_REVIEW", "ESCALATED", "CLOSED", "FALSE_POSITIVE"]
InvestigationSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class CaseNoteOut(BaseModel):
    id: int
    author: str
    claimed_name: str | None
    body: str
    created_at: datetime


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    icao24: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{6}$")
    anomaly_id: str | None = Field(default=None, pattern=r"^ANM-\d{1,9}$")
    severity: InvestigationSeverity = "MEDIUM"
    initial_note: str | None = Field(default=None, max_length=5000)
    claimed_name: str | None = Field(default=None, max_length=64)


class CaseStatusUpdate(BaseModel):
    status: InvestigationStatus
    reason: str | None = Field(default=None, max_length=1000)
    claimed_name: str | None = Field(default=None, max_length=64)


class CaseNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    claimed_name: str | None = Field(default=None, max_length=64)


class CaseListItem(BaseModel):
    id: int
    title: str
    description: str | None
    status: str
    severity: str
    opened_by: str
    lead_analyst: str | None
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    aircraft_id: int | None
    icao24: str | None
    anomaly_id: str | None  # public format ANM-0042
    anomaly_title: str | None
    notes_count: int


class TimelineEvent(BaseModel):
    timestamp: datetime
    actor: str
    action: str
    details: dict[str, object]


class CaseDetail(CaseListItem):
    notes: list[CaseNoteOut]
    timeline: list[TimelineEvent]
    aircraft_summary: dict[str, object] | None = None
    anomaly_summary: dict[str, object] | None = None
