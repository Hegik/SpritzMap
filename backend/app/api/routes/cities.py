from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, exists
from app.core.database import get_db
from app.models.area import Area
from app.models.city import City

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("/")
async def list_cities(db: AsyncSession = Depends(get_db)):
    has_areas = exists().where(Area.city_id == City.id)
    result = await db.execute(
        select(City, has_areas.label("has_areas")).where(City.is_active == True).order_by(City.name)
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "state": c.state,
            "bbox": c.bbox,
            "center_lat": c.center_lat,
            "center_lon": c.center_lon,
            "default_zoom": c.default_zoom,
            "has_areas": bool(areas),
            "wms_layer": c.wms_layer,  # veraltet, bleibt bis zur Umstellung aller Clients
        }
        for c, areas in result.all()
    ]


@router.get("/locate")
async def locate_city(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    """Stadt, in der ein Punkt liegt (Grenze, sonst Bbox) – für die Vorauswahl per Standort."""
    row = (await db.execute(
        text("""
            SELECT id FROM cities
            WHERE is_active AND (
                (boundary IS NOT NULL AND ST_Covers(boundary, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)))
                OR (boundary IS NULL
                    AND :lat BETWEEN split_part(bbox, ',', 1)::float AND split_part(bbox, ',', 3)::float
                    AND :lon BETWEEN split_part(bbox, ',', 2)::float AND split_part(bbox, ',', 4)::float)
            )
            ORDER BY boundary IS NULL
            LIMIT 1
        """),
        {"lat": lat, "lon": lon},
    )).first()
    return {"city_id": row.id if row else None}
