from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from app.core.database import Base


class Area(Base):
    """Teilgebiet einer Stadt (Stadtteil/LOR) für die Zusammenfassung auf der Karte."""

    __tablename__ = "areas"
    __table_args__ = (UniqueConstraint("city_id", "key", name="uq_areas_city_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    admin_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(10))  # "osm" | "upload"
    geom: Mapped[object] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))

    city: Mapped["City"] = relationship(back_populates="areas")
