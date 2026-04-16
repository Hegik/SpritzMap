from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.city import City

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("/")
async def list_cities(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(City).where(City.is_active == True).order_by(City.name)
    )
    cities = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "center_lat": c.center_lat,
            "center_lon": c.center_lon,
            "default_zoom": c.default_zoom,
            "wms_layer": c.wms_layer,
        }
        for c in cities
    ]
