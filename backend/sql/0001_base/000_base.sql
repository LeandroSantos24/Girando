-- =====================================================================
-- GIRANDO · Base única del esquema (fases 1 a 4). La aplica Alembic (base_0001) en una transacción,
-- archivo por archivo en orden alfabético. Cambios futuros: migraciones nuevas, no editar esta base.
-- 000 · Extensiones, esquemas, roles y funciones de contexto
-- Motor objetivo: PostgreSQL 16 (compatible con Supabase cambiando
-- app_current_user_id() por auth.uid()).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()
CREATE EXTENSION IF NOT EXISTS citext;     -- emails case-insensitive
CREATE EXTENSION IF NOT EXISTS unaccent;   -- búsqueda sin tildes
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- búsqueda aproximada de nombres

-- Esquemas
--   app        : tablas de dominio (nunca expuestas directo a clientes)
--   api_public : vistas de solo lectura con datos PÚBLICOS únicamente
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS api_public;

-- ---------------------------------------------------------------------
-- Roles de base de datos (sin login; el backend usa roles LOGIN que
-- heredan de estos). Ningún rol de aplicación es dueño de las tablas,
-- por lo tanto RLS siempre aplica.
-- ---------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'girando_anon')   THEN CREATE ROLE girando_anon   NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'girando_app')    THEN CREATE ROLE girando_app    NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'girando_worker') THEN CREATE ROLE girando_worker NOLOGIN; END IF;
END $$;
-- girando_anon   : visitantes sin sesión → solo api_public.*
-- girando_app    : API con usuario autenticado (app y panel admin). RLS por app.user_id
-- girando_worker : webhooks (Mercado Pago), jobs programados (vencimientos, retención, emails)

GRANT USAGE ON SCHEMA api_public TO girando_anon, girando_app, girando_worker;
GRANT USAGE ON SCHEMA app        TO girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- Contexto de la request. El backend, después de validar el JWT, ejecuta
-- dentro de la transacción:  SELECT set_config('app.user_id', '<uuid>', true);
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.app_current_user_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$$;

-- Rol "real" de la conexión. Dentro de funciones SECURITY DEFINER current_user
-- es el dueño de la función, por eso se usa el rol de sesión (o el SET ROLE).
CREATE OR REPLACE FUNCTION app.app_connection_role() RETURNS name
LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN current_setting('role') <> 'none' THEN current_setting('role')::name ELSE session_user END
$$;

CREATE OR REPLACE FUNCTION app.app_is_worker() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT pg_has_role(app.app_connection_role(), 'girando_worker', 'member')
         AND NOT pg_has_role(app.app_connection_role(), 'girando_app', 'member')
$$;

-- Normalizaciones inmutables (usables en índices / columnas generadas)
CREATE OR REPLACE FUNCTION app.f_unaccent(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
  SELECT public.unaccent('public.unaccent'::regdictionary, $1)
$$;

CREATE OR REPLACE FUNCTION app.normalize_plate(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
  SELECT upper(regexp_replace($1, '[^A-Za-z0-9]', '', 'g'))
$$;

-- CUIT/CUIL argentino: 11 dígitos, prefijo válido y dígito verificador módulo 11
CREATE OR REPLACE FUNCTION app.is_valid_cuit(p text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
  d text := regexp_replace(coalesce(p, ''), '[^0-9]', '', 'g');
  w int[] := ARRAY[5,4,3,2,7,6,5,4,3,2];
  s int := 0; r int; dv int;
BEGIN
  IF length(d) <> 11 OR left(d, 2) NOT IN ('20','23','24','25','26','27','30','33','34') THEN
    RETURN false;
  END IF;
  FOR i IN 1..10 LOOP s := s + substr(d, i, 1)::int * w[i]; END LOOP;
  r := 11 - (s % 11);
  dv := CASE WHEN r = 11 THEN 0 WHEN r = 10 THEN 9 ELSE r END;
  RETURN dv = substr(d, 11, 1)::int;
END $$;

-- Patente argentina: formato viejo auto (ABC123), Mercosur auto (AB123CD),
-- viejo moto (123ABC) y Mercosur moto (A123BCD). Otros países: no se valida formato.
CREATE OR REPLACE FUNCTION app.is_valid_ar_plate(p text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT app.normalize_plate(p) ~ '^([A-Z]{3}[0-9]{3}|[A-Z]{2}[0-9]{3}[A-Z]{2}|[0-9]{3}[A-Z]{3}|[A-Z][0-9]{3}[A-Z]{3})$'
$$;

-- updated_at automático
CREATE OR REPLACE FUNCTION app.tg_set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;
