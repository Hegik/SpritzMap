from datetime import datetime
from sqlalchemy import String, Boolean, BigInteger, Integer, Enum as SAEnum, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
import enum
from app.core.database import Base


class LocationType(str, enum.Enum):
    bar = "bar"
    beer_garden = "beer_garden"
    restaurant = "restaurant"
    cafe = "cafe"
    other = "other"


class Location(Base):
    __tablename__ = "locations"
    # OSM-IDs sind nur pro Typ eindeutig (node 123 ≠ way 123)
    __table_args__ = (UniqueConstraint("osm_type", "osm_id", name="uq_locations_osm_type_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    osm_type: Mapped[str] = mapped_column(String(10))  # node, way, relation
    name: Mapped[str] = mapped_column(String(255))
    location_type: Mapped[LocationType] = mapped_column(SAEnum(LocationType), default=LocationType.bar)

    # PostGIS point (EPSG:4326)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326))

    address_street: Mapped[str | None] = mapped_column(String(255))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_postcode: Mapped[str | None] = mapped_column(String(20))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    no_spritz: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Jede Location gehört genau zu einer Stadt → Statistiken strikt pro Stadt
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), index=True)
    city: Mapped["City"] = relationship(back_populates="locations")

    # Vorberechnete Gebietszuordnung (Punkt-in-Polygon), wird bei Sync und Gebietsimport aktualisiert
    area_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Zuletzt im OSM-Sync gesehen; lange nicht gesehen → Deaktivierung
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    price_entries: Mapped[list["PriceEntry"]] = relationship(back_populates="location")
