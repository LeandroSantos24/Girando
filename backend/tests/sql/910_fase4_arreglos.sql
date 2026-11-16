-- =====================================================================
-- Tests SQL de los arreglos de la fase 4 (migración base completa aplicada).
-- Datos FICTICIOS dentro de una transacción que termina en ROLLBACK.
--   A. RLS de messages sin recursión: participante ve, tercero no, moderación
--      solo si hay un mensaje reportado.
--   B. Verificación presencial de una casa de repuestos: al aprobarse, la
--      cuenta comercial pasa a 'verified'.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE SCHEMA t;
CREATE FUNCTION t.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS NOT TRUE THEN RAISE EXCEPTION 'FALLÓ: %', label; END IF; RAISE NOTICE 'ok: %', label; END $$;
CREATE FUNCTION t.as_user(u uuid) RETURNS void LANGUAGE sql AS $$ SELECT set_config('app.user_id', u::text, true) $$;
CREATE TABLE t.ids (k text PRIMARY KEY, id uuid);
CREATE FUNCTION t.id(k text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT id FROM t.ids WHERE ids.k = $1 $$;
GRANT USAGE ON SCHEMA t TO girando_app, girando_worker;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO girando_app, girando_worker;
GRANT ALL ON t.ids TO girando_app, girando_worker;

SET ROLE girando_worker;
INSERT INTO t.ids SELECT k, gen_random_uuid() FROM unnest(ARRAY['bea','sam','oto','mia','rep']) k;
INSERT INTO app.users (id, email, status, email_verified_at)
SELECT id, k || '@test.invalid', 'active', now() FROM t.ids;
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
INSERT INTO app.report_reasons (code, label, applies_to) VALUES ('spam_msg', 'Spam', ARRAY['message']::app.report_target[]);
INSERT INTO app.verification_products (code, name, description, kind, subject, public_disclaimer, status)
VALUES ('parts_store', 'Casa de repuestos verificada', 'Visita presencial', 'onsite_visit', 'agency', 'Certifica que el local existe.', 'active');
RESET ROLE;

-- ------------------------------------------------------------------ A. mensajes
SET ROLE girando_app;
SELECT t.as_user(t.id('sam'));
INSERT INTO app.vehicles (owner_user_id, version_id, engine_id, year, color) VALUES (t.id('sam'), t.id('ver'), t.id('eng'), 2012, 'Gris') RETURNING id \gset v_
INSERT INTO app.listings (owner_user_id, created_by, vehicle_id, geo_area_id, title, price_amount, km)
VALUES (t.id('sam'), t.id('sam'), :'v_id', t.id('gc'), 'Gol Trend de prueba', 7900000, 125000) RETURNING id \gset l_
UPDATE app.listings SET status = 'pending' WHERE id = :'l_id';
SELECT t.as_user(t.id('mia'));
UPDATE app.listings SET status = 'published' WHERE id = :'l_id';
RESET ROLE;

SET ROLE girando_app;
SELECT t.as_user(t.id('bea'));
INSERT INTO app.conversations (listing_id, buyer_user_id, seller_user_id) VALUES (:'l_id', t.id('bea'), t.id('sam')) RETURNING id \gset c_
INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body) VALUES (:'c_id', t.id('bea'), 'buyer', 'Hola, ¿sigue disponible?') RETURNING id \gset m_
SELECT t.ok((SELECT count(*) = 1 FROM app.messages WHERE conversation_id = :'c_id'), 'la compradora lee su conversación (sin recursión RLS)');
SELECT t.ok((SELECT count(*) = 1 FROM app.messages m WHERE m.read_at IS NULL AND m.sender_user_id <> app.me()
                AND EXISTS (SELECT 1 FROM app.conversations c WHERE c.id = m.conversation_id)) IS NOT NULL, 'subconsulta de no leídos sobre messages no recursa');
SELECT t.ok((SELECT count(*) = 0 FROM app.listings WHERE id = :'l_id'), 'la compradora no lee app.listings ajeno (RLS)');
SELECT t.ok((SELECT subject_title = 'Gol Trend de prueba' AND vertical = 'vehicle' AND subject_code IS NOT NULL AND subject_status = 'published'
               FROM app.conversation_subject(:'c_id')), 'pero sí ve el asunto de su conversación (conversation_subject)');
SELECT t.as_user(t.id('sam'));
SELECT t.ok((SELECT count(*) = 1 FROM app.messages WHERE conversation_id = :'c_id'), 'el vendedor lee la conversación');
SELECT t.as_user(t.id('oto'));
SELECT t.ok((SELECT count(*) = 0 FROM app.conversation_subject(:'c_id')), 'un tercero no obtiene el asunto de una conversación ajena');
SELECT t.as_user(t.id('oto'));
SELECT t.ok((SELECT count(*) = 0 FROM app.messages), 'un tercero no ve mensajes ajenos');
SELECT t.as_user(t.id('mia'));
SELECT t.ok((SELECT count(*) = 0 FROM app.messages), 'moderación NO ve mensajes de una conversación sin reporte');
SELECT t.as_user(t.id('sam'));
INSERT INTO app.reports (reporter_user_id, target, message_id, reason_id)
SELECT t.id('sam'), 'message', :'m_id', id FROM app.report_reasons WHERE code = 'spam_msg';
SELECT t.as_user(t.id('mia'));
SELECT t.ok((SELECT count(*) = 1 FROM app.messages WHERE conversation_id = :'c_id'), 'moderación ve la conversación recién cuando hay un mensaje reportado');
SELECT t.as_user(t.id('oto'));
SELECT t.ok((SELECT count(*) = 0 FROM app.messages), 'el reporte no abre la conversación a terceros');
RESET ROLE;

-- ------------------------------------------------------------------ B. repuestos
SET ROLE girando_worker;
INSERT INTO app.agencies (slug, kind, legal_name, trade_name, cuit, geo_area_id, created_by)
VALUES ('repuestos-test', 'parts_store', 'Repuestos Test SRL', 'Repuestos Test', '30123456781', t.id('gc'), t.id('rep')) RETURNING id \gset a_
INSERT INTO app.verifications (product_id, subject_agency_id, requested_by)
SELECT id, :'a_id', t.id('rep') FROM app.verification_products WHERE code = 'parts_store' RETURNING id \gset ver_
RESET ROLE;
SET ROLE girando_app;
SELECT t.as_user(t.id('mia'));
UPDATE app.verifications SET status = 'review' WHERE id = :'ver_id';
SELECT t.ok((SELECT status = 'review' FROM app.agencies WHERE id = :'a_id'), 'repuestos: en revisión se refleja en la cuenta');
-- sin suscripción paga vigente no se aprueba, ni siquiera desde moderación
SAVEPOINT sin_pago;
DO $$ BEGIN
  UPDATE app.verifications SET status = 'approved' WHERE subject_agency_id = (SELECT id FROM app.agencies WHERE slug = 'repuestos-test');
  RAISE EXCEPTION 'FALLÓ: se aprobó una casa de repuestos sin pago';
EXCEPTION WHEN OTHERS THEN
  IF SQLERRM NOT LIKE '%PAGO_REQUERIDO_ANTES_DE_VERIFICAR%' THEN RAISE; END IF;
  RAISE NOTICE 'ok (error esperado): PAGO_REQUERIDO_ANTES_DE_VERIFICAR';
END $$;
ROLLBACK TO SAVEPOINT sin_pago;
RESET ROLE;
SET ROLE girando_worker;
INSERT INTO app.plans (code, name, audience, price_amount, billing_period, max_active_listings)
VALUES ('repuestos', 'Repuestos', 'agency', 4000, 'month', 0);
INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, status, price_amount, currency, billing_period,
                               started_at, current_period_start, current_period_end)
SELECT id, :'a_id', t.id('rep'), 'manual', 'active', 4000, 'ARS', 'month', now(), now(), now() + interval '1 month' FROM app.plans WHERE code = 'repuestos';
RESET ROLE;
SET ROLE girando_app;
SELECT t.as_user(t.id('mia'));
UPDATE app.verifications SET status = 'approved' WHERE id = :'ver_id';
SELECT t.ok((SELECT status = 'verified' AND verified_at IS NOT NULL FROM app.agencies WHERE id = :'a_id'), 'repuestos: verificación presencial aprobada deja la cuenta verified');
UPDATE app.verifications SET status = 'revoked', decision_reason = 'El local cerró' WHERE id = :'ver_id';
SELECT t.ok((SELECT status = 'revoked' AND verified_at IS NULL FROM app.agencies WHERE id = :'a_id'), 'repuestos: revocar quita el sello');
RESET ROLE;

-- ------------------------------------------------------------------ C. vistas públicas como visitante sin sesión
-- Las funciones de app están revocadas a PUBLIC: si una vista de api_public usa una sin EXECUTE para girando_anon,
-- el listado público falla con "permission denied for function …" (pasó con api_public.posts y subscription_grants).
SET ROLE girando_anon;
DO $$
DECLARE v text; n bigint; total int := 0;
BEGIN
  FOR v IN SELECT viewname FROM pg_views WHERE schemaname = 'api_public' ORDER BY 1 LOOP
    EXECUTE format('SELECT count(*) FROM api_public.%I', v) INTO n;
    total := total + 1;
  END LOOP;
  IF total < 19 THEN RAISE EXCEPTION 'FALLÓ: se esperaban al menos 19 vistas públicas y hay %', total; END IF;
  RAISE NOTICE 'ok: el visitante sin sesión puede leer las % vistas de api_public', total;
END $$;
RESET ROLE;
ROLLBACK;
