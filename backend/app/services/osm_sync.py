"""
Syncs bar/restaurant/beer garden locations from OpenStreetMap via Overpass API.

Für viele Städte ausgelegt:
- Abfrage über die Stadtfläche (OSM-Grenzrelation) statt Bbox → keine Überlappung zwischen Nachbarstädten;
  bei Timeout Fallback auf 2×2-Kacheln der Bbox, gefiltert nach der Stadtgrenze
- Bulk-Upsert statt einer Abfrage pro Element
- gestaffelte Warteschlange: der Scheduler synchronisiert alle 10 Minuten höchstens EINE fällige Stadt
- Postgres-Advisory-Lock → nie zwei Syncs gleichzeitig (mehrere Worker, manueller Start)
- Lokale werden erst deaktiviert, wenn sie 7 Tage lang in erfolgreichen Läufen fehlen
"""
import logging
import random
from datetime import datetime, timedelta, timezone

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.prepared import prep
from sqlalchemy import select, text, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.city import City
from app.models.location import Location, LocationType
from app.models.osm_sync_run import OsmSyncRun
from app.services.spatial import assign_areas

logger = logging.getLogger(__name__)

# Hauptserver zuerst; bei Überlastung (429/5xx/Timeout) auf öffentliche Mirrors ausweichen
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
# Overpass lehnt generische Client-User-Agents (z. B. "python-httpx/…") mit 406 ab
OVERPASS_HEADERS = {"User-Agent": "SpritzMap/1.0 (+https://spritzmap.hegik.de)"}
OVERPASS_AREA_OFFSET = 3_600_000_000  # Overpass-Area-ID = Relation-ID + Offset

AMENITY_REGEX = "bar|pub|biergarten|restaurant|cafe"
OSM_AMENITY_TO_TYPE: dict[str, LocationType] = {
    "bar": LocationType.bar,
    "pub": LocationType.bar,
    "biergarten": LocationType.beer_garden,
    "restaurant": LocationType.restaurant,
    "cafe": LocationType.cafe,
}

UPSERT_CHUNK = 1000
DEACTIVATE_AFTER = timedelta(days=7)
RETRY_BASE = timedelta(minutes=30)
RETRY_MAX = timedelta(hours=12)
SYNC_LOCK_KEY = 815_001  # beliebige, projektweit feste Advisory-Lock-ID


class OverpassUnavailable(Exception):
    """Alle Overpass-Server überlastet/nicht erreichbar (nicht: fehlerhafte Anfrage)."""


def _area_query(relation_id: int) -> str:
    return f"""
[out:json][timeout:180];
area(id:{OVERPASS_AREA_OFFSET + relation_id})->.a;
(
  node["amenity"~"{AMENITY_REGEX}"](area.a);
  way["amenity"~"{AMENITY_REGEX}"](area.a);
);
out center;
"""


def _bbox_query(bbox: str) -> str:
    return f"""
[out:json][timeout:180];
(
  node["amenity"~"{AMENITY_REGEX}"]({bbox});
  way["amenity"~"{AMENITY_REGEX}"]({bbox});
);
out center;
"""


async def overpass(query: str, timeout: float = 200) -> tuple[dict, str]:
    """Führt eine Overpass-Abfrage aus, mit Mirror-Fallback. Gibt (JSON, Server-URL) zurück."""
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, headers=OVERPASS_HEADERS) as client:
        for url in OVERPASS_URLS:
            try:
                response = await client.post(url, data={"data": query})
                response.raise_for_status()
                data = response.json()
                # Overpass meldet serverseitige Timeouts teils mit 200 + "remark"
                remark = data.get("remark") or ""
                if "timed out" in remark or "out of memory" in remark:
                    raise OverpassUnavailable(remark)
                return data, url
            except httpx.HTTPStatusError as e:
                # 4xx außer 429 = Fehler in unserer Anfrage → Mirror würde gleich antworten
                if e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                last_error = e
            except (httpx.TransportError, OverpassUnavailable, ValueError) as e:
                last_error = e
            logger.warning("Overpass %s nicht verfügbar (%s), versuche nächsten Server", url, last_error)
    raise OverpassUnavailable(str(last_error))


def _split_bbox(bbox: str) -> list[str]:
    min_lat, min_lon, max_lat, max_lon = (float(v) for v in bbox.split(","))
    mid_lat, mid_lon = (min_lat + max_lat) / 2, (min_lon + max_lon) / 2
    return [
        f"{a},{b},{c},{d}"
        for a, c in ((min_lat, mid_lat), (mid_lat, max_lat))
        for b, d in ((min_lon, mid_lon), (mid_lon, max_lon))
    ]


async def fetch_city_elements(city: City) -> tuple[list[dict], str]:
    """Holt alle relevanten OSM-Elemente einer Stadt. Gibt (Elemente, Server) zurück."""
    if city.osm_relation_id:
        try:
            data, server = await overpass(_area_query(city.osm_relation_id))
            return data.get("elements", []), server
        except OverpassUnavailable as e:
            logger.warning("Flächenabfrage für '%s' fehlgeschlagen (%s) → Kachel-Fallback", city.name, e)

    tiles = _split_bbox(city.bbox) if city.osm_relation_id else [city.bbox]
    seen: dict[tuple[str, int], dict] = {}
    server = ""
    for tile in tiles:
        data, server = await overpass(_bbox_query(tile))
        for el in data.get("elements", []):
            seen[(el["type"], el["id"])] = el
    return list(seen.values()), server


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
        "name": name[:255],
        "location_type": location_type,
        "lat": float(lat),
        "lon": float(lon),
        "address_street": tags.get("addr:street"),
        "address_city": tags.get("addr:city"),
        "address_postcode": tags.get("addr:postcode"),
    }


async def sync_osm_locations(db: AsyncSession, city: City) -> OsmSyncRun:
    """Synchronisiert eine Stadt und protokolliert den Lauf. Wirft bei Fehlern (nach Protokollierung)."""
    run = OsmSyncRun(city_id=city.id)
    db.add(run)
    await db.commit()

    try:
        logger.info("Starting OSM sync for city '%s'", city.name)
        elements, server = await fetch_city_elements(city)
        run.server = server
        run.elements = len(elements)

        # Nur Punkte innerhalb der Stadtgrenze gehören zu dieser Stadt (Bbox-Kacheln ragen darüber hinaus)
        boundary = prep(to_shape(city.boundary)) if city.boundary is not None else None
        now = datetime.now(timezone.utc)
        rows = []
        for el in elements:
            p = _parse_location(el)
            if not p:
                continue
            if boundary is not None and not boundary.covers(Point(p["lon"], p["lat"])):
                continue
            rows.append({
                "osm_id": p["osm_id"],
                "osm_type": p["osm_type"],
                "name": p["name"],
                "location_type": p["location_type"],
                "geom": f"SRID=4326;POINT({p['lon']} {p['lat']})",
                "address_street": p["address_street"],
                "address_city": p["address_city"],
                "address_postcode": p["address_postcode"],
                "city_id": city.id,
                "is_active": True,
                "last_seen_at": now,
            })

        created = updated = 0
        for i in range(0, len(rows), UPSERT_CHUNK):
            stmt = pg_insert(Location).values(rows[i:i + UPSERT_CHUNK])
            update_cols = {
                c: stmt.excluded[c]
                for c in ("name", "location_type", "geom", "address_street", "address_city",
                          "address_postcode", "is_active", "last_seen_at")
            }
            # Mit Stadtgrenze ist die Zuordnung eindeutig; ohne (Legacy-Bbox) keine fremden Lokale übernehmen
            if boundary is not None:
                update_cols["city_id"] = stmt.excluded.city_id
                stmt = stmt.on_conflict_do_update(constraint="uq_locations_osm_type_id", set_=update_cols)
            else:
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_locations_osm_type_id", set_=update_cols,
                    where=Location.city_id == city.id,
                )
            result = await db.execute(stmt.returning(literal_column("(xmax = 0)").label("inserted")))
            inserted = [r.inserted for r in result]
            created += sum(inserted)
            updated += len(inserted) - sum(inserted)

        # Erst nach erfolgreichem Lauf: lange nicht gesehene Lokale deaktivieren (Einträge bleiben erhalten)
        deactivated = (await db.execute(
            text("""
                UPDATE locations SET is_active = false
                WHERE city_id = :city_id AND is_active AND last_seen_at < :cutoff
            """),
            {"city_id": city.id, "cutoff": now - DEACTIVATE_AFTER},
        )).rowcount

        await assign_areas(db, city.id)

        run.created, run.updated, run.deactivated = created, updated, deactivated
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        city.last_sync_at = run.finished_at
        city.last_sync_status = "success"
        city.last_sync_error = None
        city.sync_failures = 0
        # Jitter verteilt die Städte über den Tag, statt sie alle zur selben Uhrzeit zu synchronisieren
        city.next_sync_at = run.finished_at + timedelta(
            hours=settings.OSM_SYNC_INTERVAL_HOURS, minutes=random.randint(0, 60)
        )
        await db.commit()
        logger.info("OSM sync complete for '%s': %d created, %d updated, %d deactivated",
                    city.name, created, updated, deactivated)
        return run

    except Exception as e:
        await db.rollback()
        # Rollback lässt die ORM-Objekte ablaufen → neu laden statt async Lazy-Load
        await db.refresh(city)
        await db.refresh(run)
        failures = (city.sync_failures or 0) + 1
        run.status = "failed"
        run.error = str(e)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        city.last_sync_status = "failed"
        city.last_sync_error = run.error
        city.sync_failures = failures
        city.next_sync_at = run.finished_at + min(RETRY_BASE * 2 ** (failures - 1), RETRY_MAX)
        await db.commit()
        logger.warning("OSM sync failed for '%s' (%d. Fehlschlag): %s", city.name, failures, e)
        raise


async def run_sync(city_id: int | None = None) -> bool:
    """Synchronisiert die angegebene oder die am längsten fällige Stadt.

    Hält währenddessen einen Postgres-Advisory-Lock; läuft bereits ein Sync, passiert nichts.
    Gibt True zurück, wenn ein Sync gelaufen ist.
    """
    async with engine.connect() as lock_conn:
        locked = (await lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": SYNC_LOCK_KEY}
        )).scalar()
        await lock_conn.commit()
        if not locked:
            logger.info("OSM sync übersprungen: anderer Sync läuft bereits")
            return False
        try:
            async with AsyncSessionLocal() as db:
                query = select(City).where(City.is_active == True, City.osm_sync_enabled == True)
                if city_id is not None:
                    query = query.where(City.id == city_id)
                else:
                    query = query.where(City.next_sync_at <= datetime.now(timezone.utc)).order_by(City.next_sync_at)
                city = (await db.execute(query.limit(1))).scalar_one_or_none()
                if city is None:
                    return False
                try:
                    await sync_osm_locations(db, city)
                except Exception:
                    pass  # bereits protokolliert, Backoff gesetzt
                return True
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SYNC_LOCK_KEY})
            await lock_conn.commit()
