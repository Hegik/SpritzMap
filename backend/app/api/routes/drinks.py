from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.drink import Drink
from app.schemas.drink import DrinkOut, DrinkCreate
from app.api.deps import get_admin
from app.models.user import User

router = APIRouter(prefix="/drinks", tags=["drinks"])


@router.get("/", response_model=list[DrinkOut])
async def list_drinks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Drink).where(Drink.is_active == True))
    return result.scalars().all()


@router.post("/", response_model=DrinkOut, status_code=status.HTTP_201_CREATED)
async def create_drink(
    data: DrinkCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin),
):
    drink = Drink(name=data.name, color_hex=data.color_hex)
    db.add(drink)
    await db.commit()
    await db.refresh(drink)
    return drink
