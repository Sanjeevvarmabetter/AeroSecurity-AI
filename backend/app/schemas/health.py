from typing import Literal

from pydantic import BaseModel

Status = Literal["ok", "degraded", "down"]


class ComponentHealth(BaseModel):
    status: Status
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Status
    version: str
    environment: str
    components: dict[str, ComponentHealth]
