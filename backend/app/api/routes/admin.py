import json
import logging
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text, delete, insert, update as sa_update
from app.core.database import get_db, AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.city import City
from app.models.osm_sync_run import OsmSyncRun
from app.models.moderator_city import moderator_cities
from app.models.price_entry import PriceEntry
from app.api.deps import get_admin
from app.services.osm_sync import run_sync, OverpassUnavailable
from app.services.geo_import import (
    GeoImportError, search_cities, create_city_from_osm, refresh_boundary,
    fetch_area_candidates, level_stats, choose_level, import_osm_areas, import_uploaded_areas,
)

logger = logging.getLogger(__name__)
MAX_AREA_UPLOAD_BYTES = 50_000_000

router = APIRouter(prefix="/admin", tags=["admin"])


class UpdateRole(BaseModel):
    role: UserRole


class UpdateActive(BaseModel):
    is_active: bool


class UserCities(BaseModel):
    city_ids: list[int]


class CityCreate(BaseModel):
    osm_relation_id: int


class CityUpdate(BaseModel):
    name: str | None = None
    default_zoom: int | None = None
    is_active: bool | None = None
    osm_sync_enabled: bool | None = None


class BoundaryUpdate(BaseModel):
    osm_relation_id: int | None = None


class OsmAreaImport(BaseModel):
    admin_level: int | None = None
    replace_upload: bool = False


@router.get("/users")
async def list_users(
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    query = select(User)
    if search:
        query = query.where(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * limit
    result = await db.execute(
        query.order_by(User.id.asc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()

    city_rows = await db.execute(
        select(moderator_cities.c.user_id, moderator_cities.c.city_id)
        .where(moderator_cities.c.user_id.in_([u.id for u in users]))
    )
    cities_by_user: dict[int, list[int]] = {}
    for r in city_rows:
        cities_by_user.setdefault(r.user_id, []).append(r.city_id)

    items = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "moderated_city_ids": sorted(cities_by_user.get(u.id, [])),
        }
        for u in users
    ]
    return {"total": total, "items": items}


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: UpdateRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = body.role
    await db.commit()
    return {"id": target.id, "role": target.role}


@router.put("/users/{user_id}/cities")
async def set_user_cities(
    user_id: int,
    body: UserCities,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    """Städte, in denen ein Moderator bearbeiten darf (ersetzt die bisherige Zuweisung)."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    city_ids = sorted(set(body.city_ids))
    if city_ids:
        found = (await db.execute(select(func.count()).select_from(City).where(City.id.in_(city_ids)))).scalar_one()
        if found != len(city_ids):
            raise HTTPException(status_code=400, detail="Unbekannte Stadt")
    await db.execute(delete(moderator_cities).where(moderator_cities.c.user_id == user_id))
    if city_ids:
        await db.execute(insert(moderator_cities), [{"user_id": user_id, "city_id": c} for c in city_ids])
    await db.commit()
    return {"id": user_id, "moderated_city_ids": city_ids}


@router.patch("/users/{user_id}/activate")
async def update_user_active(
    user_id: int,
    body: UpdateActive,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot suspend your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.is_active = body.is_active
    await db.commit()
    return {"id": target.id, "is_active": target.is_active}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Anonymize price entries (same pattern as self-delete in auth.py)
    await db.execute(
        sa_update(PriceEntry)
        .where(PriceEntry.user_id == user_id)
        .values(user_id=None)
    )

    await db.delete(target)
    await db.commit()
    return {"deleted": user_id}


# --- City management ---
# Städte werden per Namenssuche angelegt; Grenze, Gebiete und erster OSM-Sync laufen automatisch.

def _city_to_dict(c: City, stats: dict | None = None) -> dict:
    stats = stats or {}
    return {
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "state": c.state,
        "osm_relation_id": c.osm_relation_id,
        "has_boundary": c.boundary is not None,
        "bbox": c.bbox,
        "center_lat": c.center_lat,
        "center_lon": c.center_lon,
        "default_zoom": c.default_zoom,
        "is_active": c.is_active,
        "osm_sync_enabled": c.osm_sync_enabled,
        "area_source": c.area_source,
        "area_admin_level": c.area_admin_level,
        "last_sync_at": c.last_sync_at,
        "last_sync_status": c.last_sync_status,
        "last_sync_error": c.last_sync_error,
        "next_sync_at": c.next_sync_at,
        "sync_failures": c.sync_failures,
        "area_count": stats.get("area_count", 0),
        "location_count": stats.get("location_count", 0),
        "priced_location_count": stats.get("priced_location_count", 0),
    }


async def _get_city(db: AsyncSession, city_id: int) -> City:
    city = (await db.execute(select(City).where(City.id == city_id))).scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    return city


async def _setup_city_background(city_id: int) -> None:
    """Nach dem Anlegen: Gebiete aus OSM importieren, dann ersten OSM-Sync ausführen."""
    async with AsyncSessionLocal() as db:
        city = await _get_city(db, city_id)
        try:
            await import_osm_areas(db, city)
        except Exception as e:
            logger.warning("Area import for '%s' failed: %s", city.name, e)
    await run_sync(city_id)


@router.get("/cities")
async def list_all_cities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    cities = (await db.execute(select(City).order_by(City.name))).scalars().all()
    stats_rows = await db.execute(text("""
        SELECT c.id,
               (SELECT count(*) FROM areas a WHERE a.city_id = c.id) AS area_count,
               (SELECT count(*) FROM locations l WHERE l.city_id = c.id AND l.is_active) AS location_count,
               (SELECT count(DISTINCT pe.location_id) FROM price_entries pe
                  JOIN locations l ON l.id = pe.location_id
                 WHERE l.city_id = c.id AND pe.is_current) AS priced_location_count
        FROM cities c
    """))
    stats = {r.id: r._asdict() for r in stats_rows}
    return [_city_to_dict(c, stats.get(c.id)) for c in cities]


@router.get("/cities/search")
async def search_new_city(
    q: str,
    current_user: User = Depends(get_admin),
):
    try:
        return await search_cities(q)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Nominatim nicht erreichbar: {e}")


@router.post("/cities", status_code=201)
async def create_city(
    body: CityCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    try:
        city = await create_city_from_osm(db, body.osm_relation_id)
    except GeoImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Nominatim nicht erreichbar: {e}")
    background_tasks.add_task(_setup_city_background, city.id)
    return _city_to_dict(city)


@router.patch("/cities/{city_id}")
async def update_city(
    city_id: int,
    body: CityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(city, field, value)
    await db.commit()
    return _city_to_dict(city)


@router.post("/cities/{city_id}/sync")
async def trigger_city_sync(
    city_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    # Läuft bereits ein Sync, verhindert der Advisory-Lock einen Doppellauf; die Stadt bleibt dann fällig
    city.next_sync_at = datetime.now(timezone.utc)
    await db.commit()
    background_tasks.add_task(run_sync, city_id)
    return {"detail": f"OSM-Sync für '{city.name}' gestartet"}


@router.get("/cities/{city_id}/sync-runs")
async def list_sync_runs(
    city_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    runs = (await db.execute(
        select(OsmSyncRun).where(OsmSyncRun.city_id == city_id)
        .order_by(OsmSyncRun.started_at.desc()).limit(min(limit, 50))
    )).scalars().all()
    return [
        {
            "id": r.id, "started_at": r.started_at, "finished_at": r.finished_at, "status": r.status,
            "server": r.server, "elements": r.elements, "created": r.created, "updated": r.updated,
            "deactivated": r.deactivated, "error": r.error,
        }
        for r in runs
    ]


@router.post("/cities/{city_id}/boundary")
async def update_city_boundary(
    city_id: int,
    body: BoundaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    try:
        await refresh_boundary(db, city, body.osm_relation_id)
    except GeoImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Nominatim nicht erreichbar: {e}")
    return _city_to_dict(city)


@router.get("/cities/{city_id}/area-levels")
async def preview_area_levels(
    city_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    try:
        by_level = await fetch_area_candidates(city)
    except GeoImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OverpassUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Overpass nicht verfügbar: {e}")
    stats = level_stats(city, by_level)
    return {"levels": stats, "recommended": choose_level(stats)}


@router.post("/cities/{city_id}/areas/osm")
async def import_city_areas_from_osm(
    city_id: int,
    body: OsmAreaImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    try:
        return await import_osm_areas(db, city, body.admin_level, force=body.replace_upload)
    except GeoImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OverpassUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Overpass nicht verfügbar: {e}")


@router.post("/cities/{city_id}/areas/upload")
async def upload_city_areas(
    city_id: int,
    file: UploadFile = File(...),
    key_prop: str = Form(...),
    name_prop: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    city = await _get_city(db, city_id)
    raw = await file.read(MAX_AREA_UPLOAD_BYTES + 1)
    if len(raw) > MAX_AREA_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Datei zu groß (max. 50 MB)")
    try:
        geojson = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Keine gültige JSON-Datei")
    try:
        count = await import_uploaded_areas(db, city, geojson, key_prop, name_prop)
    except GeoImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": count}
