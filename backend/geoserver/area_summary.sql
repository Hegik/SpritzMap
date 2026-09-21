-- GeoServer-SQL-View "area_summary": Spritz-Index je Gebiet für EINE Stadt und EIN Getränk.
-- Viewparams: city_id, drink_id  (z. B. viewparams=city_id:1;drink_id:1)
-- Gebietszuordnung ist in locations.area_id vorberechnet → kein räumlicher Join nötig.
-- min/max-Preis werden pro Stadt normiert, damit Städte mit unterschiedlichem Preisniveau vergleichbar eingefärbt werden.
WITH area_stats AS (
  SELECT
    a.id                AS area_id,
    a.key               AS area_key,
    a.name              AS area_name,
    a.geom,
    AVG(pe.price)       AS avg_price,
    AVG(pe.color_value) AS avg_color_value,
    COUNT(pe.id)        AS entry_count
  FROM areas a
  LEFT JOIN locations loc
    ON loc.area_id = a.id
    AND loc.is_active = TRUE
  LEFT JOIN price_entries pe
    ON pe.location_id = loc.id
    AND pe.is_current   = TRUE
    AND pe.unavailable  = FALSE
    AND pe.drink_id     = %drink_id%
  WHERE a.city_id = %city_id%
  GROUP BY a.id, a.key, a.name, a.geom
),
city_stats AS (
  SELECT MAX(avg_price) AS max_price, MIN(avg_price) AS min_price
  FROM area_stats
  WHERE avg_price IS NOT NULL
),
drink_meta AS (
  SELECT color_hex FROM drinks WHERE id = %drink_id%
)
SELECT
  s.area_id,
  s.area_key,
  s.area_name,
  s.geom,
  s.avg_price,
  s.entry_count,
  dm.color_hex AS drink_color,
  CASE
    WHEN s.avg_price IS NULL OR g.max_price IS NULL OR g.min_price <= 0
    THEN NULL
    WHEN g.max_price = g.min_price
    -- Nur ein Gebiet mit Daten → kein relativer Vergleich möglich, neutraler Index
    THEN 50.0 * (COALESCE(s.avg_color_value, 128) / 128.0)
    ELSE LEAST(100.0, GREATEST(0.0,
      (LN(g.max_price / s.avg_price) / LN(g.max_price / g.min_price))
      * (COALESCE(s.avg_color_value, 128) / 128.0)
      * 100.0
    ))
  END AS spritz_index
FROM area_stats s
CROSS JOIN city_stats g
LEFT JOIN drink_meta dm ON TRUE
