-- Carga idempotente de Georef en app.geo_areas.
-- Entrada: tabla temporal tmp_georef(level text, code text, parent_code text, name text, lat numeric, lng numeric)
-- ya cargada por `seed-base` desde provincias.csv, departamentos.csv y localidades.csv.
-- Reglas:
--   * La clave es (país, nivel, código oficial). Reejecutar no duplica; actualiza nombre, centroide y padre.
--   * Filas viejas sin código (seed anterior: provincias y departamentos de Cuyo) se "adoptan" por padre + nombre,
--     así conservan su id y no se rompen las publicaciones que ya las referencian.
--   * No borra nada. Lo que Georef deja de publicar queda como está (se revisa a mano).
INSERT INTO app.geo_areas (level, name, country_code)
SELECT 'country', 'Argentina', 'AR' WHERE NOT EXISTS (SELECT 1 FROM app.geo_areas WHERE level = 'country' AND country_code = 'AR');

-- ---- provincias
UPDATE app.geo_areas g SET official_code = t.code
  FROM tmp_georef t, app.geo_areas ar
 WHERE t.level = 'province' AND ar.level = 'country' AND ar.country_code = 'AR'
   AND g.parent_id = ar.id AND g.level = 'province' AND g.official_code IS NULL
   AND lower(app.f_unaccent(g.name)) = lower(app.f_unaccent(t.name))
   AND NOT EXISTS (SELECT 1 FROM app.geo_areas x WHERE x.level = 'province' AND x.country_code = 'AR' AND x.official_code = t.code);
UPDATE app.geo_areas g SET name = t.name, centroid_lat = t.lat, centroid_lng = t.lng
  FROM tmp_georef t
 WHERE t.level = 'province' AND g.level = 'province' AND g.country_code = 'AR' AND g.official_code = t.code
   AND (g.name, g.centroid_lat, g.centroid_lng) IS DISTINCT FROM (t.name, t.lat, t.lng);
INSERT INTO app.geo_areas (parent_id, level, name, official_code, centroid_lat, centroid_lng)
SELECT ar.id, 'province', t.name, t.code, t.lat, t.lng
  FROM tmp_georef t, app.geo_areas ar
 WHERE t.level = 'province' AND ar.level = 'country' AND ar.country_code = 'AR'
   AND NOT EXISTS (SELECT 1 FROM app.geo_areas x WHERE x.level = 'province' AND x.country_code = 'AR' AND x.official_code = t.code);

-- ---- departamentos (partidos en Buenos Aires, comunas en CABA)
UPDATE app.geo_areas g SET official_code = t.code
  FROM tmp_georef t JOIN app.geo_areas p ON p.level = 'province' AND p.country_code = 'AR' AND p.official_code = t.parent_code
 WHERE t.level = 'department' AND g.parent_id = p.id AND g.level = 'department' AND g.official_code IS NULL
   AND lower(app.f_unaccent(g.name)) = lower(app.f_unaccent(t.name))
   AND NOT EXISTS (SELECT 1 FROM app.geo_areas x WHERE x.level = 'department' AND x.country_code = 'AR' AND x.official_code = t.code);
UPDATE app.geo_areas g SET name = t.name, centroid_lat = t.lat, centroid_lng = t.lng, parent_id = p.id
  FROM tmp_georef t JOIN app.geo_areas p ON p.level = 'province' AND p.country_code = 'AR' AND p.official_code = t.parent_code
 WHERE t.level = 'department' AND g.level = 'department' AND g.country_code = 'AR' AND g.official_code = t.code
   AND (g.name, g.centroid_lat, g.centroid_lng, g.parent_id) IS DISTINCT FROM (t.name, t.lat, t.lng, p.id);
INSERT INTO app.geo_areas (parent_id, level, name, official_code, centroid_lat, centroid_lng)
SELECT p.id, 'department', t.name, t.code, t.lat, t.lng
  FROM tmp_georef t JOIN app.geo_areas p ON p.level = 'province' AND p.country_code = 'AR' AND p.official_code = t.parent_code
 WHERE t.level = 'department'
   AND NOT EXISTS (SELECT 1 FROM app.geo_areas x WHERE x.level = 'department' AND x.country_code = 'AR' AND x.official_code = t.code);

-- ---- localidades (siempre cuelgan de un departamento: la vista pública arma "Localidad, Provincia" con esa cadena)
UPDATE app.geo_areas g SET name = t.name, centroid_lat = t.lat, centroid_lng = t.lng, parent_id = d.id
  FROM tmp_georef t JOIN app.geo_areas d ON d.level = 'department' AND d.country_code = 'AR' AND d.official_code = t.parent_code
 WHERE t.level = 'locality' AND g.level = 'locality' AND g.country_code = 'AR' AND g.official_code = t.code
   AND (g.name, g.centroid_lat, g.centroid_lng, g.parent_id) IS DISTINCT FROM (t.name, t.lat, t.lng, d.id);
INSERT INTO app.geo_areas (parent_id, level, name, official_code, centroid_lat, centroid_lng)
SELECT d.id, 'locality', t.name, t.code, t.lat, t.lng
  FROM tmp_georef t JOIN app.geo_areas d ON d.level = 'department' AND d.country_code = 'AR' AND d.official_code = t.parent_code
 WHERE t.level = 'locality'
   AND NOT EXISTS (SELECT 1 FROM app.geo_areas x WHERE x.level = 'locality' AND x.country_code = 'AR' AND x.official_code = t.code);
