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
    OSM_SYNC_INTERVAL_HOURS: int = 24

    # Color averaging
    COLOR_AVERAGE_SAMPLE_SIZE: int = 50

    # Foto-Uploads (persistentes Volume, in Coolify unter /app/media gemountet)
    MEDIA_ROOT: str = "/app/media"
    MAX_UPLOAD_BYTES: int = 3_000_000
    MAX_IMAGE_DIMENSION: int = 2000

    # SMTP
    SMTP_HOST: str = "smtp.protonmail.ch"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # Login: "legacy" (eigene Konten), "both" (Übergang: beides, aber keine neuen Legacy-Registrierungen),
    # "authentik" (nur noch OIDC über Authentik)
    AUTH_MODE: str = "legacy"
    # Öffentliche Authentik-Adresse der SpritzMap-Brand (Browser-Redirects, Konto-Links)
    AUTHENTIK_URL: str = "https://spritz.auth.hegik.de"
    # Optional: Server-zu-Server-Aufrufe (Discovery, Token, JWKS) über eine interne Adresse; der Host-Header
    # bleibt der öffentliche, damit Authentik Brand und Issuer gleich auflöst
    AUTHENTIK_INTERNAL_URL: str = ""
    OIDC_CLIENT_ID: str = "spritzmap"
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = "http://localhost:8000/auth/oidc/callback"
    OIDC_APP_SLUG: str = "spritzmap"
    OIDC_ENROLLMENT_FLOW: str = "spritzmap-enrollment"
    OIDC_UNENROLLMENT_FLOW: str = "spritzmap-unenrollment"

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
