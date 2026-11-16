from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class AircraftObservation(CreatedAtMixin, Base):
    """One state-vector observation. All physical values are SI (m, m/s, degrees).

    Every field a provider may omit is nullable: nothing is assumed to be populated.
    """

    __tablename__ = "aircraft_observations"
    __table_args__ = (
        UniqueConstraint("aircraft_id", "data_source_id", "observed_at", name="uq_observation_identity"),
        Index("ix_obs_aircraft_time", "aircraft_id", "observed_at"),
        Index("ix_obs_observed_at", "observed_at"),
        Index("ix_obs_callsign", "callsign", postgresql_ops={"callsign": "text_pattern_ops"}),
        # GiST index on `position` is created automatically by GeoAlchemy2 (spatial_index=True).
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"))
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # position/state time (UTC)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    callsign: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[WKBElement | None] = mapped_column(Geometry("POINT", srid=4326))
    baro_altitude_m: Mapped[float | None] = mapped_column(Float)
    geo_altitude_m: Mapped[float | None] = mapped_column(Float)
    on_ground: Mapped[bool | None] = mapped_column(Boolean)
    velocity_ms: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    vertical_rate_ms: Mapped[float | None] = mapped_column(Float)
    squawk: Mapped[str | None] = mapped_column(String(4))
    position_source: Mapped[int | None] = mapped_column(SmallInteger)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # untrusted provider payload, kept for evidence
