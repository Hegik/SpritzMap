from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.database import get_db
from app.core.config import settings
from app.models.price_entry import PriceEntry
from app.models.moderation_log import ModerationLog
from app.models.user import User
from app.schemas.price_entry import PriceEntryCreate, PriceEntryUpdate, PriceEntryOut
from app.api.deps import get_current_user

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
        }
    )


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
    result = await db.execute(select(PriceEntry).where(PriceEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Price entry not found")

    entry.price = data.price
    entry.color_value = data.color_value
    entry.note = data.note
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
