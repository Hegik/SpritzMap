#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
# Hinter Traefik: echte Client-IP aus X-Forwarded-For übernehmen (sonst teilen sich alle Besucher ein Rate-Limit).
# Traefik ersetzt einen vom Client mitgeschickten Header, der Container ist nur im Docker-Netz erreichbar.
# Kein Access-Log: SpritzMap speichert keine IP-Adressen (siehe Datenschutzerklärung).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --no-access-log
