from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin


class Airport(CreatedAtMixin, Base):
    """Airport reference data (OurAirports schema subset)."""

    __tablename__ = "airports"

    id: Mapped[int] = mapped_column(primary_key=True)
    ident: Mapped[str] = mapped_column(String(16), unique=True)
    iata_code: Mapped[str | None] = mapped_column(String(3), index=True)
    name: Mapped[str] = mapped_column(String(256))
    airport_type: Mapped[str | None] = mapped_column(String(32))
    iso_country: Mapped[str | None] = mapped_column(String(2))
    elevation_ft: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326))
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))
