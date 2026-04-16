from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, update as sa_update
from app.core.database import get_db, AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.city import City
from app.models.price_entry import PriceEntry
from app.api.deps import get_admin
from app.services.osm_sync import sync_osm_locations

router = APIRouter(prefix="/admin", tags=["admin"])


class UpdateRole(BaseModel):
    role: UserRole


class UpdateActive(BaseModel):
    is_active: bool


class CityCreate(BaseModel):
    name: str
    slug: str
    bbox: str
    center_lat: float
    center_lon: float
    default_zoom: int = 12
    osm_sync_enabled: bool = True
    wms_layer: str | None = None


class CityUpdate(BaseModel):
    name: str | None = None
    bbox: str | None = None
    center_lat: float | None = None
    center_lon: float | None = None
    default_zoom: int | None = None
    is_active: bool | None = None
    osm_sync_enabled: bool | None = None
    wms_layer: str | None = None


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

    items = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
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

@router.get("/cities")
async def list_all_cities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    result = await db.execute(select(City).order_by(City.id))
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "bbox": c.bbox,
            "center_lat": c.center_lat,
            "center_lon": c.center_lon,
            "default_zoom": c.default_zoom,
            "is_active": c.is_active,
            "osm_sync_enabled": c.osm_sync_enabled,
            "wms_layer": c.wms_layer,
        }
        for c in result.scalars().all()
    ]


@router.post("/cities", status_code=201)
async def create_city(
    body: CityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    existing = await db.execute(select(City).where(City.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")

    city = City(**body.model_dump())
    db.add(city)
    await db.commit()
    await db.refresh(city)
    return {"id": city.id, "name": city.name, "slug": city.slug}


@router.patch("/cities/{city_id}")
async def update_city(
    city_id: int,
    body: CityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(city, field, value)
    await db.commit()
    return {"id": city.id, "name": city.name}


@router.post("/cities/{city_id}/sync")
async def trigger_city_sync(
    city_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin),
):
    result = await db.execute(select(City).where(City.id == city_id))
    city = result.scalar_one_or_none()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    async def _run_sync(cid: int):
        async with AsyncSessionLocal() as session:
            r = await session.execute(select(City).where(City.id == cid))
            c = r.scalar_one_or_none()
            if c:
                await sync_osm_locations(session, c)

    background_tasks.add_task(_run_sync, city_id)
    return {"detail": f"OSM sync started for '{city.name}'"}
