"""
Stadt anlegen und Gebiete importieren – ersetzt den früheren manuellen Setup-Wizard.

- Stadtsuche/Grenze über Nominatim (OSM-Grenzrelation, Polygon, Bbox, Zentrum)
- Stadtteile automatisch aus OSM (boundary=administrative, admin_level 9/10) mit automatischer Ebenenwahl
- alternativ GeoJSON-Upload offizieller Gebiete (z. B. Berliner LOR); Upload hat Vorrang vor OSM
"""
import logging
import math
import re
import unicodedata
from datetime import datetime, timezone

import httpx
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep
from shapely.validation import make_valid
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.area import Area
from app.models.city import City
from app.services.osm_sync import OVERPASS_AREA_OFFSET, OVERPASS_HEADERS, overpass
from app.services.spatial import assign_areas

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
AREA_LEVELS = (9, 10)
MIN_AREAS, MAX_AREAS = 5, 250
GOOD_COVERAGE = 0.9
REST_AREA_MIN_SHARE = 0.02  # unabgedeckter Rest ab 2 % der Stadtfläche wird eigenes Gebiet


class GeoImportError(Exception):
    pass


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _to_multipolygon(geom) -> MultiPolygon | None:
    """Beliebige (evtl. ungültige) Geometrie → gültiges MultiPolygon (nur Flächenanteile)."""
    geom = make_valid(geom)
    polys: list[Polygon] = []
    for g in getattr(geom, "geoms", [geom]):
        if isinstance(g, Polygon):
            polys.append(g)
        elif isinstance(g, MultiPolygon):
            polys.extend(g.geoms)
        elif hasattr(g, "geoms"):  # GeometryCollection mit verschachtelten Flächen
            polys.extend(p for p in g.geoms if isinstance(p, Polygon))
    polys = [p for p in polys if not p.is_empty and p.area > 0]
    return MultiPolygon(polys) if polys else None


def slugify(name: str) -> str:
    name = name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")[:50] or "stadt"


def _default_zoom(boundary: MultiPolygon) -> int:
    """Start-Zoom so, dass die Kernstadt auf einen Bildschirm passt.

    Maßgeblich ist die größte Teilfläche: Exklaven wie Hamburgs Insel Neuwerk würden sonst weit herauszoomen.
    """
    main = max(boundary.geoms, key=lambda g: g.area)
    min_lon, min_lat, max_lon, max_lat = main.bounds
    # Breite in "Längengrad-Äquivalent" (Breitengrade sind in Mercator ~1/cos(lat) gestreckt)
    extent = max(max_lon - min_lon, (max_lat - min_lat) / math.cos(math.radians((min_lat + max_lat) / 2)))
    # 256-px-Kacheln, Ziel ca. 1200 px Breite: 360° / 2^z * (1200/256) >= extent
    zoom = math.floor(math.log2(360 * (1200 / 256) / max(extent, 1e-6)))
    return max(9, min(13, zoom))


async def _nominatim(path: str, params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, headers=OVERPASS_HEADERS) as client:
        response = await client.get(f"{NOMINATIM_URL}/{path}", params={**params, "format": "jsonv2"})
        response.raise_for_status()
        return response.json()


# ── Stadt suchen / anlegen / Grenze aktualisieren ───────────────────────────

async def search_cities(query: str) -> list[dict]:
    """Kandidaten für eine neue Stadt (nur OSM-Relationen in Deutschland)."""
    results = await _nominatim("search", {
        "q": query, "countrycodes": "de", "featuretype": "settlement",
        "addressdetails": 1, "limit": 10,
    })
    seen, out = set(), []
    for r in results:
        if r.get("osm_type") != "relation" or r["osm_id"] in seen:
            continue
        seen.add(r["osm_id"])
        address = r.get("address", {})
        out.append({
            "osm_relation_id": r["osm_id"],
            "name": r.get("name") or r.get("display_name", "").split(",")[0],
            "state": address.get("state") or r.get("name"),
            "type": r.get("addresstype") or r.get("type"),
            "display_name": r.get("display_name"),
        })
    return out


async def _lookup_boundary(relation_id: int) -> dict:
    results = await _nominatim("lookup", {
        "osm_ids": f"R{relation_id}", "polygon_geojson": 1, "addressdetails": 1,
    })
    if not results:
        raise GeoImportError(f"OSM-Relation {relation_id} nicht gefunden")
    r = results[0]
    boundary = _to_multipolygon(shape(r["geojson"])) if r.get("geojson") else None
    if boundary is None:
        raise GeoImportError("Für diese Relation liefert OSM keine Fläche")
    min_lat, max_lat, min_lon, max_lon = (float(v) for v in r["boundingbox"])
    name = r.get("name") or r.get("display_name", "").split(",")[0]
    return {
        "name": name,
        # Stadtstaaten (Berlin, Hamburg, Bremen) haben kein eigenes "state"-Feld
        "state": r.get("address", {}).get("state") or name,
        "boundary": boundary,
        "bbox": f"{min_lat},{min_lon},{max_lat},{max_lon}",
        "center_lat": float(r["lat"]),
        "center_lon": float(r["lon"]),
        "default_zoom": _default_zoom(boundary),
    }


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while (await db.execute(select(City.id).where(City.slug == slug))).first():
        slug, n = f"{base[:46]}-{n}", n + 1
    return slug


async def create_city_from_osm(db: AsyncSession, relation_id: int) -> City:
    existing = (await db.execute(select(City).where(City.osm_relation_id == relation_id))).scalar_one_or_none()
    if existing:
        raise GeoImportError(f"'{existing.name}' ist bereits angelegt")
    info = await _lookup_boundary(relation_id)
    city = City(
        name=info["name"],
        slug=await _unique_slug(db, info["name"]),
        state=info["state"],
        osm_relation_id=relation_id,
        boundary=from_shape(info["boundary"], srid=4326),
        bbox=info["bbox"],
        center_lat=info["center_lat"],
        center_lon=info["center_lon"],
        default_zoom=info["default_zoom"],
        is_active=True,
        osm_sync_enabled=True,
        area_source="none",
        next_sync_at=datetime.now(timezone.utc),
    )
    db.add(city)
    await db.commit()
    await db.refresh(city)
    return city


async def refresh_boundary(db: AsyncSession, city: City, relation_id: int | None = None) -> City:
    """Grenze, Bbox und Zentrum aus OSM (neu) laden, z. B. für Städte aus der Zeit vor der Grenzrelation."""
    relation_id = relation_id or city.osm_relation_id
    if not relation_id:
        raise GeoImportError("Keine OSM-Relation hinterlegt")
    info = await _lookup_boundary(relation_id)
    city.osm_relation_id = relation_id
    city.boundary = from_shape(info["boundary"], srid=4326)
    city.bbox = info["bbox"]
    city.center_lat, city.center_lon = info["center_lat"], info["center_lon"]
    city.state = city.state or info["state"]
    await db.commit()
    return city


# ── Gebiete aus OSM ──────────────────────────────────────────────────────────

def _relation_geometry(rel: dict):
    outer, inner = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        line = LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        (inner if m.get("role") == "inner" else outer).append(line)
    outer_poly = unary_union(list(polygonize(outer)))
    if outer_poly.is_empty:
        return None
    if inner:
        outer_poly = outer_poly.difference(unary_union(list(polygonize(inner))))
    return _to_multipolygon(outer_poly)


async def fetch_area_candidates(city: City) -> dict[int, list[dict]]:
    """Alle Verwaltungsgebiete der Ebenen 9/10 innerhalb der Stadt, gruppiert nach Ebene."""
    if not city.osm_relation_id or city.boundary is None:
        raise GeoImportError("Stadt hat noch keine Grenze – zuerst 'Grenze aktualisieren'")
    levels = "|".join(str(level) for level in AREA_LEVELS)
    data, _ = await overpass(f"""
[out:json][timeout:180];
area(id:{OVERPASS_AREA_OFFSET + city.osm_relation_id})->.a;
rel(area.a)["boundary"="administrative"]["admin_level"~"^({levels})$"];
out geom;
""", expect_results=True)
    boundary = to_shape(city.boundary)
    inside = prep(boundary.buffer(0.001))
    by_level: dict[int, list[dict]] = {}
    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        geom = _relation_geometry(rel)
        # rel(area) liefert auch Nachbargebiete, die die Stadt nur berühren
        if geom is None or not inside.contains(geom.representative_point()):
            continue
        geom = _to_multipolygon(geom.intersection(boundary))
        if geom is None:
            continue
        level = int(tags["admin_level"])
        by_level.setdefault(level, []).append({
            "key": f"r{rel['id']}",
            "name": tags.get("name") or f"Gebiet {rel['id']}",
            "geom": geom,
        })
    return by_level


async def city_points(db: AsyncSession, city: City) -> list[Point]:
    """Aktive Lokale der Stadt als Punkte – Maßstab dafür, ob Gebiete die relevanten Teile abdecken."""
    rows = await db.execute(
        text("SELECT ST_X(geom) AS lon, ST_Y(geom) AS lat FROM locations WHERE city_id = :c AND is_active"),
        {"c": city.id},
    )
    return [Point(r.lon, r.lat) for r in rows]


def _share_covered(geoms: list, points: list[Point]) -> float:
    covered = prep(unary_union(geoms))
    return sum(1 for p in points if covered.covers(p)) / len(points)


def level_stats(city: City, by_level: dict[int, list[dict]], points: list[Point] | None = None) -> list[dict]:
    """Je Ebene: Anzahl, Flächenabdeckung und – falls Lokale bekannt – Anteil der Lokale in den Gebieten.

    Die Fläche allein täuscht: Hamburgs Stadtgebiet enthält z. B. viel Wattenmeer, das keinem Stadtteil gehört.
    """
    city_area = to_shape(city.boundary).area or 1
    stats = []
    for level, items in sorted(by_level.items()):
        geoms = [i["geom"] for i in items]
        stat = {
            "admin_level": level,
            "count": len(items),
            "coverage": round(min(1.0, sum(g.area for g in geoms) / city_area), 3),
        }
        if points:
            stat["location_coverage"] = round(_share_covered(geoms, points), 3)
        stats.append(stat)
    return stats


def _coverage_metric(stat: dict) -> float:
    return stat.get("location_coverage", stat["coverage"])


def choose_level(stats: list[dict]) -> int | None:
    """Feinste Ebene, die die Lokale (bzw. ohne Lokale: die Fläche) gut abdeckt; sonst die beste Abdeckung."""
    usable = [s for s in stats if MIN_AREAS <= s["count"] <= MAX_AREAS]
    if not usable:
        return None
    good = [s for s in usable if _coverage_metric(s) >= GOOD_COVERAGE]
    if good:
        return max(good, key=lambda s: s["count"])["admin_level"]
    return max(usable, key=_coverage_metric)["admin_level"]


async def _replace_areas(db: AsyncSession, city: City, items: list[dict], source: str, level: int | None) -> int:
    await db.execute(delete(Area).where(Area.city_id == city.id))
    for item in items:
        db.add(Area(
            city_id=city.id, key=item["key"][:100], name=item["name"][:255],
            admin_level=level, source=source, geom=from_shape(item["geom"], srid=4326),
        ))
    city.area_source = source if items else "none"
    city.area_admin_level = level
    await db.flush()
    await assign_areas(db, city.id)
    await db.commit()
    return len(items)


async def import_osm_areas(db: AsyncSession, city: City, admin_level: int | None = None, force: bool = False) -> dict:
    """Importiert Stadtteile aus OSM. Hochgeladene Gebiete werden nur mit force=True ersetzt."""
    if city.area_source == "upload" and not force:
        return {"skipped": True, "reason": "Stadt nutzt hochgeladene Gebiete"}
    by_level = await fetch_area_candidates(city)
    points = await city_points(db, city)
    stats = level_stats(city, by_level, points)
    level = admin_level or choose_level(stats)
    if level is None or level not in by_level:
        return {"skipped": True, "reason": "Keine passende Gebietsebene in OSM gefunden", "levels": stats}
    items = list(by_level[level])
    # Viele Städte sind in OSM nur teilweise unterteilt (z. B. Potsdam: nur eingemeindete Ortsteile).
    # Den Rest als eigenes Gebiet ergänzen, damit jedes Lokal einem Gebiet zugeordnet ist –
    # aber nur, wenn dort auch Lokale liegen (Hamburgs Wattenmeer braucht kein leeres Restgebiet).
    boundary = to_shape(city.boundary)
    rest = _to_multipolygon(boundary.difference(unary_union([i["geom"] for i in items])))
    if rest is not None and rest.area / boundary.area > REST_AREA_MIN_SHARE:
        prepared_rest = prep(rest)
        if not points or any(prepared_rest.covers(p) for p in points):
            items.append({"key": "rest", "name": f"{city.name} (übriges Stadtgebiet)", "geom": rest})
    count = await _replace_areas(db, city, items, "osm", level)
    logger.info("Imported %d OSM areas (admin_level %d) for '%s'", count, level, city.name)
    return {"skipped": False, "admin_level": level, "count": count, "levels": stats}


# ── Gebiete per Upload ───────────────────────────────────────────────────────

async def import_uploaded_areas(db: AsyncSession, city: City, geojson: dict, key_prop: str, name_prop: str) -> int:
    if geojson.get("type") != "FeatureCollection" or not geojson.get("features"):
        raise GeoImportError("Erwartet wird eine GeoJSON-FeatureCollection")
    items, keys = [], set()
    for i, feature in enumerate(geojson["features"]):
        props = feature.get("properties") or {}
        key = str(props.get(key_prop) or "").strip()
        if not key:
            raise GeoImportError(f"Feature {i + 1}: Eigenschaft '{key_prop}' fehlt")
        if key in keys:
            raise GeoImportError(f"Schlüssel '{key}' kommt mehrfach vor")
        keys.add(key)
        try:
            geom = _to_multipolygon(shape(feature["geometry"]))
        except Exception as e:
            raise GeoImportError(f"Feature {i + 1}: ungültige Geometrie ({e})")
        if geom is None:
            raise GeoImportError(f"Feature {i + 1}: keine Fläche")
        minx, miny, maxx, maxy = geom.bounds
        if not (-180 <= minx <= 180 and -90 <= miny <= 90 and -180 <= maxx <= 180 and -90 <= maxy <= 90):
            raise GeoImportError("Koordinaten sind nicht in WGS84 (EPSG:4326) – bitte vorher umprojizieren")
        items.append({"key": key, "name": str(props.get(name_prop) or key), "geom": geom})
    return await _replace_areas(db, city, items, "upload", None)
