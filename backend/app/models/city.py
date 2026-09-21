from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer, BigInteger, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
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
    # Veraltet: früher ein GeoServer-Layer pro Stadt; heute ein gemeinsamer Layer mit viewparams city_id
    wms_layer: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # OSM-Grenzrelation → exakte Stadtfläche für Import und Stadtzuordnung (statt Bbox)
    osm_relation_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    boundary: Mapped[object | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )

    # Gebiete für die Zusammenfassung: "osm" (automatisch), "upload" (hat Vorrang), "none"
    area_source: Mapped[str] = mapped_column(String(10), default="none", server_default="none")
    area_admin_level: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # OSM-Sync-Status (gestaffelte Warteschlange, siehe services/osm_sync.py)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sync_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    locations: Mapped[list["Location"]] = relationship(back_populates="city")
    areas: Mapped[list["Area"]] = relationship(back_populates="city", cascade="all, delete-orphan")
