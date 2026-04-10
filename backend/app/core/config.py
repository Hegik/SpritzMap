from pydantic_settings import BaseSettings
from typing import ClassVar


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Price thresholds (€ / €€ / €€€)
    PRICE_TIER_1_MAX: float = 6.50
    PRICE_TIER_2_MAX: float = 8.50

    # OSM Sync
    OSM_BBOX_BERLIN: str = "52.3382,13.0883,52.6755,13.7611"
    OSM_SYNC_INTERVAL_HOURS: int = 24

    # Color averaging
    COLOR_AVERAGE_SAMPLE_SIZE: int = 50

    # SMTP
    SMTP_HOST: str = "smtp.protonmail.ch"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    PRICE_TIERS: ClassVar[dict] = {
        1: {"label": "€", "max": None},
        2: {"label": "€€", "max": None},
        3: {"label": "€€€", "max": None},
    }

    def get_price_tier(self, price: float) -> str:
        if price <= self.PRICE_TIER_1_MAX:
            return "€"
        elif price <= self.PRICE_TIER_2_MAX:
            return "€€"
        return "€€€"

    class Config:
        env_file = ".env"


settings = Settings()
