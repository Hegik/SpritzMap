"""
Syncs bar/restaurant/beer garden locations from OpenStreetMap via Overpass API.

Für viele Städte ausgelegt:
- Abfrage über die Stadtfläche (OSM-Grenzrelation) statt Bbox → keine Überlappung zwischen Nachbarstädten;
  bei Timeout Fallback auf Kacheln je Teilfläche der Grenze, gefiltert nach der Stadtgrenze
- Bulk-Upsert statt einer Abfrage pro Element
- Warteschlange, Lock und Zeitbudget: siehe services/city_jobs.py
- Lokale werden erst deaktiviert, wenn sie 7 Tage lang in erfolgreichen Läufen fehlen
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.prepared import prep
from sqlalchemy import text, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
TILE_MAX_DEGREES = 0.2  # größere Teilflächen werden für den Fallback in 2×2 Kacheln geteilt
TILE_PAUSE = 3  # Sekunden zwischen Kachel-Abfragen


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


async def overpass(query: str, timeout: float = 200, expect_results: bool = False) -> tuple[dict, str]:
    """Führt eine Overpass-Abfrage aus, mit Mirror-Fallback. Gibt (JSON, Server-URL) zurück.

    expect_results=True: eine leere Antwort gilt als Fehlschlag (überlastete Server liefern teils still
    ein leeres Ergebnis) – sonst würde ein Sync "erfolgreich" 0 Lokale melden.
    """
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, headers=OVERPASS_HEADERS) as client:
        for url in OVERPASS_URLS:
            try:
                response = await client.post(url, data={"data": query})
                response.raise_for_status()
                data = response.json()
                # Overpass meldet serverseitige Fehler (Timeout, Speicher, Rate-Limit) teils mit 200 + "remark"
                remark = data.get("remark") or ""
                if "error" in remark.lower() or "timed out" in remark or "out of memory" in remark:
                    raise OverpassUnavailable(remark)
                if expect_results and not data.get("elements"):
                    raise OverpassUnavailable("leere Antwort")
                return data, url
            except httpx.HTTPStatusError as e:
                # 4xx außer 429 = Fehler in unserer Anfrage → Mirror würde gleich antworten
                if e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                last_error = e
            except (httpx.TransportError, OverpassUnavailable, ValueError) as e:
                last_error = e
            logger.warning("Overpass %s nicht verfügbar (%s), versuche nächsten Server", url, _describe(last_error))
    raise OverpassUnavailable(_describe(last_error))


def _describe(e: Exception | None) -> str:
    # httpx-Timeouts haben keinen Text → Typ mit ausgeben
    return f"{type(e).__name__}: {e}" if e and str(e) else type(e).__name__ if e else "unbekannt"


def _split_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[str]:
    if max(max_lat - min_lat, max_lon - min_lon) <= TILE_MAX_DEGREES:
        return [f"{min_lat},{min_lon},{max_lat},{max_lon}"]
    mid_lat, mid_lon = (min_lat + max_lat) / 2, (min_lon + max_lon) / 2
    return [
        f"{a},{b},{c},{d}"
        for a, c in ((min_lat, mid_lat), (mid_lat, max_lat))
        for b, d in ((min_lon, mid_lon), (mid_lon, max_lon))
    ]


def _fallback_tiles(city: City) -> list[str]:
    """Kacheln für den Fallback: je Teilfläche der Stadtgrenze statt der Gesamt-Bbox
    (z. B. Hamburg mit der Insel Neuwerk – die Gesamt-Bbox reicht bis in die Nordsee)."""
    if city.boundary is None:
        return [city.bbox]
    boundary = to_shape(city.boundary)
    parts = sorted(getattr(boundary, "geoms", [boundary]), key=lambda g: g.area, reverse=True)
    tiles: list[str] = []
    for part in parts:
        if part.area < boundary.area * 0.001:
            continue  # winzige Splitterflächen
        min_lon, min_lat, max_lon, max_lat = part.bounds
        tiles.extend(_split_bbox(min_lat, min_lon, max_lat, max_lon))
    return tiles


async def fetch_city_elements(city: City) -> tuple[list[dict], str]:
    """Holt alle relevanten OSM-Elemente einer Stadt. Gibt (Elemente, Server) zurück."""
    if city.osm_relation_id:
        try:
            data, server = await overpass(_area_query(city.osm_relation_id), expect_results=True)
            return data.get("elements", []), server
        except OverpassUnavailable as e:
            logger.warning("Flächenabfrage für '%s' fehlgeschlagen (%s) → Kachel-Fallback", city.name, e)

    tiles = _fallback_tiles(city)
    seen: dict[tuple[str, int], dict] = {}
    server = ""
    for i, tile in enumerate(tiles):
        if i:
            await asyncio.sleep(TILE_PAUSE)
        data, server = await overpass(_bbox_query(tile))
        for el in data.get("elements", []):
            seen[(el["type"], el["id"])] = el
    if not seen:
        raise OverpassUnavailable("keine Lokale gefunden (leere Antworten)")
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
