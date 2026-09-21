from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from app.core.database import get_db
from app.core.config import settings
from app.models.price_entry import PriceEntry
from app.models.moderation_log import ModerationLog
from app.models.user import User, UserRole
from app.schemas.price_entry import PriceEntryCreate, PriceEntryUpdate, PriceEntryOut, PriceEntryUnavailable, GlassTypeUpdate
from app.api.deps import get_current_user, can_moderate
from app.models.location import Location

router = APIRouter(prefix="/prices", tags=["prices"])


def _to_out(entry: PriceEntry) -> PriceEntryOut:
    return PriceEntryOut(
        **{
            "id": entry.id,
            "location_id": entry.location_id,
            "drink_id": entry.drink_id,
            "user_id": entry.user_id,
            "price": entry.price,
            "price_tier": settings.get_price_tier(entry.price),
            "color_value": entry.color_value,
            "reported_at": entry.reported_at,
            "last_confirmed_at": entry.last_confirmed_at,
            "is_current": entry.is_current,
            "note": entry.note,
            "glass_type": entry.glass_type,
            "ai_color_value": entry.ai_color_value,
            "ai_glass_type": entry.ai_glass_type,
        }
    )


async def _entry_city_id(db: AsyncSession, entry: PriceEntry) -> int:
    return (await db.execute(select(Location.city_id).where(Location.id == entry.location_id))).scalar_one()


async def _get_own_entry(db: AsyncSession, entry_id: int, user: User) -> PriceEntry:
    """Eintrag, den der Nutzer ändern darf: eigener Eintrag oder Moderator dieser Stadt."""
    result = await db.execute(select(PriceEntry).where(PriceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Price entry not found")
    if entry.user_id != user.id and not await can_moderate(user, await _entry_city_id(db, entry), db):
        raise HTTPException(status_code=403, detail="Not allowed")
    return entry


@router.post("/unavailable", status_code=status.HTTP_201_CREATED)
async def mark_drink_unavailable(
    data: PriceEntryUnavailable,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a specific drink as unavailable at a location."""
    entry = PriceEntry(
        location_id=data.location_id,
        drink_id=data.drink_id,
        user_id=current_user.id,
        price=0.0,
        color_value=0,
        unavailable=True,
        is_current=True,
    )
    db.add(entry)
    await db.commit()
    return {"detail": "Drink marked as unavailable"}


@router.post("/", response_model=PriceEntryOut, status_code=status.HTTP_201_CREATED)
async def create_price_entry(
    data: PriceEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = PriceEntry(
        location_id=data.location_id,
        drink_id=data.drink_id,
        user_id=current_user.id,
        price=data.price,
        color_value=data.color_value,
        note=data.note,
        glass_type=data.glass_type,
        ai_color_value=data.ai_color_value,
        ai_glass_type=data.ai_glass_type,
    )
    db.add(entry)
    await db.flush()

    log = ModerationLog(
        price_entry_id=entry.id,
        moderator_id=None,
        action="created",
    )
    db.add(log)
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)


@router.put("/{entry_id}", response_model=PriceEntryOut)
async def update_price_entry(
    entry_id: int,
    data: PriceEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_own_entry(db, entry_id, current_user)

    entry.price = data.price
    entry.color_value = data.color_value
    entry.note = data.note
    if data.glass_type is not None:
        entry.glass_type = data.glass_type
    entry.reported_at = datetime.now(timezone.utc)
    entry.last_confirmed_at = datetime.now(timezone.utc)
    entry.is_current = True

    log = ModerationLog(
        price_entry_id=entry.id,
        moderator_id=current_user.id,
        action="updated",
    )
    db.add(log)
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)


@router.patch("/{entry_id}/glass-type", response_model=PriceEntryOut)
async def update_glass_type(
    entry_id: int,
    data: GlassTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Korrigiert nur die Glasform. Keine neue Preismeldung: Zeitstempel bleiben unverändert."""
    entry = await _get_own_entry(db, entry_id, current_user)
    entry.glass_type = data.glass_type
    db.add(ModerationLog(
        price_entry_id=entry.id,
        moderator_id=current_user.id,
        action="glass_type_changed",
        note=data.glass_type.value if data.glass_type else None,
    ))
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = await _get_own_entry(db, entry_id, current_user)
    await db.delete(entry)
    await db.commit()


@router.post("/{entry_id}/confirm", response_model=PriceEntryOut)
async def confirm_price(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a price as still current."""
    result = await db.execute(select(PriceEntry).where(PriceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Price entry not found")
    if entry.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Eigene Einträge können nicht bestätigt werden")

    recent = await db.execute(
        select(ModerationLog.id)
        .where(ModerationLog.price_entry_id == entry.id)
        .where(ModerationLog.moderator_id == current_user.id)
        .where(ModerationLog.action == "confirmed")
        .where(ModerationLog.created_at >= datetime.now(timezone.utc) - timedelta(hours=24))
        .limit(1)
    )
    if recent.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Bereits bestätigt")

    entry.last_confirmed_at = datetime.now(timezone.utc)
    entry.is_current = True

    log = ModerationLog(
        price_entry_id=entry.id,
        moderator_id=current_user.id,
        action="confirmed",
    )
    db.add(log)
    await db.commit()
    await db.refresh(entry)
    return _to_out(entry)
