"""
Warteschlange für OSM-Arbeiten pro Stadt (Gebietsimport + Lokal-Sync).

- läuft nie parallel: Postgres-Advisory-Lock über alle Worker hinweg
- pro Tick höchstens MAX_CITIES_PER_TICK fällige Städte, mit Pause dazwischen (schont Overpass)
- jede Stadt hat ein Zeitbudget; eine hängende Stadt blockiert die Warteschlange nicht
- fehlende Gebiete werden bei jedem Lauf erneut versucht, bis der Import klappt
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text, update

from app.core.database import AsyncSessionLocal, engine
from app.models.city import City
from app.models.osm_sync_run import OsmSyncRun
from app.services.geo_import import import_osm_areas
from app.services.osm_sync import RETRY_BASE, RETRY_MAX, sync_osm_locations

logger = logging.getLogger(__name__)

SYNC_LOCK_KEY = 815_001  # projektweit feste Advisory-Lock-ID
MAX_CITIES_PER_TICK = 3
PAUSE_BETWEEN_CITIES = 10  # Sekunden
CITY_DEADLINE = 15 * 60  # Sekunden pro Stadt (Gebietsimport + Sync)


async def _mark_failed(city_id: int, reason: str) -> None:
    """Nach Timeout/Abbruch: offenen Lauf schließen und Backoff setzen (eigene Session, alte ist abgebrochen)."""
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(OsmSyncRun)
            .where(OsmSyncRun.city_id == city_id, OsmSyncRun.status == "running")
            .values(status="failed", finished_at=now, error=reason)
        )
        city = await db.get(City, city_id)
        if city:
            city.sync_failures = (city.sync_failures or 0) + 1
            city.last_sync_status = "failed"
            city.last_sync_error = reason
            city.next_sync_at = now + min(RETRY_BASE * 2 ** (city.sync_failures - 1), RETRY_MAX)
        await db.commit()


async def fail_interrupted_runs() -> None:
    """Beim Start: Läufe, die ein Neustart unterbrochen hat, als fehlgeschlagen markieren."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(OsmSyncRun).where(OsmSyncRun.status == "running")
            .values(status="failed", finished_at=datetime.now(timezone.utc), error="Durch Neustart unterbrochen")
        )
        await db.commit()


async def _process_city(city_id: int) -> None:
    async with AsyncSessionLocal() as db:
        city = await db.get(City, city_id)
        if city is None:
            return
        name = city.name  # nach einem Rollback nicht mehr lesbar (abgelaufenes ORM-Objekt)
        # Erst die Lokale: die Gebietsebene wird danach gewählt, wie viele Lokale sie abdeckt
        try:
            await sync_osm_locations(db, city)
        except Exception:
            pass  # bereits protokolliert, Backoff gesetzt
        # Gebiete fehlen noch (neue Stadt, oder Overpass war überlastet) → bei jedem Lauf erneut versuchen
        if city.area_source == "none" and city.boundary is not None:
            try:
                result = await import_osm_areas(db, city)
                if result.get("skipped"):
                    logger.info("Keine OSM-Gebiete für '%s': %s", name, result.get("reason"))
            except Exception as e:
                await db.rollback()
                logger.warning("Gebietsimport für '%s' fehlgeschlagen: %s", name, e)


async def run_city_jobs(city_id: int | None = None) -> int:
    """Arbeitet fällige Städte ab (oder genau die angegebene). Gibt die Anzahl bearbeiteter Städte zurück."""
    async with engine.connect() as lock_conn:
        locked = (await lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SYNC_LOCK_KEY})).scalar()
        await lock_conn.commit()
        if not locked:
            logger.info("OSM-Jobs übersprungen: läuft bereits (Stadt bleibt fällig)")
            return 0
        processed = 0
        try:
            while processed < (1 if city_id is not None else MAX_CITIES_PER_TICK):
                async with AsyncSessionLocal() as db:
                    query = select(City.id, City.name).where(City.is_active == True, City.osm_sync_enabled == True)
                    if city_id is not None:
                        query = query.where(City.id == city_id)
                    else:
                        query = query.where(City.next_sync_at <= datetime.now(timezone.utc)).order_by(City.next_sync_at)
                    row = (await db.execute(query.limit(1))).first()
                if row is None:
                    break
                if processed:
                    await asyncio.sleep(PAUSE_BETWEEN_CITIES)
                try:
                    await asyncio.wait_for(_process_city(row.id), timeout=CITY_DEADLINE)
                except asyncio.TimeoutError:
                    logger.warning("OSM-Job für '%s' nach %d s abgebrochen", row.name, CITY_DEADLINE)
                    await _mark_failed(row.id, f"Zeitbudget von {CITY_DEADLINE // 60} min überschritten (Overpass überlastet?)")
                processed += 1
            return processed
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SYNC_LOCK_KEY})
            await lock_conn.commit()
