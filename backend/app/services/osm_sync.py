"""
Syncs bar/restaurant/beer garden locations from OpenStreetMap via Overpass API.
Runs on startup and then every OSM_SYNC_INTERVAL_HOURS hours.
"""
import asyncio
import httpx
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from app.models.city import City
from app.models.location import Location, LocationType

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OSM_AMENITY_TO_TYPE: dict[str, LocationType] = {
    "bar": LocationType.bar,
    "pub": LocationType.bar,
    "biergarten": LocationType.beer_garden,
    "restaurant": LocationType.restaurant,
    "cafe": LocationType.cafe,
}

OVERPASS_QUERY_TEMPLATE = """
[out:json][timeout:60];
(
  node["amenity"~"bar|pub|biergarten|restaurant|cafe"]({bbox});
  way["amenity"~"bar|pub|biergarten|restaurant|cafe"]({bbox});
);
out center;
"""


async def fetch_osm_locations(bbox: str) -> list[dict]:
    query = OVERPASS_QUERY_TEMPLATE.format(bbox=bbox)
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(OVERPASS_URL, data={"data": query})
        response.raise_for_status()
        return response.json().get("elements", [])


def _parse_location(element: dict) -> dict | None:
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None

    # Ways have a 'center' key; nodes have lat/lon directly
    lat = element.get("lat") or (element.get("center") or {}).get("lat")
    lon = element.get("lon") or (element.get("center") or {}).get("lon")
    if not lat or not lon:
        return None

    amenity = tags.get("amenity", "other")
    location_type = OSM_AMENITY_TO_TYPE.get(amenity, LocationType.other)

    return {
        "osm_id": element["id"],
        "osm_type": element["type"],
        "name": name,
        "location_type": location_type,
        "lat": float(lat),
        "lon": float(lon),
        "address_street": tags.get("addr:street"),
        "address_city": tags.get("addr:city"),
        "address_postcode": tags.get("addr:postcode"),
    }


async def sync_osm_locations(db: AsyncSession, city: City) -> int:
    logger.info("Starting OSM sync for city '%s' (bbox: %s)", city.name, city.bbox)
    elements = await fetch_osm_locations(city.bbox)
    logger.info("Fetched %d OSM elements for '%s'", len(elements), city.name)

    created = 0
    updated = 0

    for element in elements:
        parsed = _parse_location(element)
        if not parsed:
            continue

        result = await db.execute(
            select(Location).where(Location.osm_id == parsed["osm_id"])
        )
        existing = result.scalar_one_or_none()
        geom = from_shape(Point(parsed["lon"], parsed["lat"]), srid=4326)

        if existing:
            existing.name = parsed["name"]
            existing.location_type = parsed["location_type"]
            existing.geom = geom
            existing.address_street = parsed["address_street"]
            existing.address_city = parsed["address_city"]
            existing.address_postcode = parsed["address_postcode"]
            existing.is_active = True
            # Assign city if not yet set
            if existing.city_id is None:
                existing.city_id = city.id
            updated += 1
        else:
            location = Location(
                osm_id=parsed["osm_id"],
                osm_type=parsed["osm_type"],
                name=parsed["name"],
                location_type=parsed["location_type"],
                geom=geom,
                address_street=parsed["address_street"],
                address_city=parsed["address_city"],
                address_postcode=parsed["address_postcode"],
                city_id=city.id,
            )
            db.add(location)
            created += 1

    await db.commit()
    logger.info("OSM sync complete for '%s': %d created, %d updated", city.name, created, updated)
    return created + updated


async def sync_all_cities(db: AsyncSession) -> None:
    result = await db.execute(
        select(City).where(City.osm_sync_enabled == True, City.is_active == True)
    )
    cities = result.scalars().all()

    for i, city in enumerate(cities):
        try:
            await sync_osm_locations(db, city)
        except Exception as e:
            logger.warning("OSM sync failed for city '%s': %s", city.name, e)
        if i < len(cities) - 1:
            await asyncio.sleep(2)  # Overpass rate limit between cities
