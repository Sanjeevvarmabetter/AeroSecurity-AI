from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class DetectionRule(CreatedAtMixin, Base):
    """Registry of rules known to the engine, with operator-editable configuration."""

    __tablename__ = "detection_rules"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "DET-001"
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Anomaly(CreatedAtMixin, Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint("rule_id", "rule_version", "dedup_key", name="uq_anomaly_identity"),
        CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="severity_valid"),
        CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','FALSE_POSITIVE','RESOLVED')", name="status_valid"
        ),
        CheckConstraint("data_quality IN ('GOOD','PARTIAL','DEGRADED')", name="data_quality_valid"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("aircraft_id IS NOT NULL OR airport_ident IS NOT NULL", name="has_subject"),
        Index("ix_anomaly_aircraft_time", "aircraft_id", "event_start"),
        Index("ix_anomaly_severity", "severity"),
        Index("ix_anomaly_type", "detection_type"),
        Index("ix_anomaly_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)  # public id is "ANM-%04d" % id
    rule_id: Mapped[str] = mapped_column(ForeignKey("detection_rules.id"))
    rule_version: Mapped[str] = mapped_column(String(16))
    aircraft_id: Mapped[int | None] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"))
    airport_ident: Mapped[str | None] = mapped_column(String(16))
    detection_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[float] = mapped_column(Float)  # confidence in the data pattern; NOT P(malicious)
    data_quality: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="OPEN", server_default="OPEN")
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dedup_key: Mapped[str] = mapped_column(String(128))
    source_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # rule metrics + alternatives


class Evidence(Base):
    """Ordered supporting items for an anomaly: observation references and computed metrics."""

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_anomaly", "anomaly_id", "ordinal"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    anomaly_id: Mapped[int] = mapped_column(ForeignKey("anomalies.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("aircraft_observations.id", ondelete="SET NULL")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
