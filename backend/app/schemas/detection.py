from typing import Any

from pydantic import BaseModel, Field


class RuleOut(BaseModel):
    id: str
    name: str
    description: str
    version: str
    enabled: bool
    config: dict[str, Any]
    findings_count: int = 0
    category: str = "DETECTION"


class RuleConfigUpdate(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class DetectionRunRequest(BaseModel):
    rule_ids: list[str] | None = None
    icao24: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{6}$")
