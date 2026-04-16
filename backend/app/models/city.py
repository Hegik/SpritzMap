from sqlalchemy import String, Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    bbox: Mapped[str] = mapped_column(String(100))  # "min_lat,min_lon,max_lat,max_lon"
    center_lat: Mapped[float] = mapped_column(Float)
    center_lon: Mapped[float] = mapped_column(Float)
    default_zoom: Mapped[int] = mapped_column(Integer, default=12)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    osm_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    wms_layer: Mapped[str | None] = mapped_column(String(200), nullable=True)

    locations: Mapped[list["Location"]] = relationship(back_populates="city")
