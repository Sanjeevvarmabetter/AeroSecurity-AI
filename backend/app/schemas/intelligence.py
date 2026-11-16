import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Provider = Literal["ollama", "openrouter"]
_MODEL = re.compile(r"^[A-Za-z0-9._:/@+-]{1,128}$")


def _check_model(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not _MODEL.match(v):
        raise ValueError("model id may contain letters, digits and . _ : / @ + -")
    return v


class _Override(BaseModel):
    provider: Provider | None = None
    model: str | None = None

    @field_validator("model")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        return _check_model(v)


class AnomalyExplanationRequest(_Override):
    anomaly_id: Annotated[str, Field(pattern=r"^ANM-\d{1,9}$")]


class AircraftInvestigationRequest(_Override):
    icao24: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{6}$")]


DISCLAIMER = (
    "AI-generated interpretation. Not a verified security finding. The deterministic detection (severity, "
    "confidence, status) is unchanged by this analysis."
)


class AnalysisOut(BaseModel):
    analysis_id: int
    kind: Literal["anomaly_explanation", "aircraft_investigation", "threat_correlation"]
    subject: str  # anomaly id or ICAO24
    provider: str
    model: str
    prompt_version: str
    status: Literal["OK", "INVALID_OUTPUT", "PROVIDER_ERROR"]
    ai_generated: Literal[True] = True
    disclaimer: str = DISCLAIMER
    output: dict[str, Any] | None
    warnings: list[str]
    error: str | None
    requested_by: str
    created_at: datetime
    latency_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    deterministic: dict[str, Any] | None  # echo of the unchanged detection, for side-by-side display


class ProviderStatus(BaseModel):
    name: Provider
    configured: bool
    current_model: str | None
    healthy: bool | None  # None when not checked
    detail: str | None
    models: list[str] | None
    base_url: str | None  # shown for Ollama (configuration, not a secret)


class AISettingsOut(BaseModel):
    provider: Provider
    source: Literal["environment", "database"]
    providers: list[ProviderStatus]
    limits: dict[str, float | int]


class AISettingsUpdate(BaseModel):
    provider: Provider | None = None
    ollama_model: str | None = None
    openrouter_model: str | None = None

    @field_validator("ollama_model", "openrouter_model")
    @classmethod
    def _model(cls, v: str | None) -> str | None:
        return _check_model(v)


# -- chat, reports, threat intel ----------------------------------------------------------------------
class ChatRequest(_Override):
    conversation_id: Annotated[str | None, Field(pattern=r"^[0-9a-f\-]{36}$")] = None
    message: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("message")
    @classmethod
    def _msg(cls, v: str) -> str:
        v = v.strip()
        if not v or "\x00" in v:
            raise ValueError("message must contain text")
        return v


class ToolCallOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    ok: bool
    error: str | None = None
    records: list[str] = []


class CitationOut(BaseModel):
    ref: str
    note: str = ""
    kind: Literal["anomaly", "aircraft", "document", "airport", "trajectory", "observations", "other"]
    link: str | None  # in-app path, only for kinds the UI can open


class ChatOut(BaseModel):
    conversation_id: str
    answer: str
    citations: list[CitationOut]
    tool_calls: list[ToolCallOut]
    warnings: list[str]
    provider: str
    model: str
    ai_generated: Literal[True] = True
    disclaimer: str = DISCLAIMER


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: str | None
    tool_args: dict[str, Any] | None
    citations: list[CitationOut] | None
    warnings: list[str] | None
    provider: str | None
    model: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    owner: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[ChatMessageOut]


class ThreatCorrelationRequest(_Override):
    anomaly_id: Annotated[str, Field(pattern=r"^ANM-\d{1,9}$")]


class ReportRequest(BaseModel):
    anomaly_id: Annotated[str | None, Field(pattern=r"^ANM-\d{1,9}$")] = None
    icao24: Annotated[str | None, Field(pattern=r"^[0-9a-fA-F]{6}$")] = None
    include_ai: bool = False

    @model_validator(mode="after")
    def _one_subject(self) -> "ReportRequest":
        if (self.icao24 is None) == (self.anomaly_id is None):
            raise ValueError("provide exactly one of anomaly_id or icao24")
        return self


class ReportMeta(BaseModel):
    id: int
    title: str
    subject_type: Literal["anomaly", "aircraft"]
    subject: str
    created_by: str
    created_at: datetime
    includes_ai: bool
    status: str = "UNREVIEWED"


class ReportOut(ReportMeta):
    structured: dict[str, Any]
    markdown: str


class IntelCreate(BaseModel):
    source_name: Annotated[str, Field(min_length=2, max_length=128)]
    source_url: Annotated[str, Field(max_length=512)]
    title: Annotated[str, Field(min_length=3, max_length=300)]
    authors: Annotated[str | None, Field(max_length=500)] = None
    publication_date: datetime | None = None
    excerpt: Annotated[
        str, Field(min_length=20, max_length=4000, description="abstract or your own summary, not full text")
    ]
    reliability_notes: Annotated[
        str, Field(min_length=10, max_length=1000, description="required: limits of this source")
    ]
    tags: Annotated[list[str], Field(max_length=10)] = []


class IntelOut(BaseModel):
    id: int
    source_name: str
    source_url: str
    title: str
    authors: str | None
    publication_date: str | None
    retrieved_at: datetime
    excerpt: str
    reliability_notes: str
    tags: list[str]
    origin: str
    added_by: str


class ArxivImport(BaseModel):
    query: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 .\-+]{1,99}$")]
    max_results: Annotated[int, Field(ge=1, le=10)] = 5
