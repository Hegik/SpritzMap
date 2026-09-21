from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.core.database import Base
from app.api.routes import auth, locations, prices, drinks, moderation, admin, cities, photos, config
from app.services.osm_sync import run_sync
from datetime import datetime, timedelta, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Gestaffelter OSM-Sync: pro Tick höchstens eine fällige Stadt (siehe services/osm_sync.py)
OSM_SYNC_TICK_MINUTES = 10


async def scheduled_osm_sync():
    try:
        await run_sync()
    except Exception as e:
        logger.warning("OSM sync tick failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Kein blockierender Sync beim Start mehr: der erste Tick läuft kurz nach dem Hochfahren
    scheduler.add_job(
        scheduled_osm_sync,
        "interval",
        minutes=OSM_SYNC_TICK_MINUTES,
        id="osm_sync",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    scheduler.start()

    yield

    scheduler.shutdown()


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SpritzMap API",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(locations.router)
app.include_router(prices.router)
app.include_router(drinks.router)
app.include_router(moderation.router)
app.include_router(admin.router)
app.include_router(cities.router)
app.include_router(photos.router)
app.include_router(config.router)


class ImmutableStaticFiles(StaticFiles):
    """Fotos haben UUID-Dateinamen und ändern sich nie → langes Browser-Caching."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# python:slim kennt .webp nicht → sonst text/plain
mimetypes.add_type("image/webp", ".webp")
Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
app.mount("/media", ImmutableStaticFiles(directory=settings.MEDIA_ROOT), name="media")


@app.get("/health")
async def health():
    return {"status": "ok"}
