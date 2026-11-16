from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIAnalysis(Base):
    """Every AI request is recorded: who, provider/model/prompt version, outcome. Generated text stays here as
    AI output and is never copied into anomaly or detection records."""

    __tablename__ = "ai_analyses"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('anomaly_explanation','aircraft_investigation','threat_correlation')", name="kind_valid"
        ),
        CheckConstraint("status IN ('OK','INVALID_OUTPUT','PROVIDER_ERROR')", name="status_valid"),
        Index("ix_ai_anomaly", "anomaly_id", "created_at"),
        Index("ix_ai_aircraft", "aircraft_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    anomaly_id: Mapped[int | None] = mapped_column(ForeignKey("anomalies.id", ondelete="SET NULL"))
    aircraft_id: Mapped[int | None] = mapped_column(ForeignKey("aircraft.id", ondelete="SET NULL"))
    requested_by: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    input_sha256: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AISettings(Base):
    """Runtime provider/model selection (single row). Secrets and base URLs stay in the environment only."""

    __tablename__ = "ai_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    provider: Mapped[str | None] = mapped_column(String(16))
    ollama_model: Mapped[str | None] = mapped_column(String(128))
    openrouter_model: Mapped[str | None] = mapped_column(String(128))
    updated_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
