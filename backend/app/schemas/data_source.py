from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    enabled: bool
    terms_url: str | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
