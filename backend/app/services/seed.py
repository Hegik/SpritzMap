"""
Initial seed: default drinks with their brand colors.
Run once after first migration: python -m app.services.seed
"""
import asyncio
from app.core.database import AsyncSessionLocal, engine, Base
from app.models.drink import Drink
from sqlalchemy import select

INITIAL_DRINKS = [
    {"name": "Aperol Spritz",    "color_hex": "#FF6B35"},
    {"name": "Limoncello Spritz","color_hex": "#E8E800"},
    {"name": "Select Spritz",    "color_hex": "#C8001A"},
    {"name": "Cynar Spritz",     "color_hex": "#4A6741"},
    {"name": "Sanddorn Spritz",  "color_hex": "#E87000"},
    {"name": "Campari Spritz",   "color_hex": "#CC0000"},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        for drink_data in INITIAL_DRINKS:
            result = await db.execute(select(Drink).where(Drink.name == drink_data["name"]))
            if not result.scalar_one_or_none():
                db.add(Drink(**drink_data))
        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
