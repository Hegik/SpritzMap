# GeoServer Setup

## LOR-Layer einrichten

### 1. Workspace anlegen
- Name: `spritzmap`, Namespace URI: `http://spritzmap`

### 2. PostGIS Store anlegen
- Host: `db` (Docker) oder Coolify-DB-Host
- Port: `5432`
- Database: `spritzmap`
- User/Password: aus `.env`

### 3. SQL View `lor_price_summary` anlegen

Layer → SQL View mit folgendem Query:

```sql
WITH lor_stats AS (
  SELECT
    l.lor_schluessel,
    l.geom,
    AVG(pe.price)        AS avg_price,
    AVG(pe.color_value)  AS avg_color_value,
    COUNT(pe.id)         AS entry_count
  FROM lor_planungsraeume l
  LEFT JOIN locations loc
    ON ST_Within(loc.geom, ST_Transform(l.geom, 4326))
  LEFT JOIN price_entries pe
    ON pe.location_id = loc.id
    AND pe.is_current   = TRUE
    AND pe.unavailable  = FALSE
    AND pe.drink_id     = %drink_id%
  GROUP BY l.lor_schluessel, l.geom
),
global_stats AS (
  SELECT
    MAX(avg_price) AS max_price,
    MIN(avg_price) AS min_price
  FROM lor_stats
  WHERE avg_price IS NOT NULL
),
drink_meta AS (
  SELECT color_hex
  FROM drinks
  WHERE id = %drink_id%
)
SELECT
  s.lor_schluessel,
  s.geom,
  s.avg_price,
  s.entry_count,
  dm.color_hex AS drink_color,
  CASE
    WHEN s.avg_price IS NULL OR g.max_price IS NULL OR g.min_price <= 0
    THEN NULL
    WHEN g.max_price = g.min_price
    -- Only one LOR has data → no relative comparison possible, use neutral index
    THEN 50.0 * (COALESCE(s.avg_color_value, 128) / 128.0)
    ELSE LEAST(100.0, GREATEST(0.0,
      (LN(g.max_price / s.avg_price) / LN(g.max_price / g.min_price))
      * (COALESCE(s.avg_color_value, 128) / 128.0)
      * 100.0
    ))
  END AS spritz_index
FROM lor_stats s
CROSS JOIN global_stats g
CROSS JOIN drink_meta dm
```

**Viewparam** im SQL View Formular eintragen:
- Name: `drink_id`, Default: `1`, Validation Regex: `^[0-9]+$`

**Geometry** im SQL View Formular:
- Attribut: `geom`, SRID: `25833` (EPSG:25833)

### 4. Bounding Box berechnen
Nach dem Speichern auf "Compute from data" und "Compute from native bounds" klicken.

### 5. SLD-Style `spritz_index_style` anlegen

Styles → Neu → Format: **SLD** → Inhalt aus `geoserver/lor_spritz_index.sld` einfügen → Speichern.

Die `fill-opacity` wird per OGC-Expression berechnet: `0.08 + (spritz_index / 100) × 0.72`.
- Index 0 → Opacity 0.08 (kaum sichtbar)
- Index 100 → Opacity 0.80 (intensiv)
- `spritz_index IS NULL` → komplett transparent

Die Farbe (`drink_color`) kommt direkt als `#rrggbb`-String aus dem SQL-View — passt sich automatisch an den gewählten Drink an.

Style dem Layer `lor_price_summary` zuweisen.

### 6. Layer in der Karte testen

Im Frontend wird der Layer mit `viewparams=drink_id:X` abgerufen — der Wert kommt aus dem Drink-Filter. Farbe und Index wechseln automatisch beim Filterwechsel.

---

## Spritz-Index Formel

```
price_score      = ln(max_price / avg_price) / ln(max_price / min_price)   -- 0..1
intensity_factor = avg_color_value / 128                                    -- ~0..2
spritz_index     = price_score × intensity_factor × 100                    -- 0..100
```

- `max_price` / `min_price` werden **pro Drink über alle LORs** berechnet → fair normiert
- Günstigster Bezirk bekommt `price_score ≈ 1`, teuerster `≈ 0`
- Intensitätswert > 128 hebt den Score, < 128 senkt ihn
- Logarithmische Skala: Unterschied 5 € → 6 € zählt stärker als 9 € → 10 €
