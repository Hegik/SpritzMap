# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SpritzMap is a WebMap for visualizing Spritz drink prices (Aperol, Limoncello, etc.) at bars and beer gardens in Berlin. Users can register to submit and confirm prices. Data is stored in PostgreSQL/PostGIS; summary layers are served via GeoServer.

## Architecture

```
frontend/   — SvelteKit 5 (Runes) + MapLibre GL + TypeScript
backend/    — FastAPI (Python 3.12) + SQLAlchemy async + PostGIS
geoserver/  — kartoza/geoserver Docker image, reads from the same DB
```

**Key data flow:**
- Locations are synced from OSM (Overpass API) on startup + every 24h (`backend/app/services/osm_sync.py`)
- `GET /locations/geojson` returns filtered GeoJSON for MapLibre GL markers
- GeoServer publishes a WMS layer `spritzmap:lor_price_summary` — shown at zoom < 17, hidden at zoom ≥ 17
- The layer is parameterized via `viewparams=drink_id:X`; color and index are computed per-drink in SQL

## Development Commands

### Backend
```bash
cd backend
cp .env.example .env        # fill in DATABASE_URL and SECRET_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload   # starts on :8000, auto-creates tables + OSM sync
```

Seed initial drinks after first start:
```bash
python -m app.services.seed
```

Run Alembic migrations (after model changes):
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Frontend
```bash
cd frontend
cp .env.example .env
npm install
npm run dev         # starts on :5173
npm run build
npm run preview
```

### Full stack (local)
```bash
docker compose up --build
```

Services: frontend `:3000`, backend `:8000`, geoserver `:8080`, postgres `:5432`

## Key Files

| File | Purpose |
|---|---|
| `backend/app/core/config.py` | All settings incl. price tier thresholds (`PRICE_TIER_1_MAX`, `PRICE_TIER_2_MAX`) |
| `backend/app/services/osm_sync.py` | OSM Overpass sync logic, Berlin bbox |
| `backend/app/api/routes/locations.py` | GeoJSON endpoint with drink/price filter |
| `frontend/src/lib/utils/markerIcon.ts` | SVG wine glass icon generator (color + intensity) |
| `frontend/src/lib/components/SpritzMap.svelte` | Main MapLibre GL map, marker loading, WMS layer |
| `geoserver/README.md` | Step-by-step GeoServer LOR layer setup |

## Price Tiers

Configured in `backend/app/core/config.py`:
- `€`   → up to 6.50 €
- `€€`  → up to 8.50 €
- `€€€` → above 8.50 €

Change `PRICE_TIER_1_MAX` / `PRICE_TIER_2_MAX` in `.env` to adjust without code changes.

## Database

- PostgreSQL 16 + PostGIS 3.4
- `DATABASE_URL` must use `postgresql+asyncpg://` scheme
- `locations.geom` is a PostGIS `POINT` (SRID 4326)
- Color intensity: `price_entries.color_value` is 0–255; the map uses the **average of the 50 most recent entries** per location+drink

## Deployment (Coolify)

Each service is a separate Coolify application backed by the shared PostgreSQL instance. Set env vars (`DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL`, `VITE_API_URL`, `VITE_GEOSERVER_URL`) in Coolify's environment panel. GeoServer uses the `kartoza/geoserver:2.25.0` Docker image.

## Frontend Notes (Svelte 5)

- All components use **Runes syntax** (`$state`, `$props`, `$effect`, `$bindable`)
- Svelte stores (`authStore`, `drinks`, `selectedDrinkId`, `selectedPriceTier`) are used for cross-component state
- `on:click` → `onclick` (Svelte 5 native event syntax)
- MapLibre GL is imported dynamically inside `onMount` to avoid SSR issues

## Offene Aufgaben

- 