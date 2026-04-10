# GeoServer Setup

## LOR-Layer einrichten

1. LOR-Geodaten für Berlin herunterladen:
   https://daten.berlin.de/datensaetze/lebensweltlich-orientierte-raeume-lor-planungsraeume-berlin

2. Shapefile in `./data/` ablegen.

3. GeoServer unter http://localhost:8080/geoserver aufrufen (admin / geoserver).

4. Neuen Workspace `spritzmap` anlegen.

5. Neuen Store vom Typ **PostGIS** anlegen:
   - Host: db (Docker) oder Coolify-DB-Host
   - Port: 5432
   - Database: spritzmap
   - User/Password: aus .env

6. Layer `lor_price_summary` aus folgendem SQL-View publizieren:

```sql
SELECT
  l.lor_schluessel,
  l.geom,
  AVG(pe.price)   AS avg_price,
  COUNT(pe.id)    AS entry_count
FROM lor_planungsraeume l
LEFT JOIN locations loc ON ST_Within(loc.geom, l.geom)
LEFT JOIN price_entries pe ON pe.location_id = loc.id AND pe.is_current = TRUE
GROUP BY l.lor_schluessel, l.geom
```

7. SLD-Style für Farbkodierung nach `avg_price` anlegen (€ / €€ / €€€).
