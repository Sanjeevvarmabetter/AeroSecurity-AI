from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
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

from app.models.base import Base


class ThreatIntelligence(Base):
    """An external document used as context. Stored with provenance and an explicit reliability statement.
    Content is untrusted; it is only ever passed to a model as delimited data."""

    __tablename__ = "threat_intelligence"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_intel_url"),
        CheckConstraint("origin IN ('arxiv','manual')", name="origin_valid"),
        CheckConstraint("char_length(excerpt) <= 4000", name="excerpt_length"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(128))  # e.g. "arXiv"
    source_url: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(300))
    authors: Mapped[str | None] = mapped_column(String(500))
    publication_date: Mapped[date | None] = mapped_column(Date)  # NULL when the source gives none
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    excerpt: Mapped[str] = mapped_column(Text)  # abstract or analyst-written summary, never full text
    reliability_notes: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    origin: Mapped[str] = mapped_column(String(8))
    added_by: Mapped[str] = mapped_column(String(64))


class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"
    __table_args__ = (
        CheckConstraint("subject_type IN ('anomaly','aircraft')", name="subject_type_valid"),
        Index("ix_report_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    subject_type: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    includes_ai: Mapped[bool] = mapped_column(default=False)
    ai_analysis_ids: Mapped[list[int]] = mapped_column(JSONB, default=list)
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB)
    markdown: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    owner: Mapped[str] = mapped_column(String(64))  # authenticated principal that created it
    title: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','tool')", name="role_valid"),
        Index("ix_chat_conv", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(48))
    tool_args: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tokens: Mapped[int | None] = mapped_column(Integer)
