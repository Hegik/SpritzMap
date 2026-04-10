from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.database import get_db
from app.models.price_entry import PriceEntry
from app.models.moderation_log import ModerationLog
from app.models.user import User
from app.api.deps import get_moderator

router = APIRouter(prefix="/moderation", tags=["moderation"])


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
