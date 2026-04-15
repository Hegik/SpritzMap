from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.core.database import get_db
from app.models.user import User, UserRole
from app.api.deps import get_admin

router = APIRouter(prefix="/admin", tags=["admin"])


class UpdateRole(BaseModel):
    role: UserRole


class UpdateActive(BaseModel):
    is_active: bool


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
