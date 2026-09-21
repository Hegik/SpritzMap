# GeoServer: Gebietslayer `spritzmap:area_summary`

Ein **einziger** WMS-Layer liefert die Gebietszusammenfassung für **alle** Städte. Die Stadt wird per
`viewparams` gewählt – für neue Städte ist in GeoServer nichts mehr einzurichten.

```
/geoserver/wms?...&LAYERS=spritzmap:area_summary&viewparams=city_id:1;drink_id:1
```

## Einrichtung (einmalig, idempotent)

```bash
GEOSERVER_URL=https://geoserver.example.de/geoserver \
GEOSERVER_USER=admin GEOSERVER_PASSWORD=... \
DB_HOST=... DB_PORT=5432 DB_NAME=spritzmap DB_USER=... DB_PASSWORD=... \
python3 geoserver/setup_area_layer.py
```

Das Skript (nur Python-Standardbibliothek) legt per REST-API an bzw. aktualisiert:

| Objekt | Name |
|---|---|
| Workspace | `spritzmap` |
| PostGIS-Store | `spritzmap_db` (bestehender Store wird wiederverwendet, `STORE_NAME` überschreibt den Namen) |
| SQL-View-Layer | `area_summary` aus [`area_summary.sql`](area_summary.sql), Viewparams `city_id`, `drink_id` (nur Ziffern erlaubt) |
| Stil | `spritz_index_style` aus [`lor_spritz_index.sld`](lor_spritz_index.sld) |

Nach Änderungen an `area_summary.sql` oder am SLD das Skript einfach erneut ausführen.

## Datenmodell dahinter

- `areas` – Teilgebiete je Stadt (`city_id`, `key`, `name`, `geom` MultiPolygon EPSG:4326).
  Quelle: automatisch aus OSM (`boundary=administrative`, `admin_level` 9/10) oder per GeoJSON-Upload im
  Admin-Bereich **Städte** (Upload hat Vorrang, z. B. Berliner LOR).
- `locations.area_id` – vorberechnete Gebietszuordnung (Punkt-in-Polygon), aktualisiert bei jedem OSM-Sync
  und Gebietsimport. Der View braucht daher keinen räumlichen Join.

## Spritz-Index-Formel

```
price_score      = ln(max_price / avg_price) / ln(max_price / min_price)   -- 0..1
intensity_factor = avg_color_value / 128                                    -- ~0..2
spritz_index     = price_score × intensity_factor × 100                    -- 0..100
```

- `max_price` / `min_price` werden **pro Stadt und Drink** über alle Gebiete berechnet → Städte mit
  unterschiedlichem Preisniveau werden jeweils in sich normiert
- Günstigstes Gebiet bekommt `price_score ≈ 1`, teuerstes `≈ 0`
- Intensitätswert > 128 hebt den Score, < 128 senkt ihn
- Logarithmische Skala: Unterschied 5 € → 6 € zählt stärker als 9 € → 10 €

Die `fill-opacity` im SLD: `0.08 + (spritz_index / 100) × 0.72`; `spritz_index IS NULL` → transparent.
Die Füllfarbe (`drink_color`) kommt aus dem SQL-View und passt sich dem gewählten Drink an.

## Altlast

Der frühere Berlin-Layer `spritzmap:lor_index_berlin` (SQL auf `public.lor`) wird nicht mehr verwendet und
kann gelöscht werden, sobald `area_summary` läuft. `public.lor` wurde bei der Migration nach `areas`
übernommen und kann danach ebenfalls entfernt werden.
