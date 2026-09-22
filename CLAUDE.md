# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SpritzMap is a WebMap for visualizing Spritz drink prices (Aperol, Limoncello, etc.) at bars and beer gardens in German cities (started in Berlin). Users can register to submit and confirm prices. Data is stored in PostgreSQL/PostGIS; summary layers are served via GeoServer.

## Architecture

```
frontend/   — SvelteKit 5 (Runes) + MapLibre GL + TypeScript
backend/    — FastAPI (Python 3.12) + SQLAlchemy async + PostGIS
geoserver/  — kartoza/geoserver Docker image, reads from the same DB
```

**Key data flow:**
- Every location belongs to exactly one city (`locations.city_id` NOT NULL) → all stats are per city
- Admins add cities by name search (Nominatim); boundary, districts (`areas`) and the first OSM import run automatically (`backend/app/services/geo_import.py`)
- OSM sync (`backend/app/services/osm_sync.py`) is a staggered queue: every 10 min at most ONE due city (`cities.next_sync_at`), guarded by a Postgres advisory lock, bulk upsert, query by city boundary, backoff on failure, deactivation only after 7 days unseen. Each run is logged in `osm_sync_runs`
- `GET /locations/geojson` returns filtered GeoJSON for MapLibre GL markers
- GeoServer publishes ONE WMS layer `spritzmap:area_summary` for all cities (`viewparams=city_id:X;drink_id:Y`) — shown at zoom < 15, hidden at zoom ≥ 15 (`WMS_MAX_ZOOM` in `SpritzMap.svelte`). Setup: `backend/geoserver/setup_area_layer.py`
- Moderators edit only in assigned cities (`moderator_cities`, checks in `app/api/deps.py`: `assert_can_moderate`), but can read everything; admins edit everywhere

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
| `backend/app/services/osm_sync.py` | OSM Overpass sync: queue, lock, bulk upsert, mirrors |
| `backend/app/services/geo_import.py` | City creation (Nominatim), district import from OSM, GeoJSON upload |
| `backend/app/services/spatial.py` | `assign_areas` – precomputed point-in-polygon `locations.area_id` |
| `backend/geoserver/area_summary.sql` | SQL view behind the shared area layer |
| `backend/app/api/routes/locations.py` | GeoJSON endpoint with drink/price filter |
| `frontend/src/lib/utils/markerIcon.ts` | SVG wine glass icon generator (color + intensity) |
| `frontend/src/lib/components/SpritzMap.svelte` | Main MapLibre GL map, marker loading, WMS layer |
| `geoserver/README.md` | Step-by-step GeoServer LOR layer setup |
| `backend/app/api/routes/photos.py` | Photo upload/list/delete (validation only, no re-encoding) |
| `frontend/src/lib/utils/imageProcessing.ts` | Client-side resize → WebP + thumbnail, strips EXIF |
| `frontend/src/lib/utils/colorAnalysis.ts` | AI step 1: color_value suggestion from photo pixels (calibration constants at top) |
| `frontend/src/lib/utils/glassDetection.ts` | AI step 2: glass shape via COCO-SSD (TF.js, lazy-loaded) |
| `frontend/src/lib/components/MapLegend.svelte` | Zoom-dependent map legend; tiers from `GET /config/price-tiers` |

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

## Login (Authentik)

- `AUTH_MODE` (backend env): `legacy` (own accounts, default) → `both` (transition: OIDC + old login, no new local sign-ups) → `authentik` (OIDC only)
- The backend is the OIDC client (`app/services/oidc.py`, routes in `app/api/routes/oidc.py`): code flow + PKCE, validates the ID token, then issues the usual SpritzMap JWT via a one-time code (`/auth/oidc/exchange`). Roles and city assignments stay in SpritzMap; users are linked **only** via `users.authentik_sub` (Authentik user UUID), never by e-mail
- Authentik config lives in `authentik/` (blueprint, apply script, step-0 script, runbook in `authentik/README.md`). Accounts from SpritzMap sign-up land in group `spritzmap-users` and may use **only** the `spritzmap` application; every other Authentik application must be bound to `hegik-services`
- Account deletion: SpritzMap anonymizes its data, then sends the user to Authentik's unenrollment flow (the backend holds no Authentik admin token)

## Photos & AI analysis

- All heavy lifting runs in the browser: compression (max 1600 px WebP, 400 px thumb) and AI suggestions. The backend only validates (Pillow `verify`, WebP/JPEG, ≤ 2000 px, ≤ 3 MB) and stores files.
- Files live in `MEDIA_ROOT` (`/app/media`, persistent Coolify volume `spritzmap-media`) and are served under `/media/…` with immutable caching.
- AI values are **suggestions only**: `color_value` / `glass_type` are what the user confirmed; `ai_color_value` / `ai_glass_type` keep the raw suggestion for accuracy tracking. `PATCH /prices/{id}/glass-type` corrects the glass later without touching timestamps.
- COCO-SSD model is self-hosted in `frontend/static/models/coco-ssd/` (weights quantized to uint8, ~4.6 MB) — no requests to Google.

## Deployment (Coolify)

Each service is a separate Coolify application backed by the shared PostgreSQL instance. Set env vars (`DATABASE_URL`, `SECRET_KEY`, `FRONTEND_URL`, `VITE_API_URL`, `VITE_GEOSERVER_URL`) in Coolify's environment panel. GeoServer uses the `kartoza/geoserver:2.25.0` Docker image.

## Frontend Notes (Svelte 5)

- All components use **Runes syntax** (`$state`, `$props`, `$effect`, `$bindable`)
- Svelte stores (`authStore`, `drinks`, `selectedDrinkId`, `selectedPriceTier`) are used for cross-component state
- `on:click` → `onclick` (Svelte 5 native event syntax)
- MapLibre GL is imported dynamically inside `onMount` to avoid SSR issues

## Offene Aufgaben

- [ ] Gebietsauswertungen
- [ ] GitHub-Webhook → Coolify deployt nach Push nicht automatisch (manuell per Coolify deployen)