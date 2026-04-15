from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone, timedelta
from app.core.database import get_db
from app.models.price_entry import PriceEntry
from app.models.moderation_log import ModerationLog
from app.models.location import Location
from app.models.drink import Drink
from app.models.user import User
from app.api.deps import get_moderator

router = APIRouter(prefix="/moderation", tags=["moderation"])


# ── existing endpoints ────────────────────────────────────────────────────────

@router.get("/logs")
async def get_moderation_logs(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    result = await db.execute(
        select(ModerationLog)
        .order_by(ModerationLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/flag/{entry_id}")
async def flag_entry(
    entry_id: int,
    note: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_moderator),
):
    result = await db.execute(select(PriceEntry).where(PriceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    log = ModerationLog(
        price_entry_id=entry_id,
        moderator_id=current_user.id,
        action="flagged",
        note=note,
    )
    db.add(log)
    await db.commit()
    return {"status": "flagged"}


@router.delete("/entry/{entry_id}")
async def delete_entry(
    entry_id: int,
    note: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_moderator),
):
    result = await db.execute(select(PriceEntry).where(PriceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry.is_current = False
    log = ModerationLog(
        price_entry_id=entry_id,
        moderator_id=current_user.id,
        action="deleted",
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    await db.commit()
    return {"status": "removed"}


# ── new endpoints ─────────────────────────────────────────────────────────────

@router.get("/entries")
async def list_entries(
    drink_id: int | None = None,
    location_name: str | None = None,
    username: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    conditions = []
    if drink_id is not None:
        conditions.append(PriceEntry.drink_id == drink_id)
    if location_name:
        conditions.append(Location.name.ilike(f"%{location_name}%"))
    if username:
        conditions.append(User.username.ilike(f"%{username}%"))
    if date_from:
        conditions.append(PriceEntry.reported_at >= date_from)
    if date_to:
        conditions.append(PriceEntry.reported_at <= date_to)

    base_query = (
        select(PriceEntry, Location.name.label("location_name"), Drink.name.label("drink_name"), User.username.label("username"))
        .join(Location, PriceEntry.location_id == Location.id)
        .join(Drink, PriceEntry.drink_id == Drink.id)
        .outerjoin(User, PriceEntry.user_id == User.id)
    )
    if conditions:
        base_query = base_query.where(and_(*conditions))

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * limit
    rows = await db.execute(
        base_query.order_by(PriceEntry.reported_at.desc()).offset(offset).limit(limit)
    )

    items = []
    for row in rows:
        entry, location_name_val, drink_name_val, username_val = row
        items.append({
            "id": entry.id,
            "location_name": location_name_val,
            "drink_name": drink_name_val,
            "username": username_val,
            "price": entry.price,
            "reported_at": entry.reported_at,
            "is_current": entry.is_current,
            "note": entry.note,
        })

    return {"total": total, "items": items}


class BulkDeleteRequest(BaseModel):
    entry_ids: list[int]


@router.post("/entries/bulk-delete")
async def bulk_delete_entries(
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_moderator),
):
    if not body.entry_ids:
        return {"deleted": 0}

    result = await db.execute(
        select(PriceEntry).where(PriceEntry.id.in_(body.entry_ids))
    )
    entries = result.scalars().all()

    now = datetime.now(timezone.utc)
    for entry in entries:
        entry.is_current = False
        db.add(ModerationLog(
            price_entry_id=entry.id,
            moderator_id=current_user.id,
            action="deleted",
            created_at=now,
        ))

    await db.commit()
    return {"deleted": len(entries)}


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    # Total entries
    total_entries_result = await db.execute(select(func.count(PriceEntry.id)))
    total_entries = total_entries_result.scalar_one()

    # Entries by drink
    by_drink_result = await db.execute(
        select(Drink.name, Drink.color_hex, func.count(PriceEntry.id).label("count"))
        .join(PriceEntry, Drink.id == PriceEntry.drink_id)
        .group_by(Drink.name, Drink.color_hex)
        .order_by(func.count(PriceEntry.id).desc())
    )
    entries_by_drink = [{"drink_name": row[0], "color_hex": row[1], "count": row[2]} for row in by_drink_result]

    # Entries last 30 days (daily buckets)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    daily_result = await db.execute(
        select(
            func.date_trunc("day", PriceEntry.reported_at).label("day"),
            func.count(PriceEntry.id).label("count"),
        )
        .where(PriceEntry.reported_at >= cutoff)
        .group_by(func.date_trunc("day", PriceEntry.reported_at))
        .order_by(func.date_trunc("day", PriceEntry.reported_at))
    )
    entries_last_30_days = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in daily_result
    ]

    # Total users
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar_one()

    # Locations with at least one price entry
    locations_with_price_result = await db.execute(
        select(func.count(func.distinct(PriceEntry.location_id)))
    )
    total_locations_with_price = locations_with_price_result.scalar_one()

    return {
        "total_entries": total_entries,
        "entries_by_drink": entries_by_drink,
        "entries_last_30_days": entries_last_30_days,
        "total_users": total_users,
        "total_locations_with_price": total_locations_with_price,
    }
