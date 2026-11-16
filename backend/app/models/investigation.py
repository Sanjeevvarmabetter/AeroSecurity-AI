from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Investigation(Base):
    """Investigation case workspace: tied to an anomaly, an aircraft, or a standalone incident."""

    __tablename__ = "investigations"
    __table_args__ = (
        Index("ix_investigation_aircraft", "aircraft_id"),
        Index("ix_investigation_anomaly", "anomaly_id"),
        Index("ix_investigation_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    anomaly_id: Mapped[int | None] = mapped_column(
        ForeignKey("anomalies.id", ondelete="CASCADE"), nullable=True
    )
    aircraft_id: Mapped[int | None] = mapped_column(
        ForeignKey("aircraft.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), server_default="Investigation Case")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), server_default="IN_PROGRESS"
    )  # NEW, IN_PROGRESS, UNDER_REVIEW, ESCALATED, CLOSED, FALSE_POSITIVE
    severity: Mapped[str] = mapped_column(String(16), server_default="MEDIUM")  # LOW, MEDIUM, HIGH, CRITICAL
    opened_by: Mapped[str] = mapped_column(String(64))  # principal, e.g. "analyst:3fa9c21b"
    lead_analyst: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    notes = relationship(
        "InvestigationNote",
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="InvestigationNote.created_at.desc()",
    )


class InvestigationNote(Base):
    __tablename__ = "investigation_notes"
    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        Index("ix_note_investigation", "investigation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"))
    author: Mapped[str] = mapped_column(String(64))  # authenticated principal
    claimed_name: Mapped[str | None] = mapped_column(
        String(64)
    )  # self-asserted display name; NOT authenticated
    body: Mapped[str] = mapped_column(Text)  # plain text only; clients must never render it as HTML
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    investigation = relationship("Investigation", back_populates="notes")
