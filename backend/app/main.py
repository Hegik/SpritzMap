from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.core.database import Base
from app.api.routes import auth, locations, prices, drinks, moderation
from app.services.osm_sync import sync_osm_locations
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def scheduled_osm_sync():
    async with AsyncSessionLocal() as db:
        try:
            await sync_osm_locations(db)
        except Exception as e:
            logger.warning("OSM sync failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initial OSM sync — non-blocking, server starts even if Overpass is unavailable
    async with AsyncSessionLocal() as db:
        try:
            await sync_osm_locations(db)
        except Exception as e:
            logger.warning("Initial OSM sync failed (will retry on schedule): %s", e)

    # Schedule recurring sync
    scheduler.add_job(
        scheduled_osm_sync,
        "interval",
        hours=settings.OSM_SYNC_INTERVAL_HOURS,
        id="osm_sync",
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


@app.get("/health")
async def health():
    return {"status": "ok"}
