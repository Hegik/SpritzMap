from sqlalchemy import String, Float, Boolean, BigInteger, Enum as SAEnum
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

    id: Mapped[int] = mapped_column(primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    osm_type: Mapped[str] = mapped_column(String(10))  # node, way, relation
    name: Mapped[str] = mapped_column(String(255))
    location_type: Mapped[LocationType] = mapped_column(SAEnum(LocationType), default=LocationType.bar)

    # PostGIS point (EPSG:4326)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326))

    address_street: Mapped[str | None] = mapped_column(String(255))
    address_city: Mapped[str | None] = mapped_column(String(100))
    address_postcode: Mapped[str | None] = mapped_column(String(20))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    price_entries: Mapped[list["PriceEntry"]] = relationship(back_populates="location")
