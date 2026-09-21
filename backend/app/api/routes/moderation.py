import calendar
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct, text
from datetime import datetime, timezone, timedelta
from app.core.database import get_db
from app.models.price_entry import PriceEntry
from app.models.moderation_log import ModerationLog
from app.models.location import Location
from app.models.drink import Drink
from app.models.user_deletion_log import UserDeletionLog
from app.models.user import User
from app.models.photo import Photo
from app.api.routes.photos import photo_to_dict
from app.api.deps import get_moderator

router = APIRouter(prefix="/moderation", tags=["moderation"])

LOCATION_TYPE_LABELS = {
    "bar": "Bar",
    "beer_garden": "Biergarten",
    "restaurant": "Restaurant",
    "cafe": "Café",
    "other": "Sonstiges",
}
LOCATION_TYPE_COLORS = {
    "bar": "#5C6BC0",
    "beer_garden": "#66BB6A",
    "restaurant": "#FFA726",
    "cafe": "#AB47BC",
    "other": "#78909C",
}


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

@router.get("/filter-options")
async def get_filter_options(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    locations_result = await db.execute(
        select(Location.name).distinct().order_by(Location.name)
    )
    usernames_result = await db.execute(
        select(User.username).where(User.username.isnot(None)).distinct().order_by(User.username)
    )
    return {
        "locations": [r[0] for r in locations_result],
        "usernames": [r[0] for r in usernames_result],
    }


@router.get("/entries")
async def list_entries(
    drink_id: int | None = None,
    location_name: str | None = None,
    username: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    city_id: int | None = None,
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
    if city_id is not None:
        conditions.append(Location.city_id == city_id)

    joins = (
        lambda q: q
        .join(Location, PriceEntry.location_id == Location.id)
        .join(Drink, PriceEntry.drink_id == Drink.id)
        .outerjoin(User, PriceEntry.user_id == User.id)
    )

    count_q = joins(select(func.count(PriceEntry.id)))
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    base_query = joins(
        select(PriceEntry, Location.name.label("location_name"), Drink.name.label("drink_name"), Drink.color_hex.label("color_hex"), User.username.label("username"))
    )
    if conditions:
        base_query = base_query.where(and_(*conditions))

    offset = (page - 1) * limit
    rows = await db.execute(
        base_query.order_by(PriceEntry.reported_at.desc()).offset(offset).limit(limit)
    )

    rows = rows.all()
    entry_ids = [row[0].id for row in rows]
    photos_by_entry: dict[int, list[dict]] = {}
    if entry_ids:
        photo_rows = await db.execute(select(Photo).where(Photo.price_entry_id.in_(entry_ids)))
        for p in photo_rows.scalars().all():
            photos_by_entry.setdefault(p.price_entry_id, []).append(photo_to_dict(p))

    items = []
    for row in rows:
        entry, location_name_val, drink_name_val, color_hex_val, username_val = row
        items.append({
            "id": entry.id,
            "location_name": location_name_val,
            "drink_name": drink_name_val,
            "color_hex": color_hex_val,
            "username": username_val,
            "price": entry.price,
            "reported_at": entry.reported_at,
            "is_current": entry.is_current,
            "note": entry.note,
            "glass_type": entry.glass_type.value if entry.glass_type else None,
            "ai_glass_type": entry.ai_glass_type.value if entry.ai_glass_type else None,
            "photos": photos_by_entry.get(entry.id, []),
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
        text("""
            SELECT date_trunc('day', reported_at) AS day, COUNT(id) AS count
            FROM price_entries
            WHERE reported_at >= :cutoff
            GROUP BY 1
            ORDER BY 1
        """),
        {"cutoff": cutoff},
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
        select(func.count(distinct(PriceEntry.location_id)))
    )
    total_locations_with_price = locations_with_price_result.scalar_one()

    return {
        "total_entries": total_entries,
        "entries_by_drink": entries_by_drink,
        "entries_last_30_days": entries_last_30_days,
        "total_users": total_users,
        "total_locations_with_price": total_locations_with_price,
    }


# ── helper ────────────────────────────────────────────────────────────────────

def _time_window(granularity: str, year: int | None, month: int | None) -> tuple[datetime, datetime]:
    utc = timezone.utc
    if granularity == "all":
        return datetime(2000, 1, 1, tzinfo=utc), datetime(2100, 12, 31, 23, 59, 59, tzinfo=utc)
    if year is None:
        year = datetime.now(utc).year
    if granularity == "year":
        return datetime(year, 1, 1, tzinfo=utc), datetime(year, 12, 31, 23, 59, 59, tzinfo=utc)
    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, 1, tzinfo=utc), datetime(year, month, last_day, 23, 59, 59, tzinfo=utc)


# ── new stats endpoints ───────────────────────────────────────────────────────

@router.get("/graph-users")
async def stats_users(
    granularity: str = "month",
    year: int | None = None,
    month: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if granularity == "month" and not month:
        month = 1
    start, end = _time_window(granularity, year, month)

    reg_result = await db.execute(
        text("""
            SELECT date_trunc('day', created_at) AS day, COUNT(id) AS count
            FROM users
            WHERE created_at BETWEEN :start AND :end
            GROUP BY 1
            ORDER BY 1
        """),
        {"start": start, "end": end},
    )
    registrations = [{"date": row[0].strftime("%Y-%m-%d"), "count": row[1]} for row in reg_result]

    del_result = await db.execute(
        text("""
            SELECT date_trunc('day', deleted_at) AS day, COUNT(id) AS count
            FROM user_deletion_logs
            WHERE deleted_at BETWEEN :start AND :end
            GROUP BY 1
            ORDER BY 1
        """),
        {"start": start, "end": end},
    )
    deletions = [{"date": row[0].strftime("%Y-%m-%d"), "count": row[1]} for row in del_result]

    base_result = await db.execute(
        select(func.count(User.id)).where(User.created_at < start)
    )
    base_count = base_result.scalar_one()

    return {"registrations": registrations, "deletions": deletions, "base_count": base_count}


@router.get("/graph-entries")
async def stats_entries(
    granularity: str = "month",
    year: int | None = None,
    month: int | None = None,
    group_by: str = "drink",
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if granularity == "month" and not month:
        month = 1
    start, end = _time_window(granularity, year, month)

    city_filter_loc = "AND loc.city_id = :city_id" if city_id else ""
    city_filter_sub = "AND location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    base_params: dict = {"start": start, "end": end}
    if city_id:
        base_params["city_id"] = city_id

    if group_by == "location_type":
        groups_result = await db.execute(
            text(f"""
                SELECT DISTINCT loc.location_type::text
                FROM price_entries pe
                JOIN locations loc ON pe.location_id = loc.id
                WHERE pe.reported_at BETWEEN :start AND :end
                {city_filter_loc}
                ORDER BY 1
            """),
            base_params,
        )
        groups = [
            {
                "id": row[0],
                "name": LOCATION_TYPE_LABELS.get(row[0], row[0]),
                "color_hex": LOCATION_TYPE_COLORS.get(row[0], "#999"),
            }
            for row in groups_result
        ]
        rows_result = await db.execute(
            text(f"""
                SELECT date_trunc('day', pe.reported_at) AS day,
                       loc.location_type::text,
                       COUNT(pe.id) AS count
                FROM price_entries pe
                JOIN locations loc ON pe.location_id = loc.id
                WHERE pe.reported_at BETWEEN :start AND :end
                {city_filter_loc}
                GROUP BY 1, 2
                ORDER BY 1
            """),
            base_params,
        )
    else:
        drinks_result = await db.execute(
            select(Drink.id, Drink.name, Drink.color_hex).order_by(Drink.name)
        )
        groups = [{"id": str(row[0]), "name": row[1], "color_hex": row[2]} for row in drinks_result]
        rows_result = await db.execute(
            text(f"""
                SELECT date_trunc('day', reported_at) AS day, drink_id::text, COUNT(id) AS count
                FROM price_entries
                WHERE reported_at BETWEEN :start AND :end
                {city_filter_sub}
                GROUP BY 1, 2
                ORDER BY 1
            """),
            base_params,
        )

    day_map: dict[str, dict[str, int]] = {}
    for row in rows_result:
        day_str = row[0].strftime("%Y-%m-%d")
        if day_str not in day_map:
            day_map[day_str] = {}
        day_map[day_str][str(row[1])] = int(row[2])

    days = [{"date": d, "counts": day_map[d]} for d in sorted(day_map)]
    return {"groups": groups, "days": days}


@router.get("/lors")
async def stats_lors(
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if city_id is not None:
        result = await db.execute(
            text("SELECT DISTINCT lor_schluessel, pr_name FROM public.lor WHERE city_id = :city_id ORDER BY pr_name"),
            {"city_id": city_id},
        )
    else:
        result = await db.execute(
            text("SELECT DISTINCT lor_schluessel, pr_name FROM public.lor ORDER BY pr_name")
        )
    return [{"lor_schluessel": row[0], "pr_name": row[1]} for row in result]


@router.get("/graph-prices")
async def stats_prices(
    granularity: str = "month",
    year: int | None = None,
    month: int | None = None,
    lor_schluessel: str | None = None,
    drink_id: int | None = None,
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if granularity == "month" and not month:
        month = 1
    start, end = _time_window(granularity, year, month)

    drink_filter = "AND drink_id = :drink_id" if drink_id is not None else ""
    city_filter = "AND location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    city_filter_loc = "AND loc.city_id = :city_id" if city_id else ""
    params: dict = {"start": start, "end": end}
    if drink_id is not None:
        params["drink_id"] = drink_id
    if city_id is not None:
        params["city_id"] = city_id

    berlin_result = await db.execute(
        text(f"""
            SELECT date_trunc('day', reported_at) AS day,
                   AVG(price) AS avg_price,
                   MIN(price) AS min_price,
                   MAX(price) AS max_price
            FROM price_entries
            WHERE reported_at BETWEEN :start AND :end
              AND price > 0
              {drink_filter}
              {city_filter}
            GROUP BY 1
            ORDER BY 1
        """),
        params,
    )
    berlin = [
        {
            "date": row[0].strftime("%Y-%m-%d"),
            "avg_price": float(row[1]),
            "min_price": float(row[2]),
            "max_price": float(row[3]),
        }
        for row in berlin_result
    ]

    lor_data = []
    if lor_schluessel:
        lor_params = {**params, "lor_schluessel": lor_schluessel}
        lor_result = await db.execute(
            text(f"""
                SELECT date_trunc('day', pe.reported_at) AS day,
                       AVG(pe.price) AS avg_price,
                       MIN(pe.price) AS min_price,
                       MAX(pe.price) AS max_price
                FROM price_entries pe
                JOIN locations loc ON pe.location_id = loc.id
                JOIN public.lor l ON ST_Within(ST_Transform(loc.geom, ST_SRID(l.geom)), l.geom)
                WHERE l.lor_schluessel = :lor_schluessel
                  AND pe.reported_at BETWEEN :start AND :end
                  AND pe.price > 0
                  {drink_filter}
                  {city_filter_loc}
                GROUP BY 1
                ORDER BY 1
            """),
            lor_params,
        )
        lor_data = [
            {
                "date": row[0].strftime("%Y-%m-%d"),
                "avg_price": float(row[1]),
                "min_price": float(row[2]),
                "max_price": float(row[3]),
            }
            for row in lor_result
        ]

    return {"berlin": berlin, "lor": lor_data}


@router.get("/price-feed")
async def stats_price_changes(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    result = await db.execute(
        text("""
            SELECT sub.id, sub.price, sub.prev_price, sub.reported_at, sub.user_id,
                   sub.location_name, sub.drink_name, sub.username
            FROM (
                SELECT pe.id,
                       pe.price,
                       pe.reported_at,
                       pe.user_id,
                       LAG(pe.price) OVER (
                           PARTITION BY pe.location_id, pe.drink_id
                           ORDER BY pe.reported_at
                       ) AS prev_price,
                       loc.name AS location_name,
                       d.name AS drink_name,
                       u.username
                FROM price_entries pe
                JOIN locations loc ON pe.location_id = loc.id
                JOIN drinks d ON pe.drink_id = d.id
                LEFT JOIN users u ON pe.user_id = u.id
            ) sub
            WHERE sub.prev_price IS NOT NULL AND sub.price != sub.prev_price
            ORDER BY sub.reported_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    rows = result.fetchall()
    return [
        {
            "entry_id": row[0],
            "new_price": float(row[1]),
            "prev_price": float(row[2]),
            "delta": float(row[1]) - float(row[2]),
            "reported_at": row[3].isoformat() if row[3] else None,
            "user_id": row[4],
            "location_name": row[5],
            "drink_name": row[6],
            "username": row[7],
        }
        for row in rows
    ]


@router.get("/graph-drink-trends")
async def stats_drink_trends(
    granularity: str = "month",
    year: int | None = None,
    month: int | None = None,
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if granularity == "month" and not month:
        month = 1
    start, end = _time_window(granularity, year, month)

    drinks_result = await db.execute(
        select(Drink.id, Drink.name, Drink.color_hex).order_by(Drink.name)
    )
    drinks = [{"id": row[0], "name": row[1], "color_hex": row[2]} for row in drinks_result]

    city_filter = "AND location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    params: dict = {"start": start, "end": end}
    if city_id:
        params["city_id"] = city_id

    rows_result = await db.execute(
        text(f"""
            SELECT date_trunc('day', reported_at) AS day,
                   drink_id,
                   AVG(price) AS avg_price
            FROM price_entries
            WHERE reported_at BETWEEN :start AND :end
              AND price > 0
              {city_filter}
            GROUP BY 1, 2
            ORDER BY 1
        """),
        params,
    )

    day_map: dict[str, dict[str, float]] = {}
    for row in rows_result:
        day_str = row[0].strftime("%Y-%m-%d")
        if day_str not in day_map:
            day_map[day_str] = {}
        day_map[day_str][str(row[1])] = float(row[2])

    days = [{"date": d, "prices": day_map[d]} for d in sorted(day_map)]
    return {"drinks": drinks, "days": days}


@router.get("/graph-price-histogram")
async def stats_price_histogram(
    drink_id: int | None = None,
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    drinks_result = await db.execute(
        select(Drink.id, Drink.name, Drink.color_hex)
        .where(Drink.is_active == True)
        .order_by(Drink.name)
    )
    drinks = [{"id": row[0], "name": row[1], "color_hex": row[2]} for row in drinks_result]

    drink_filter = "AND drink_id = :drink_id" if drink_id is not None else ""
    city_filter = "AND location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    params: dict = {}
    if drink_id is not None:
        params["drink_id"] = drink_id
    if city_id is not None:
        params["city_id"] = city_id

    result = await db.execute(
        text(f"""
            SELECT FLOOR(price * 2) / 2 AS bucket_start,
                   drink_id,
                   COUNT(*) AS count
            FROM price_entries
            WHERE is_current = TRUE AND price > 0
              {drink_filter}
              {city_filter}
            GROUP BY 1, 2
            ORDER BY 1
        """),
        params,
    )

    bucket_map: dict[float, dict[str, int]] = {}
    for row in result:
        b = float(row[0])
        if b not in bucket_map:
            bucket_map[b] = {}
        bucket_map[b][str(row[1])] = int(row[2])

    buckets = [
        {"bucket_start": b, "label": f"{b:.2f}–{b + 0.5:.2f} €", "counts": bucket_map[b]}
        for b in sorted(bucket_map)
    ]
    return {"drinks": drinks, "buckets": buckets}


@router.get("/graph-moderation-activity")
async def stats_moderation_activity(
    granularity: str = "month",
    year: int | None = None,
    month: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    if granularity == "month" and not month:
        month = 1
    start, end = _time_window(granularity, year, month)

    result = await db.execute(
        text("""
            SELECT date_trunc('day', created_at) AS day, action, COUNT(*) AS count
            FROM moderation_logs
            WHERE created_at BETWEEN :start AND :end
            GROUP BY 1, 2
            ORDER BY 1
        """),
        {"start": start, "end": end},
    )

    day_map: dict[str, dict[str, int]] = {}
    for row in result:
        day_str = row[0].strftime("%Y-%m-%d")
        if day_str not in day_map:
            day_map[day_str] = {}
        day_map[day_str][row[1]] = int(row[2])

    days = [{"date": d, "counts": day_map[d]} for d in sorted(day_map)]
    return {"days": days, "actions": ["created", "updated", "confirmed", "flagged", "deleted"]}


@router.get("/graph-top-locations")
async def stats_top_locations(
    limit: int = 15,
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    city_filter = "AND loc.city_id = :city_id" if city_id else ""
    params: dict = {"limit": limit}
    if city_id:
        params["city_id"] = city_id

    result = await db.execute(
        text(f"""
            SELECT loc.name, COUNT(pe.id) AS entry_count, AVG(pe.price) AS avg_price
            FROM price_entries pe
            JOIN locations loc ON pe.location_id = loc.id
            WHERE pe.price > 0
              {city_filter}
            GROUP BY loc.id, loc.name
            ORDER BY entry_count DESC
            LIMIT :limit
        """),
        params,
    )
    return [
        {"location_name": row[0], "entry_count": int(row[1]), "avg_price": float(row[2])}
        for row in result
    ]


@router.get("/graph-freshness")
async def stats_freshness(
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    city_filter = "AND location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    params: dict = {}
    if city_id:
        params["city_id"] = city_id

    result = await db.execute(
        text(f"""
            SELECT
              CASE
                WHEN NOW() - last_confirmed_at < INTERVAL '7 days'  THEN 'Frisch'
                WHEN NOW() - last_confirmed_at < INTERVAL '30 days' THEN 'Aktuell'
                WHEN NOW() - last_confirmed_at < INTERVAL '90 days' THEN 'Veraltet'
                ELSE 'Alt'
              END AS bucket,
              COUNT(*) AS count
            FROM price_entries
            WHERE is_current = TRUE AND price > 0
              {city_filter}
            GROUP BY bucket
        """),
        params,
    )
    bucket_order = ["Frisch", "Aktuell", "Veraltet", "Alt"]
    data = {row[0]: int(row[1]) for row in result}
    return [{"label": b, "count": data.get(b, 0)} for b in bucket_order]


@router.get("/graph-heatmap")
async def stats_heatmap(
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    city_filter = "WHERE location_id IN (SELECT id FROM locations WHERE city_id = :city_id)" if city_id else ""
    params: dict = {}
    if city_id:
        params["city_id"] = city_id

    result = await db.execute(
        text(f"""
            SELECT EXTRACT(dow FROM reported_at)::int AS dow,
                   EXTRACT(hour FROM reported_at AT TIME ZONE 'Europe/Berlin')::int AS hour,
                   COUNT(*) AS count
            FROM price_entries
            {city_filter}
            GROUP BY dow, hour
            ORDER BY dow, hour
        """),
        params,
    )
    return [{"dow": row[0], "hour": row[1], "count": int(row[2])} for row in result]


@router.get("/graph-location-types")
async def stats_location_types(
    city_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_moderator),
):
    city_filter = "AND loc.city_id = :city_id" if city_id else ""
    params: dict = {}
    if city_id:
        params["city_id"] = city_id

    result = await db.execute(
        text(f"""
            SELECT loc.location_type::text, COUNT(pe.id) AS count, AVG(pe.price) AS avg_price
            FROM price_entries pe
            JOIN locations loc ON pe.location_id = loc.id
            WHERE pe.price > 0
              {city_filter}
            GROUP BY loc.location_type
            ORDER BY count DESC
        """),
        params,
    )
    return [
        {
            "location_type": row[0],
            "label": LOCATION_TYPE_LABELS.get(row[0], row[0]),
            "color_hex": LOCATION_TYPE_COLORS.get(row[0], "#999"),
            "count": int(row[1]),
            "avg_price": float(row[2]),
        }
        for row in result
    ]
