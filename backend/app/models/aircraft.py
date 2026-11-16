from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class Aircraft(CreatedAtMixin, Base):
    """Aircraft identity/metadata only. Time-series data lives in aircraft_observations.

    registration/aircraft_type are NULL unless a source actually provides them.
    """

    __tablename__ = "aircraft"
    __table_args__ = (
        CheckConstraint("icao24 ~ '^[0-9a-f]{6}$'", name="icao24_format"),
        Index(
            "ix_aircraft_registration", "registration", postgresql_ops={"registration": "text_pattern_ops"}
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    icao24: Mapped[str] = mapped_column(String(6), unique=True)
    registration: Mapped[str | None] = mapped_column(String(16))
    aircraft_type: Mapped[str | None] = mapped_column(String(64))
    origin_country: Mapped[str | None] = mapped_column(String(64))
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Descriptive metadata: NULL unless a registered source supplied it (metadata_source_id says which).
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    operator: Mapped[str | None] = mapped_column(String(128))
    metadata_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
