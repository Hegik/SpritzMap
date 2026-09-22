# SpritzMap

WebMap für Spritz-Preise (Aperol, Limoncello u. a.) in Bars und Biergärten deutscher Städte – gestartet in Berlin.
Registrierte Nutzer melden und bestätigen Preise, optional mit Foto; die Karte zeigt Preisstufe und Farbintensität je
Lokal sowie eine Gebietsauswertung pro Stadtteil.

## Funktionen

- **Karte** (MapLibre GL): Weinglas-Marker je Lokal, eingefärbt nach Preisstufe (`€` / `€€` / `€€€`) und Farbintensität
  des Drinks; Filter nach Getränk und Preisstufe; zoomabhängige Legende
- **Gebietsauswertung**: ein gemeinsamer WMS-Layer (GeoServer) für alle Städte, sichtbar bei Zoom < 15
- **Mehrere Städte**: Admins legen Städte per Namenssuche an; Stadtgrenze, Stadtteile und Lokale kommen automatisch aus
  OpenStreetMap, danach regelmäßiger OSM-Sync
- **Fotos & KI-Vorschläge**: Bildkomprimierung, Farbanalyse und Glaserkennung (COCO-SSD) laufen komplett im Browser;
  KI-Werte sind nur Vorschläge, die der Nutzer bestätigt
- **Moderation**: Moderatoren bearbeiten Einträge ihrer zugewiesenen Städte, Admins überall; Dashboard mit Statistiken
- **Login**: eigene Konten oder OIDC über Authentik (umschaltbar per `AUTH_MODE`)

## Architektur

```
frontend/   SvelteKit 5 (Runes) + MapLibre GL + TypeScript
backend/    FastAPI (Python 3.12) + SQLAlchemy async + Alembic
            PostgreSQL 17 / PostGIS 3.4
geoserver/  Doku zum WMS-Layer spritzmap:area_summary (Skript + SQL in backend/geoserver/)
authentik/  Blueprint, Mailvorlagen-Setup und Runbook für den OIDC-Login
```

| Bereich | Wichtige Dateien |
|---|---|
| Karte | `frontend/src/lib/components/SpritzMap.svelte`, `frontend/src/lib/utils/markerIcon.ts` |
| Preisdaten | `backend/app/api/routes/locations.py`, `backend/app/api/routes/prices.py` |
| Städte & OSM | `backend/app/services/geo_import.py`, `backend/app/services/osm_sync.py`, `backend/app/services/spatial.py` |
| Gebietslayer | `backend/geoserver/area_summary.sql`, `backend/geoserver/setup_area_layer.py` |
| Fotos & KI | `frontend/src/lib/utils/imageProcessing.ts`, `colorAnalysis.ts`, `glassDetection.ts` |
| Login | `backend/app/services/oidc.py`, `backend/app/api/routes/oidc.py` |

## Lokale Entwicklung

### Komplett per Docker

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

Frontend `:3000`, Backend `:8000`, GeoServer `:8080`, PostgreSQL `:5432`.

### Einzeln

```bash
# Backend
cd backend
cp .env.example .env            # DATABASE_URL (postgresql+asyncpg://…) und SECRET_KEY setzen
pip install -r requirements.txt
alembic upgrade head
python -m app.services.seed     # Getränke anlegen (einmalig)
uvicorn app.main:app --reload   # :8000

# Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                     # :5173
```

Nach Model-Änderungen: `alembic revision --autogenerate -m "…"` und `alembic upgrade head`.

## Konfiguration

Alle Einstellungen stehen mit Beispielwerten in `backend/.env.example` und `frontend/.env.example`.
Die Preisstufen lassen sich ohne Codeänderung über `PRICE_TIER_1_MAX` (Standard 6,50 €) und `PRICE_TIER_2_MAX`
(Standard 8,50 €) anpassen.

## Deployment

Jeder Dienst läuft als eigene Coolify-Anwendung an einer gemeinsamen PostgreSQL-Instanz. Das Backend führt beim Start
die Migrationen aus (`backend/start.sh`). Hochgeladene Fotos liegen im persistenten Volume unter `MEDIA_ROOT`.

- GeoServer-Layer einrichten: [`geoserver/README.md`](geoserver/README.md)
- Authentik-Login einrichten und umstellen: [`authentik/README.md`](authentik/README.md)

## Daten & Lizenzen

Kartendaten und Lokale © [OpenStreetMap](https://www.openstreetmap.org/copyright)-Mitwirkende (ODbL).
Schrift „Open Sans“ siehe `frontend/static/fonts/LICENSE.txt`.
