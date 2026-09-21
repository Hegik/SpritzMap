"""Räumliche Hilfsfunktionen, die OSM-Sync und Gebietsimport gemeinsam nutzen."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def assign_areas(db: AsyncSession, city_id: int) -> None:
    """Ordnet alle Lokale einer Stadt ihrem Gebiet zu (Punkt-in-Polygon, einmal vorberechnet).

    Danach brauchen Gebietsstatistiken und der GeoServer-View keinen räumlichen Join mehr.
    """
    await db.execute(
        text("""
            UPDATE locations l
            SET area_id = (
                SELECT a.id FROM areas a
                WHERE a.city_id = l.city_id AND ST_Covers(a.geom, l.geom)
                LIMIT 1
            )
            WHERE l.city_id = :city_id
        """),
        {"city_id": city_id},
    )
