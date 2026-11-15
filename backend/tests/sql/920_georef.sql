-- =====================================================================
-- Test SQL del cargador de Georef (app/seeds/georef/cargar.sql).
-- Usa una MUESTRA MÍNIMA DE PRUEBA dentro de una transacción con ROLLBACK:
-- no es el dataset (ese se descarga con scripts/georef_descargar.py).
-- Se corre desde backend/:  psql -f tests/sql/920_georef.sql
-- =====================================================================
\set QUIET on
BEGIN;
CREATE SCHEMA t;
CREATE FUNCTION t.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS NOT TRUE THEN RAISE EXCEPTION 'FALLÓ: %', label; END IF; RAISE NOTICE 'ok: %', label; END $$;
GRANT USAGE ON SCHEMA t TO girando_worker; GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO girando_worker;
SET ROLE girando_worker;

-- estado previo: seed viejo, sin códigos oficiales
WITH ar AS (INSERT INTO app.geo_areas (level, name) VALUES ('country', 'Argentina') RETURNING id),
     mza AS (INSERT INTO app.geo_areas (parent_id, level, name) SELECT id, 'province', 'Mendoza' FROM ar RETURNING id)
INSERT INTO app.geo_areas (parent_id, level, name) SELECT id, 'department', 'Godoy Cruz' FROM mza;
SELECT id AS gc_id FROM app.geo_areas WHERE name = 'Godoy Cruz' \gset

CREATE TEMP TABLE tmp_georef (level text, code text, parent_code text, name text, lat numeric, lng numeric);
INSERT INTO tmp_georef VALUES
  ('province',   'P1',  NULL, 'Mendoza',     -34.63, -68.58),
  ('province',   'P2',  NULL, 'Córdoba',     -32.14, -63.80),
  ('department', 'D11', 'P1', 'Godoy Cruz',  -32.93, -68.85),
  ('department', 'D12', 'P1', 'Capital',     -32.88, -68.84),
  ('department', 'D21', 'P2', 'Capital',     -31.41, -64.18),
  ('locality',   'L111','D11','Godoy Cruz',  -32.92, -68.84),
  ('locality',   'L211','D21','Córdoba',     -31.41, -64.18),
  ('locality',   'L212','D21','Córdoba',     -31.50, -64.20);   -- mismo nombre, otro código: son dos localidades
\i app/seeds/georef/cargar.sql
SELECT t.ok((SELECT count(*) = 1 FROM app.geo_areas WHERE level = 'country'), 'no duplica el país');
SELECT t.ok((SELECT count(*) = 2 FROM app.geo_areas WHERE level = 'province'), 'provincias: adopta Mendoza y agrega Córdoba');
SELECT t.ok((SELECT id = :'gc_id' AND official_code = 'D11' AND centroid_lat = -32.93 FROM app.geo_areas WHERE level = 'department' AND name = 'Godoy Cruz'),
            'el departamento viejo conserva su id y recibe código y centroide');
SELECT t.ok((SELECT count(*) = 2 FROM app.geo_areas WHERE level = 'department' AND name = 'Capital'), 'mismo nombre en dos provincias: dos departamentos');
SELECT t.ok((SELECT count(*) = 3 FROM app.geo_areas WHERE level = 'locality'), 'localidades cargadas (homónimas incluidas)');
SELECT t.ok((SELECT p.name = 'Mendoza' FROM app.geo_areas l JOIN app.geo_areas d ON d.id = l.parent_id JOIN app.geo_areas p ON p.id = d.parent_id
              WHERE l.official_code = 'L111'), 'cadena localidad → departamento → provincia');
SELECT count(*) AS n1 FROM app.geo_areas \gset
-- segunda carga con un cambio de nombre: idempotente + actualiza
UPDATE tmp_georef SET name = 'Ciudad de Córdoba' WHERE code = 'L211';
\i app/seeds/georef/cargar.sql
SELECT t.ok((SELECT count(*) = :n1 FROM app.geo_areas), 'recargar no duplica nada');
SELECT t.ok((SELECT name = 'Ciudad de Córdoba' FROM app.geo_areas WHERE official_code = 'L211'), 'recargar actualiza el nombre por código');
RESET ROLE;
ROLLBACK;
