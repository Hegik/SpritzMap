from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from geoalchemy2.functions import ST_AsGeoJSON, ST_X, ST_Y
import json
from app.core.database import get_db
from app.models.location import Location
from app.models.price_entry import PriceEntry
from app.models.drink import Drink
from app.models.user import User
from app.core.config import settings
from app.api.deps import get_current_user

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/geojson")
async def get_locations_geojson(
    drink_id: int | None = Query(None),
    price_tier: str | None = Query(None, pattern="^(€|€€|€€€)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns GeoJSON FeatureCollection of all active locations with
    aggregated price data. Filtered by drink and/or price tier.
    """
    # Subquery: latest price per location+drink
    latest_price_sq = (
        select(
            PriceEntry.location_id,
            PriceEntry.drink_id,
            func.max(PriceEntry.reported_at).label("max_reported_at"),
        )
        .where(PriceEntry.is_current == True)
        .where(PriceEntry.unavailable == False)
        .group_by(PriceEntry.location_id, PriceEntry.drink_id)
        .subquery()
    )

    # Subquery: avg color_value from last 50 entries per location+drink
    color_sq = (
        select(
            PriceEntry.location_id,
            PriceEntry.drink_id,
            func.avg(PriceEntry.color_value).label("avg_color"),
        )
        .where(PriceEntry.is_current == True)
        .where(PriceEntry.unavailable == False)
        .group_by(PriceEntry.location_id, PriceEntry.drink_id)
        .subquery()
    )

    query = (
        select(
            Location,
            PriceEntry.price,
            PriceEntry.drink_id,
            PriceEntry.reported_at,
            Drink.name.label("drink_name"),
            Drink.color_hex,
            color_sq.c.avg_color,
            User.username,
            ST_X(Location.geom).label("lng"),
            ST_Y(Location.geom).label("lat"),
        )
        .join(latest_price_sq, Location.id == latest_price_sq.c.location_id)
        .join(
            PriceEntry,
            (PriceEntry.location_id == latest_price_sq.c.location_id)
            & (PriceEntry.drink_id == latest_price_sq.c.drink_id)
            & (PriceEntry.reported_at == latest_price_sq.c.max_reported_at),
        )
        .join(Drink, PriceEntry.drink_id == Drink.id)
        .outerjoin(User, PriceEntry.user_id == User.id)
        .join(
            color_sq,
            (color_sq.c.location_id == Location.id)
            & (color_sq.c.drink_id == PriceEntry.drink_id),
        )
        .where(Location.is_active == True)
        .where(Location.no_spritz == False)
    )

    if drink_id:
        query = query.where(PriceEntry.drink_id == drink_id)

    results = await db.execute(query)
    rows = results.all()

    features = []
    for row in rows:
        location, price, drink_id_val, reported_at, drink_name, color_hex, avg_color, username, lng, lat = row
        tier = settings.get_price_tier(price)

        if price_tier and tier != price_tier:
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "id": location.id,
                "name": location.name,
                "location_type": location.location_type.value,
                "address": f"{location.address_street or ''}, {location.address_postcode or ''} {location.address_city or ''}".strip(", "),
                "drink_id": drink_id_val,
                "drink_name": drink_name,
                "drink_color_hex": color_hex,
                "price": price,
                "price_tier": tier,
                "avg_color_value": round(avg_color or 128),
                "reported_by": username or "Gelöschter Nutzer",
                "reported_at": reported_at.strftime("%d.%m.%Y"),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/geojson/nodata")
async def get_nodata_locations_geojson(
    drink_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Returns active locations that have no current price entry for the given drink
    and have not been marked as unavailable for that drink."""
    has_entry_sq = (
        select(PriceEntry.location_id)
        .where(PriceEntry.drink_id == drink_id)
        .where(PriceEntry.is_current == True)
    )

    query = (
        select(
            Location,
            ST_X(Location.geom).label("lng"),
            ST_Y(Location.geom).label("lat"),
        )
        .where(Location.is_active == True)
        .where(Location.no_spritz == False)
        .where(Location.id.not_in(has_entry_sq))
    )

    results = await db.execute(query)
    rows = results.all()

    features = []
    for row in rows:
        location, lng, lat = row
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "id": location.id,
                "name": location.name,
                "location_type": location.location_type.value,
                "address": f"{location.address_street or ''}, {location.address_postcode or ''} {location.address_city or ''}".strip(", "),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/{location_id}/prices")
async def get_location_prices(
    location_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Returns all current prices for a location across all drink types."""
    latest_sq = (
        select(
            PriceEntry.drink_id,
            func.max(PriceEntry.reported_at).label("max_reported_at"),
        )
        .where(PriceEntry.location_id == location_id)
        .where(PriceEntry.is_current == True)
        .where(PriceEntry.unavailable == False)
        .group_by(PriceEntry.drink_id)
        .subquery()
    )

    query = (
        select(Drink.id, Drink.name, PriceEntry.price)
        .join(
            latest_sq,
            (PriceEntry.drink_id == latest_sq.c.drink_id)
            & (PriceEntry.reported_at == latest_sq.c.max_reported_at),
        )
        .join(Drink, PriceEntry.drink_id == Drink.id)
        .where(PriceEntry.location_id == location_id)
        .order_by(Drink.name)
    )

    results = await db.execute(query)
    return [
        {"drink_id": row.id, "drink_name": row.name, "price": float(row.price)}
        for row in results.all()
    ]


@router.post("/{location_id}/no-spritz")
async def mark_no_spritz(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a location as having no spritz at all — hides it from the map permanently."""
    result = await db.execute(select(Location).where(Location.id == location_id))
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    location.no_spritz = True
    await db.commit()
    return {"detail": "Location marked as no-spritz"}


@router.get("/geojson/empty")
async def get_empty_locations_geojson(db: AsyncSession = Depends(get_db)):
    """Returns active locations that have no current price entries."""
    query = (
        select(
            Location,
            ST_X(Location.geom).label("lng"),
            ST_Y(Location.geom).label("lat"),
        )
        .outerjoin(
            PriceEntry,
            (PriceEntry.location_id == Location.id) & (PriceEntry.is_current == True),
        )
        .where(Location.is_active == True)
        .where(Location.no_spritz == False)
        .where(PriceEntry.id == None)
    )

    results = await db.execute(query)
    rows = results.all()

    features = []
    for row in rows:
        location, lng, lat = row
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {
                "id": location.id,
                "name": location.name,
                "location_type": location.location_type.value,
                "address": f"{location.address_street or ''}, {location.address_postcode or ''} {location.address_city or ''}".strip(", "),
            },
        })

    return {"type": "FeatureCollection", "features": features}
