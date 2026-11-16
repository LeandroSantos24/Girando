-- =====================================================================
-- Tests SQL de la migración 0002 (contacto por WhatsApp, favoritos, precio vs mercado).
-- Datos FICTICIOS dentro de una transacción que termina en ROLLBACK.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE SCHEMA t;
CREATE FUNCTION t.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS NOT TRUE THEN RAISE EXCEPTION 'FALLÓ: %', label; END IF; RAISE NOTICE 'ok: %', label; END $$;
CREATE FUNCTION t.as_user(u uuid) RETURNS void LANGUAGE sql AS $$ SELECT set_config('app.user_id', u::text, true) $$;
CREATE FUNCTION t.fails(q text, expected text) RETURNS boolean LANGUAGE plpgsql AS $$
BEGIN EXECUTE q; RETURN false; EXCEPTION WHEN OTHERS THEN RETURN SQLERRM LIKE '%' || expected || '%'; END $$;
CREATE TABLE t.ids (k text PRIMARY KEY, id uuid);
CREATE FUNCTION t.id(k text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT id FROM t.ids WHERE ids.k = $1 $$;
GRANT USAGE ON SCHEMA t TO girando_app, girando_worker, girando_anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO girando_app, girando_worker, girando_anon;
GRANT ALL ON t.ids TO girando_app, girando_worker;

SET ROLE girando_worker;
INSERT INTO t.ids SELECT k, gen_random_uuid() FROM unnest(ARRAY['sam','bea','mia','u1','u2','u3','u4','u5','u6']) k;
INSERT INTO app.users (id, email, status, email_verified_at) SELECT id, k || '@test.invalid', 'active', now() FROM t.ids;
INSERT INTO app.user_profiles (user_id, display_name) SELECT id, initcap(k) FROM t.ids;
INSERT INTO app.staff_roles (user_id, role) VALUES (t.id('mia'), 'moderator');
WITH ar AS (INSERT INTO app.geo_areas (level, name) VALUES ('country', 'Argentina') RETURNING id),
     mza AS (INSERT INTO app.geo_areas (parent_id, level, name) SELECT id, 'province', 'Mendoza' FROM ar RETURNING id)
INSERT INTO app.geo_areas (parent_id, level, name) SELECT id, 'department', 'Godoy Cruz' FROM mza;
INSERT INTO t.ids SELECT 'gc', id FROM app.geo_areas WHERE name = 'Godoy Cruz';
WITH b AS (INSERT INTO app.vehicle_brands (name, slug) VALUES ('Volkswagen', 'volkswagen') RETURNING id),
     m AS (INSERT INTO app.vehicle_models (brand_id, name, slug, vehicle_type, default_body_type) SELECT id, 'Gol', 'gol', 'car', 'hatchback' FROM b RETURNING id),
     g AS (INSERT INTO app.vehicle_generations (model_id, name, year_from, year_to) SELECT id, 'G4', 2006, 2014 FROM m RETURNING id),
     v AS (INSERT INTO app.vehicle_versions (generation_id, name, doors, transmission, traction) SELECT id, 'Trend', 5, 'manual', 'front' FROM g RETURNING id),
     e AS (INSERT INTO app.vehicle_engines (name, fuel, displacement_cc) VALUES ('1.6 Nafta', 'gasoline', 1598) RETURNING id)
INSERT INTO app.vehicle_version_engines (version_id, engine_id, is_default) SELECT v.id, e.id, true FROM v, e;
INSERT INTO t.ids SELECT 'ver', version_id FROM app.vehicle_version_engines;
INSERT INTO t.ids SELECT 'eng', engine_id FROM app.vehicle_version_engines;
INSERT INTO app.plans (code, name, audience, price_amount, billing_period, max_active_listings, is_default_for_audience)
VALUES ('particular', 'Particular', 'particular', 0, 'none', 1, true);
INSERT INTO app.app_settings (key, value, description) VALUES ('listings.duration_days', '60', 'Duración');
RESET ROLE;

-- Alta de una publicación de un usuario (devuelve el id). Con p_wa NULL queda sin WhatsApp.
CREATE FUNCTION t.listing(p_user text, p_price numeric, p_wa text, p_year int DEFAULT 2012) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE v uuid; l uuid;
BEGIN
  PERFORM t.as_user(t.id(p_user));
  INSERT INTO app.vehicles (owner_user_id, version_id, engine_id, year, color) VALUES (t.id(p_user), t.id('ver'), t.id('eng'), p_year, 'Gris') RETURNING id INTO v;
  INSERT INTO app.listings (owner_user_id, created_by, vehicle_id, geo_area_id, title, price_amount, km)
  VALUES (t.id(p_user), t.id(p_user), v, t.id('gc'), 'Gol Trend de ' || p_user, p_price, 100000) RETURNING id INTO l;
  IF p_wa IS NOT NULL THEN UPDATE app.listing_contacts SET whatsapp_e164 = p_wa WHERE listing_id = l; END IF;
  RETURN l;
END $$;
CREATE FUNCTION t.publish(p_user text, l uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM t.as_user(t.id(p_user)); UPDATE app.listings SET status = 'pending' WHERE id = l;
  PERFORM t.as_user(t.id('mia'));  UPDATE app.listings SET status = 'published' WHERE id = l;
END $$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO girando_app, girando_worker, girando_anon;

-- ------------------------------------------------------------------ A. WhatsApp obligatorio
SET ROLE girando_app;
SELECT t.listing('sam', 8000000, NULL) AS id \gset l_
SELECT t.as_user(t.id('sam'));
SELECT t.ok(t.fails(format('UPDATE app.listings SET status = ''pending'' WHERE id = %L', :'l_id'), 'WHATSAPP_OBLIGATORIO'),
            'A1 sin WhatsApp no se puede enviar a revisión');
SELECT t.ok(t.fails(format('UPDATE app.listing_contacts SET whatsapp_e164 = ''2615550101'' WHERE listing_id = %L', :'l_id'), 'lc_wa'),
            'A2 el WhatsApp tiene que estar en formato internacional');
UPDATE app.listing_contacts SET whatsapp_e164 = '+5492615550101' WHERE listing_id = :'l_id';
SELECT t.publish('sam', :'l_id');
SELECT t.ok((SELECT status = 'published' FROM app.listings WHERE id = :'l_id'), 'A3 con WhatsApp se publica');
SELECT public_code AS code FROM app.listings WHERE id = :'l_id' \gset l_
RESET ROLE;

-- ------------------------------------------------------------------ B. el número no se expone
SET ROLE girando_anon;
SELECT t.ok(t.fails(format('SELECT * FROM app.whatsapp_target(%L)', :'l_code'), 'permission denied'), 'B1 un visitante no puede resolver el número');
SELECT t.ok(NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'api_public' AND table_name IN ('listings', 'posts')
                          AND column_name ILIKE '%whatsapp%'), 'B2 las vistas públicas no tienen columnas de WhatsApp');
RESET ROLE;
SET ROLE girando_app;
SELECT t.as_user(t.id('bea'));
SELECT t.ok(t.fails(format('SELECT * FROM app.whatsapp_target(%L)', :'l_code'), 'permission denied'), 'B3 un usuario con sesión tampoco');
RESET ROLE;
SET ROLE girando_worker;
SELECT t.ok((SELECT whatsapp = '+5492615550101' AND kind = 'listing' AND title LIKE 'Volkswagen Gol 2012' FROM app.whatsapp_target(:'l_code')),
            'B4 el sistema resuelve número y título para el mensaje precargado');
RESET ROLE;
SET ROLE girando_app;
SELECT t.as_user(t.id('sam'));
UPDATE app.listings SET status = 'paused' WHERE id = :'l_id';
RESET ROLE;
SET ROLE girando_worker;
SELECT t.ok(NOT EXISTS (SELECT 1 FROM app.whatsapp_target(:'l_code')), 'B5 una publicación pausada no entrega el número');
RESET ROLE;

-- ------------------------------------------------------------------ C. favoritos: precio al guardar y aviso de baja
SET ROLE girando_app;
SELECT t.listing('u1', 9000000, '+5492615550102') AS id \gset f_
SELECT t.publish('u1', :'f_id');
SELECT t.as_user(t.id('bea'));
INSERT INTO app.favorites (user_id, listing_id, price_at_save) VALUES (t.id('bea'), :'f_id', 1);
SELECT t.ok((SELECT price_at_save = 9000000 AND currency_at_save = 'ARS' FROM app.favorites WHERE listing_id = :'f_id'),
            'C1 el precio guardado lo pone la base, no el cliente');
RESET ROLE;
SET ROLE girando_worker;
INSERT INTO app.notification_types (code, category, description) VALUES ('favorite.price_drop', 'favorites', 'Bajó de precio');
RESET ROLE;
SET ROLE girando_app;
SELECT t.as_user(t.id('u1'));
UPDATE app.listings SET price_amount = 8500000 WHERE id = :'f_id';
RESET ROLE;
SET ROLE girando_worker;
SELECT t.ok((SELECT count(*) = 1 FROM app.notifications WHERE user_id = t.id('bea') AND type_code = 'favorite.price_drop'),
            'C2 quien guardó la publicación recibe el aviso de baja de precio');
RESET ROLE;

-- ------------------------------------------------------------------ D. precio vs mercado
SET ROLE girando_app;
SELECT t.ok((SELECT NOT sufficient AND avg_price_ars IS NULL AND "position" IS NULL AND sample = 0 FROM app.market_price(:'f_id')),
            'D1 sin muestra suficiente no hay promedio ni posición');
SELECT t.publish('u2', t.listing('u2', 10000000, '+5492615550103'));
SELECT t.publish('u3', t.listing('u3', 10000000, '+5492615550104', 2013));
SELECT t.publish('u4', t.listing('u4', 10000000, '+5492615550105', 2011));
SELECT t.publish('u5', t.listing('u5', 10000000, '+5492615550106'));
SELECT t.ok((SELECT NOT sufficient AND sample = 4 FROM app.market_price(:'f_id')), 'D2 con 4 comparables sigue sin mostrarse (mínimo 5)');
SELECT t.publish('u6', t.listing('u6', 10000000, '+5492615550107'));
SELECT t.ok((SELECT sufficient AND sample = 5 AND avg_price_ars = 10000000 AND ratio_pct = 85.0 AND "position" = 'below' FROM app.market_price(:'f_id')),
            'D3 con 5 comparables: 8,5 M contra 10 M promedio = por debajo del mercado');
RESET ROLE;

ROLLBACK;
