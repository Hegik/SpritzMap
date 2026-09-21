from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole
from app.models.moderator_city import moderator_cities

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_moderator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return current_user


async def moderated_city_ids(user: User, db: AsyncSession) -> set[int] | None:
    """Städte, in denen der Nutzer moderieren (bearbeiten) darf. None = alle (Admin)."""
    if user.role == UserRole.admin:
        return None
    if user.role != UserRole.moderator:
        return set()
    rows = await db.execute(select(moderator_cities.c.city_id).where(moderator_cities.c.user_id == user.id))
    return {r.city_id for r in rows}


async def can_moderate(user: User, city_id: int, db: AsyncSession) -> bool:
    allowed = await moderated_city_ids(user, db)
    return allowed is None or city_id in allowed


async def assert_can_moderate(user: User, city_ids: int | set[int], db: AsyncSession) -> None:
    """403, wenn der Nutzer nicht in allen genannten Städten moderieren darf."""
    allowed = await moderated_city_ids(user, db)
    wanted = {city_ids} if isinstance(city_ids, int) else set(city_ids)
    if allowed is not None and not wanted <= allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Moderationsrechte für diese Stadt")


async def get_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user
