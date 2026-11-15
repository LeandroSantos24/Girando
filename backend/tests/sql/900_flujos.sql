-- =====================================================================
-- Tests de flujos sobre la propuesta v0. Datos FICTICIOS de prueba,
-- dentro de una transacción que termina en ROLLBACK (no es un seed).
-- Cada bloque cambia de rol y de usuario igual que lo haría el backend.
-- =====================================================================
\set QUIET on
BEGIN;
CREATE SCHEMA t;
CREATE FUNCTION t.expect_error(q text, expected text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE q;
  RAISE EXCEPTION 'FALLÓ: se esperaba error "%" y no hubo error en: %', expected, q;
EXCEPTION WHEN OTHERS THEN
  IF SQLERRM LIKE 'FALLÓ:%' THEN RAISE; END IF;
  IF position(expected IN SQLERRM) = 0 AND SQLSTATE <> expected THEN
    RAISE EXCEPTION 'FALLÓ: se esperaba "%" pero vino [%] %', expected, SQLSTATE, SQLERRM;
  END IF;
  RAISE NOTICE 'ok (error esperado): %', expected;
END $$;
CREATE FUNCTION t.ok(cond boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN IF cond IS NOT TRUE THEN RAISE EXCEPTION 'FALLÓ: %', label; END IF; RAISE NOTICE 'ok: %', label; END $$;
CREATE FUNCTION t.as_user(u uuid) RETURNS void LANGUAGE sql AS $$ SELECT set_config('app.user_id', u::text, true) $$;
GRANT USAGE ON SCHEMA t TO girando_app, girando_worker, girando_anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA t TO girando_app, girando_worker, girando_anon;
CREATE TABLE t.ids (k text PRIMARY KEY, id uuid);
GRANT ALL ON t.ids TO girando_app, girando_worker, girando_anon;
CREATE FUNCTION t.id(k text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT id FROM t.ids WHERE ids.k = $1 $$;

-- ------------------------------------------------------------------ seed de prueba (worker)
SET ROLE girando_worker;
INSERT INTO t.ids VALUES ('juan', gen_random_uuid()), ('ana', gen_random_uuid()), ('sofia', gen_random_uuid()), ('fin', gen_random_uuid());
INSERT INTO app.users (id, email, status, email_verified_at) VALUES
  (t.id('juan'), 'juan@test.invalid', 'active', now()), (t.id('ana'), 'ana@test.invalid', 'active', now()),
  (t.id('sofia'), 'sofia@test.invalid', 'active', now()), (t.id('fin'), 'fin@test.invalid', 'active', now());
INSERT INTO app.user_profiles (user_id, display_name) VALUES (t.id('juan'), 'Juan M.'), (t.id('ana'), 'Ana P.');
INSERT INTO app.staff_roles (user_id, role) VALUES (t.id('sofia'), 'moderator'), (t.id('fin'), 'finance');

WITH ar AS (INSERT INTO app.geo_areas (level, name) VALUES ('country', 'Argentina') RETURNING id),
     mza AS (INSERT INTO app.geo_areas (parent_id, level, name) SELECT id, 'province', 'Mendoza' FROM ar RETURNING id)
INSERT INTO app.geo_areas (parent_id, level, name, centroid_lat, centroid_lng) SELECT id, 'department', 'Godoy Cruz', -32.93, -68.85 FROM mza;
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
VALUES ('particular', 'Particular', 'particular', 0, 'none', 1, true),
       ('agencia-pro', 'Agencia Profesional', 'agency', 54900, 'month', 30, false);
INSERT INTO app.retention_policies (code, label, category, duration, starts_from, action) VALUES
  ('media_sold', 'Fotos de publicación vendida', 'media', interval '7 days', 'sale', 'delete'),
  ('plate_after_sale', 'Patente del vehículo vendido', 'historical', interval '24 months', 'sale', 'delete');
INSERT INTO app.app_settings (key, value, description) VALUES
  ('listings.duration_days', '60', 'Duración'), ('stats.min_sample_size', '3', 'Muestra mínima');
INSERT INTO app.verification_products (code, name, description, kind, subject, public_disclaimer, status)
VALUES ('agency', 'Agencia verificada', 'Datos fiscales y responsable', 'agency', 'agency', 'Certifica datos de la empresa, no el estado de los vehículos.', 'active');
RESET ROLE;

-- ------------------------------------------------------------------ 1. Particular publica (límite 1)
SET ROLE girando_app;
SELECT t.as_user(t.id('juan'));
INSERT INTO app.vehicles (owner_user_id, version_id, engine_id, year, color) VALUES (t.id('juan'), t.id('ver'), t.id('eng'), 2012, 'Gris') RETURNING id \gset v1_
INSERT INTO app.listings (owner_user_id, created_by, vehicle_id, geo_area_id, title, price_amount, km)
VALUES (t.id('juan'), t.id('juan'), :'v1_id', t.id('gc'), 'Gol Trend impecable', 7900000, 125000) RETURNING id \gset l1_
SELECT t.ok((SELECT count(*) = 1 FROM app.listing_contacts WHERE listing_id = :'l1_id'), 'listing_contacts creado por defecto (sin teléfono visible)');
UPDATE app.listings SET status = 'pending' WHERE id = :'l1_id';
SELECT t.ok((SELECT submitted_at IS NOT NULL FROM app.listings WHERE id = :'l1_id'), 'enviar a revisión setea submitted_at');
SELECT t.expect_error(format($q$UPDATE app.listings SET status = 'published' WHERE id = %L$q$, :'l1_id'), 'TRANSICION_NO_PERMITIDA');
SELECT t.expect_error(format($q$UPDATE app.listings SET reviewed_by = %L WHERE id = %L$q$, t.id('juan'), :'l1_id'), 'CAMPO_NO_EDITABLE');

INSERT INTO app.vehicles (owner_user_id, version_id, engine_id, year) VALUES (t.id('juan'), t.id('ver'), t.id('eng'), 2010) RETURNING id \gset v2_
INSERT INTO app.listings (owner_user_id, created_by, vehicle_id, geo_area_id, title, price_amount, km)
VALUES (t.id('juan'), t.id('juan'), :'v2_id', t.id('gc'), 'Otro Gol', 6000000, 150000) RETURNING id \gset l2_
SELECT t.expect_error(format($q$UPDATE app.listings SET status = 'pending' WHERE id = %L$q$, :'l2_id'), 'LIMITE_ALCANZADO');

-- año fuera del rango de la generación
UPDATE app.vehicles SET year = 2020 WHERE id = :'v2_id';
SELECT t.expect_error(format($q$UPDATE app.listings SET status = 'pending' WHERE id = %L$q$, :'l2_id'), 'ANIO_FUERA_DE_RANGO');

-- fotos: máximo 6, primera = portada
INSERT INTO app.listing_images (listing_id, public_id, secure_url, format, position, width, height, bytes, uploaded_by)
SELECT :'l1_id', 'girando/listings/test/' || n, 'https://res.cloudinary.com/demo/image/upload/v1/x' || n || '.jpg', 'jpg', n, 1600, 1200, 900000, t.id('juan')
FROM generate_series(1, 6) n;
SELECT t.ok((SELECT count(*) = 1 FROM app.listing_images WHERE listing_id = :'l1_id' AND is_cover), 'una sola portada automática');
SELECT t.expect_error(format($q$INSERT INTO app.listing_images (listing_id, public_id, secure_url, format, position, width, height, bytes, uploaded_by)
  VALUES (%L, 'girando/x7', 'https://res.cloudinary.com/demo/x7.jpg', 'jpg', 6, 1600, 1200, 1000, %L)$q$, :'l1_id', t.id('juan')), 'MAXIMO_FOTOS');
SELECT t.expect_error(format($q$INSERT INTO app.listing_images (listing_id, public_id, secure_url, format, position, width, height, bytes, uploaded_by)
  VALUES (%L, 'girando/x8', 'https://res.cloudinary.com/demo/x8.gif', 'gif', 1, 1600, 1200, 1000, %L)$q$, :'l2_id', t.id('juan')), 'lim_format');

-- identificadores sensibles
INSERT INTO app.vehicle_identifiers (vehicle_id, type, value, declared_by) VALUES (:'v1_id', 'plate', 'AB123CD', t.id('juan'));
SELECT t.expect_error(format($q$INSERT INTO app.vehicle_identifiers (vehicle_id, type, value, declared_by) VALUES (%L, 'plate', 'ZZ99', %L)$q$, :'v2_id', t.id('juan')), 'vi_plate_ar');
SELECT t.expect_error(format($q$UPDATE app.vehicle_identifiers SET status = 'verified', verified_at = now() WHERE vehicle_id = %L$q$, :'v1_id'), 'row-level security');

-- ------------------------------------------------------------------ 2. Moderación aprueba
SELECT t.as_user(t.id('sofia'));
SELECT t.expect_error(format($q$UPDATE app.listings SET status = 'rejected' WHERE id = %L$q$, :'l1_id'), 'MOTIVO_OBLIGATORIO');
UPDATE app.listings SET status = 'published' WHERE id = :'l1_id';
SELECT t.ok((SELECT expires_at > now() + interval '59 days' AND reviewed_by = t.id('sofia') FROM app.listings WHERE id = :'l1_id'), 'aprobada: vence en 60 días y registra moderador');
RESET ROLE;

-- ------------------------------------------------------------------ 3. Visitante: solo datos públicos
SET ROLE girando_anon;
SELECT t.ok((SELECT count(*) = 1 FROM api_public.listings), 'visitante ve la publicación aprobada');
SELECT t.ok((SELECT locality = 'Godoy Cruz' AND province = 'Mendoza' AND seller_type = 'particular' FROM api_public.listings), 'ubicación pública aproximada "Godoy Cruz, Mendoza"');
SELECT t.expect_error('SELECT * FROM app.listings', 'permission denied');
SELECT t.expect_error('SELECT * FROM app.vehicle_identifiers', 'permission denied');
SELECT t.ok((SELECT phone IS NULL AND whatsapp IS NULL FROM api_public.listing_contact), 'teléfono no visible salvo que el vendedor lo active');
RESET ROLE;
SELECT t.ok(NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'api_public'
  AND column_name IN ('email_login','dni','dni_encrypted','value','plate','vin','street','street_number','lat','lng','password_hash','owner_user_id','cuit','legal_name')
  AND table_name NOT IN ('agencies','settings')), 'ninguna vista pública expone columnas sensibles');

-- ------------------------------------------------------------------ 4. Comprador: favoritos, chat, anti-spam, privacidad
SET ROLE girando_app;
SELECT t.as_user(t.id('ana'));
SELECT t.ok((SELECT count(*) = 0 FROM app.vehicle_identifiers), 'Ana no ve identificadores de vehículos ajenos');
SELECT t.ok((SELECT count(*) = 0 FROM app.listings), 'Ana no ve filas privadas de publicaciones ajenas');
INSERT INTO app.favorites (user_id, listing_id) VALUES (t.id('ana'), :'l1_id');
INSERT INTO app.conversations (listing_id, buyer_user_id, seller_user_id) VALUES (:'l1_id', t.id('ana'), t.id('ana')) RETURNING id \gset c1_
SELECT t.ok((SELECT seller_user_id = t.id('juan') FROM app.conversations WHERE id = :'c1_id'), 'el vendedor lo fija el sistema, no el cliente');
INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body) VALUES (:'c1_id', t.id('ana'), 'buyer', 'Hola, ¿sigue disponible?');
SELECT t.expect_error(format($q$INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body) VALUES (%L, %L, 'buyer', 'hola, ¿sigue disponible? ')$q$, :'c1_id', t.id('ana')), 'MENSAJE_REPETIDO');
SELECT t.as_user(t.id('juan'));
INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body) VALUES (:'c1_id', t.id('juan'), 'seller', 'Sí, está disponible');
SELECT t.ok((SELECT count(*) = 0 FROM app.favorites), 'el vendedor no ve quién guardó su publicación');
SELECT t.as_user(t.id('ana'));
INSERT INTO app.reviews (reviewer_user_id, conversation_id, rating, comment) VALUES (t.id('ana'), :'c1_id', 5, 'Respondió rápido');
SELECT t.ok((SELECT reviewed_user_id = t.id('juan') FROM app.reviews), 'la reseña apunta a la contraparte correcta');
SELECT t.expect_error(format($q$INSERT INTO app.reviews (reviewer_user_id, conversation_id, rating) VALUES (%L, %L, 1)$q$, t.id('ana'), :'c1_id'), 'rv_once_per_conversation_uq');

-- ------------------------------------------------------------------ 5. Agencia: nadie se autoverifica
SELECT t.as_user(t.id('juan'));
INSERT INTO app.agencies (slug, legal_name, trade_name, cuit, geo_area_id, created_by, status, verified_at)
VALUES ('jm-automotores', 'JM Automotores SRL', 'JM Automotores', '30500010912', t.id('gc'), t.id('juan'), 'verified', now()) RETURNING id \gset a_
SELECT t.ok((SELECT status = 'pending' AND verified_at IS NULL FROM app.agencies WHERE id = :'a_id'), 'una agencia nace pending aunque el cliente mande "verified"');
SELECT t.ok((SELECT role = 'owner' FROM app.agency_members WHERE agency_id = :'a_id' AND user_id = t.id('juan')), 'el creador queda como owner');
SELECT t.expect_error(format($q$UPDATE app.agencies SET status = 'verified' WHERE id = %L$q$, :'a_id'), 'CAMPO_NO_EDITABLE');
SELECT t.expect_error($q$INSERT INTO app.agencies (slug, legal_name, trade_name, cuit, geo_area_id, created_by) VALUES ('x-y', 'X SA', 'X', '30500010913', (SELECT t.id('gc')), (SELECT t.id('juan')))$q$, 'ag_cuit');
INSERT INTO app.verifications (product_id, subject_agency_id, requested_by)
SELECT id, :'a_id', t.id('juan') FROM app.verification_products WHERE code = 'agency' RETURNING id \gset ver_
UPDATE app.verifications SET status = 'approved' WHERE id = :'ver_id';  -- RLS: 0 filas afectadas
SELECT t.ok((SELECT status = 'pending' FROM app.verifications WHERE id = :'ver_id'), 'el solicitante no puede aprobar su propia verificación');
SELECT t.as_user(t.id('sofia'));
UPDATE app.verifications SET status = 'review' WHERE id = :'ver_id';
UPDATE app.verifications SET status = 'approved' WHERE id = :'ver_id';
SELECT t.ok((SELECT status = 'verified' FROM app.agencies WHERE id = :'a_id'), 'aprobar la verificación → agency.status = verified (fuente única)');

-- ------------------------------------------------------------------ 6. Suscripción por transferencia
SELECT t.as_user(t.id('juan'));
SELECT t.expect_error(format($q$INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, status, price_amount, currency, billing_period, started_at, current_period_end)
  SELECT id, %L, %L, 'bank_transfer', 'active', 1, 'ARS', 'month', now(), now() + interval '1 month' FROM app.plans WHERE code = 'agencia-pro'$q$, :'a_id', t.id('juan')), 'LAS_SUSCRIPCIONES_NACEN_PENDIENTES');
INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, price_amount, currency, billing_period)
SELECT id, :'a_id', t.id('juan'), 'bank_transfer', 1, 'ARS', 'month' FROM app.plans WHERE code = 'agencia-pro' RETURNING id, price_amount \gset s_
SELECT t.ok(:s_price_amount = 54900, 'el precio lo toma del plan, no del cliente');
INSERT INTO app.payments (purpose, subscription_id, payer_user_id, agency_id, provider, amount)
VALUES ('subscription', :'s_id', t.id('juan'), :'a_id', 'bank_transfer', 1) RETURNING id, amount, transfer_reference \gset p_
SELECT t.ok(:p_amount = 54900 AND :'p_transfer_reference' LIKE 'GIR-%', 'monto forzado y referencia GIR- generada por el sistema');
UPDATE app.payments SET status = 'submitted' WHERE id = :'p_id';
SELECT t.expect_error(format($q$UPDATE app.payments SET status = 'approved', paid_at = now() WHERE id = %L$q$, :'p_id'), 'CAMPO_NO_EDITABLE');
SELECT t.ok((SELECT status = 'pending' FROM app.subscriptions WHERE id = :'s_id'), 'avisar la transferencia NO activa la suscripción');
SELECT t.as_user(t.id('fin'));
UPDATE app.payments SET status = 'approved' WHERE id = :'p_id';
SELECT t.ok((SELECT status = 'active' FROM app.subscriptions WHERE id = :'s_id'), 'finanzas aprueba → suscripción activa');
SELECT t.ok((app.effective_plan(t.id('juan'), :'a_id')).max_active_listings = 30, 'el plan efectivo de la agencia pasa a 30 publicaciones');

-- ------------------------------------------------------------------ 7. Venta
SELECT t.as_user(t.id('juan'));
SELECT t.expect_error(format($q$UPDATE app.listings SET status = 'sold' WHERE id = %L$q$, :'l1_id'), 'VENTA_REQUERIDA');
SELECT app.register_sale(:'l1_id', current_date, 7600000, 'ARS', 'girando', p_plate => 'AB 123 CD', p_conversation => :'c1_id') AS sale_id \gset
SELECT t.ok((SELECT status = 'sold' AND sold_at IS NOT NULL FROM app.listings WHERE id = :'l1_id'), 'register_sale → listing sold');
SELECT t.ok((SELECT bool_and(status = 'purge_scheduled' AND purge_after > now() + interval '6 days') FROM app.listing_images WHERE listing_id = :'l1_id'), 'fotos programadas para borrar (retención 7 días)');
SELECT t.ok((SELECT attributed_to_girando FROM app.sales WHERE id = :'sale_id'), 'atribución a Girando derivada del canal');
SELECT t.ok((SELECT purge_after IS NOT NULL FROM app.vehicle_identifiers WHERE vehicle_id = :'v1_id' AND type = 'plate' AND is_current), 'patente con fecha de borrado por retención');
SELECT t.expect_error(format($q$UPDATE app.listings SET title = 'cambio' WHERE id = %L$q$, :'l1_id'), 'PUBLICACION_CERRADA');
SELECT t.ok((SELECT sales = 1 AND NOT sample_sufficient AND avg_final_price_ars IS NULL FROM app.v_sales_by_model), 'con n < 3 no se muestran promedios');
RESET ROLE;

-- ------------------------------------------------------------------ 8. Auditoría inmutable
SELECT t.ok((SELECT count(*) > 10 FROM app.audit_logs), 'cambios críticos auditados automáticamente');
SELECT t.ok((SELECT count(*) = 1 FROM app.audit_logs WHERE entity_type = 'agencies' AND after_data ->> 'status' = 'verified' AND actor_role = 'moderator'), 'auditoría registra quién y con qué rol verificó');
SELECT t.expect_error('UPDATE app.audit_logs SET reason = $$x$$', 'append-only');
SELECT t.expect_error('DELETE FROM app.audit_logs', 'append-only');

ROLLBACK;
\echo 'TESTS OK'
