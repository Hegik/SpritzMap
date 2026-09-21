from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/price-tiers")
async def get_price_tiers():
    """Preisstufen-Grenzen für die Kartenlegende (aus .env, damit Frontend und Backend übereinstimmen)."""
    return [
        {"label": "€", "min": None, "max": settings.PRICE_TIER_1_MAX},
        {"label": "€€", "min": settings.PRICE_TIER_1_MAX, "max": settings.PRICE_TIER_2_MAX},
        {"label": "€€€", "min": settings.PRICE_TIER_2_MAX, "max": None},
    ]
