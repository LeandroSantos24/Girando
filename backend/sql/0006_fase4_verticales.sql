-- =====================================================================
-- 0006 · Fase 4 — Verticales (Taxis y permisos, Servicios, Repuestos, Empleos),
--        planes por tipo de cuenta, límite gratis compartido, cambio de plan,
--        compra de promociones y candado de repuestos (pago + verificación).
--
-- Modelo: `posts` es la publicación de las verticales nuevas (los vehículos siguen en
-- `listings`). Cada vertical tiene su tabla de detalle 1:1 con columnas tipadas: los
-- filtros salen de datos estructurados, nunca de texto libre.
-- `agencies` pasa a ser la "cuenta comercial" de cualquier rubro (ver agency_kind).
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- 1. Planes: límite de empleos y requisito de verificación
-- ---------------------------------------------------------------------
ALTER TABLE plans ADD COLUMN IF NOT EXISTS max_active_jobs integer NOT NULL DEFAULT 1;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS requires_verification boolean NOT NULL DEFAULT false;
ALTER TABLE plans ADD COLUMN IF NOT EXISTS pending_owner_confirmation boolean NOT NULL DEFAULT false;
ALTER TABLE plans DROP CONSTRAINT IF EXISTS pl_jobs;
ALTER TABLE plans ADD CONSTRAINT pl_jobs CHECK (max_active_jobs >= 0);
COMMENT ON COLUMN plans.max_active_listings IS '[PÚBLICO] Publicaciones activas del rubro de la cuenta: vehículos (+ taxis) en agencias, ítems de catálogo en repuestos, fichas en servicios. En el plan del particular es el total (vehículo, taxi o empleo).';
COMMENT ON COLUMN plans.max_active_jobs IS '[PÚBLICO] Empleos activos de una cuenta comercial. En el particular no aplica: el empleo comparte el cupo gratis.';
COMMENT ON COLUMN plans.requires_verification IS '[PÚBLICO] La cuenta solo publica si además está verificada (casas de repuestos).';
COMMENT ON COLUMN plans.pending_owner_confirmation IS '[ADMIN] Valor inicial todavía no confirmado por el dueño. Se muestra en Admin → Planes.';

CREATE OR REPLACE VIEW api_public.plans AS
SELECT id, code, name, description, audience, price_amount, currency, billing_period, max_active_listings,
       included_featured_listings, stats_level, includes_verification, max_members, features_display, badge_label, sort_order,
       max_active_jobs, requires_verification
FROM app.plans WHERE is_active AND is_public;

-- Audiencia del plan según el rubro de la cuenta
CREATE OR REPLACE FUNCTION app.audience_for_kind(p_kind app.agency_kind) RETURNS app.plan_audience
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE p_kind::text WHEN 'parts_store' THEN 'parts_store' WHEN 'service_provider' THEN 'service_provider'
                           WHEN 'company' THEN 'company' ELSE 'agency' END::app.plan_audience
$$;

-- Plan efectivo: suscripción que otorga; si no hay, el plan por defecto del rubro (si existe) y, si no, el del particular.
CREATE OR REPLACE FUNCTION app.effective_plan(p_user uuid, p_agency uuid) RETURNS app.plans
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public AS $$
DECLARE r app.plans; v_kind app.agency_kind;
BEGIN
  SELECT p.* INTO r
  FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id
  WHERE (CASE WHEN p_agency IS NOT NULL THEN s.agency_id = p_agency ELSE s.user_id = p_user END)
    AND app.subscription_grants(s)
  ORDER BY s.created_at DESC LIMIT 1;
  IF FOUND THEN RETURN r; END IF;
  IF p_agency IS NOT NULL THEN
    SELECT kind INTO v_kind FROM app.agencies WHERE id = p_agency;
    IF v_kind IN ('parts_store','service_provider','company') THEN
      SELECT * INTO r FROM app.plans WHERE audience = app.audience_for_kind(v_kind) AND is_default_for_audience AND is_active;
      IF FOUND THEN RETURN r; END IF;
    END IF;
  END IF;
  SELECT * INTO r FROM app.plans WHERE audience = 'particular' AND is_default_for_audience AND is_active;
  RETURN r;
END $$;

CREATE OR REPLACE FUNCTION app.agency_has_granting_subscription(p_agency uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.subscriptions s WHERE s.agency_id = p_agency AND app.subscription_grants(s))
$$;

-- ---------------------------------------------------------------------
-- 2. posts + detalle por vertical
-- ---------------------------------------------------------------------
DO $$ BEGIN CREATE TYPE post_vertical AS ENUM ('taxi','service','part','job'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE taxi_offer_kind AS ENUM ('taxi_with_permit','permit_only','vehicle_only'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE taxi_service_type AS ENUM ('taxi','remis'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE service_category AS ENUM ('tow','auto_paperwork','insurance_broker','freight','cargo_transport','passenger_transport',
  'mechanic','tire_shop','auto_electrician','body_paint','car_wash','cng','vtv_rto','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE part_category AS ENUM ('engine','transmission','brakes','suspension','electrical','body','interior','tires_wheels',
  'lubricants','cooling','exhaust','lighting','accessories','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE job_role AS ENUM ('driver','mechanic','salesperson','administrative','dispatcher','logistics','body_painter',
  'auto_electrician','tire_fitter','car_washer','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE job_workday AS ENUM ('full_time','part_time','shifts','per_trip'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE job_modality AS ENUM ('onsite','on_route','hybrid','remote'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS posts (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_code        text NOT NULL DEFAULT app.gen_public_code('X'),
  vertical           post_vertical NOT NULL,
  owner_user_id      uuid NOT NULL REFERENCES users(id),
  agency_id          uuid REFERENCES agencies(id),
  created_by         uuid NOT NULL REFERENCES users(id),
  geo_area_id        uuid REFERENCES geo_areas(id),
  title              text NOT NULL DEFAULT '',
  description        text,
  price_amount       numeric(14,2),
  currency           currency_code NOT NULL DEFAULT 'ARS',
  status             listing_status NOT NULL DEFAULT 'draft',
  status_reason      text,
  status_changed_at  timestamptz NOT NULL DEFAULT now(),
  submitted_at       timestamptz,
  first_published_at timestamptz,
  published_at       timestamptz,
  expires_at         timestamptz,
  paused_at          timestamptz,
  closed_at          timestamptz,
  deleted_at         timestamptz,
  reviewed_by        uuid REFERENCES users(id),
  reviewed_at        timestamptz,
  search_vector      tsvector GENERATED ALWAYS AS (
                       setweight(to_tsvector('spanish', app.f_unaccent(coalesce(title, ''))), 'A') ||
                       setweight(to_tsvector('spanish', app.f_unaccent(coalesce(description, ''))), 'B')) STORED,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT po_title_len CHECK (length(title) <= 90),
  CONSTRAINT po_desc_len CHECK (description IS NULL OR length(description) <= 5000),
  CONSTRAINT po_price CHECK (price_amount IS NULL OR (price_amount > 0 AND price_amount < 100000000000)),
  CONSTRAINT po_publishable CHECK (status IN ('draft','deleted') OR (geo_area_id IS NOT NULL AND length(btrim(title)) >= 5)),
  CONSTRAINT po_closed_at CHECK ((status = 'sold') = (closed_at IS NOT NULL)),
  CONSTRAINT po_deleted_at CHECK ((status = 'deleted') = (deleted_at IS NOT NULL)),
  CONSTRAINT po_published_dates CHECK (status <> 'published' OR (published_at IS NOT NULL AND expires_at IS NOT NULL))
);
COMMENT ON TABLE posts IS 'Publicación de las verticales Taxis, Servicios, Repuestos y Empleos. status = ''sold'' significa cerrada por su dueño (vendido / puesto cubierto).';
CREATE UNIQUE INDEX IF NOT EXISTS posts_code_uq ON posts (public_code);
CREATE INDEX IF NOT EXISTS posts_published_idx ON posts (vertical, published_at DESC) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS posts_geo_idx ON posts (vertical, geo_area_id) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS posts_owner_idx ON posts (owner_user_id, status);
CREATE INDEX IF NOT EXISTS posts_agency_idx ON posts (agency_id, vertical, status) WHERE agency_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS posts_moderation_idx ON posts (submitted_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS posts_expiry_idx ON posts (expires_at) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS posts_fts_idx ON posts USING gin (search_vector);

CREATE TABLE IF NOT EXISTS taxi_posts (
  post_id              uuid PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
  offer_kind           taxi_offer_kind NOT NULL,
  service_type         taxi_service_type NOT NULL DEFAULT 'taxi',
  permit_number        text,
  permit_holder_declared text,
  version_id           uuid REFERENCES vehicle_versions(id),
  vehicle_year         smallint,
  fuel                 fuel_type,
  has_cng              boolean NOT NULL DEFAULT false,
  has_meter            boolean NOT NULL DEFAULT false,
  has_gps              boolean NOT NULL DEFAULT false,
  equipment            text[] NOT NULL DEFAULT '{}',
  permit_price         numeric(14,2),
  vehicle_price        numeric(14,2),
  includes_driver_work boolean NOT NULL DEFAULT false,
  permit_verified_at   timestamptz,
  permit_verified_by   uuid REFERENCES users(id),
  CONSTRAINT tx_permit_number CHECK (permit_number IS NULL OR permit_number ~ '^[A-Za-z0-9 ./-]{1,20}$'),
  CONSTRAINT tx_holder CHECK (permit_holder_declared IS NULL OR length(permit_holder_declared) <= 120),
  CONSTRAINT tx_year CHECK (vehicle_year IS NULL OR vehicle_year BETWEEN 1980 AND 2100),
  CONSTRAINT tx_prices CHECK ((permit_price IS NULL OR permit_price > 0) AND (vehicle_price IS NULL OR vehicle_price > 0)),
  CONSTRAINT tx_equipment CHECK (cardinality(equipment) <= 15),
  -- Coherencia entre lo que se ofrece y los datos cargados
  CONSTRAINT tx_shape CHECK (
       (offer_kind = 'permit_only'  AND version_id IS NULL AND vehicle_year IS NULL AND vehicle_price IS NULL)
    OR (offer_kind = 'vehicle_only' AND permit_number IS NULL AND permit_price IS NULL AND permit_holder_declared IS NULL)
    OR  offer_kind = 'taxi_with_permit'),
  CONSTRAINT tx_verified CHECK ((permit_verified_at IS NULL) = (permit_verified_by IS NULL))
);
COMMENT ON COLUMN taxi_posts.permit_number IS '[PÚBLICO] Número de permiso DECLARADO por quien publica. Girando no lo valida salvo sello.';
COMMENT ON COLUMN taxi_posts.permit_holder_declared IS '[PROPIETARIO/ADMIN] Titular declarado. Dato personal: nunca se publica; sirve para la verificación.';
COMMENT ON COLUMN taxi_posts.permit_verified_at IS '[PÚBLICO como sello] Solo lo completa el equipo de Girando tras comprobar el permiso.';

CREATE TABLE IF NOT EXISTS service_posts (
  post_id            uuid PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
  category           service_category NOT NULL,
  coverage_note      text,
  open_24h           boolean NOT NULL DEFAULT false,
  at_home            boolean NOT NULL DEFAULT false,
  vehicle_types      vehicle_type[] NOT NULL DEFAULT '{}',
  license_number     text,
  license_verified_at timestamptz,
  license_verified_by uuid REFERENCES users(id),
  CONSTRAINT sv_coverage CHECK (coverage_note IS NULL OR length(coverage_note) <= 300),
  CONSTRAINT sv_license CHECK (license_number IS NULL OR license_number ~ '^[A-Za-z0-9 ./-]{1,30}$'),
  -- Un productor asesor de seguros tiene que declarar su matrícula de la SSN
  CONSTRAINT sv_insurance_license CHECK (category <> 'insurance_broker' OR license_number IS NOT NULL),
  CONSTRAINT sv_verified CHECK ((license_verified_at IS NULL) = (license_verified_by IS NULL))
);
COMMENT ON COLUMN service_posts.license_number IS '[PÚBLICO] Matrícula declarada (obligatoria para productores asesores de seguros: registro de la SSN).';

CREATE TABLE IF NOT EXISTS part_posts (
  post_id        uuid PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
  category       part_category NOT NULL,
  condition      vehicle_condition NOT NULL DEFAULT 'new',
  brand_id       uuid REFERENCES vehicle_brands(id),
  model_id       uuid REFERENCES vehicle_models(id),
  year_from      smallint,
  year_to        smallint,
  part_number    text,
  part_brand     text,
  in_stock       boolean NOT NULL DEFAULT true,
  CONSTRAINT pt_years CHECK ((year_from IS NULL OR year_from BETWEEN 1950 AND 2100) AND (year_to IS NULL OR year_to BETWEEN 1950 AND 2100)
                         AND (year_from IS NULL OR year_to IS NULL OR year_to >= year_from)),
  CONSTRAINT pt_model_needs_brand CHECK (model_id IS NULL OR brand_id IS NOT NULL),
  CONSTRAINT pt_number CHECK (part_number IS NULL OR length(part_number) <= 60),
  CONSTRAINT pt_brand CHECK (part_brand IS NULL OR length(part_brand) <= 60)
);

CREATE TABLE IF NOT EXISTS job_posts (
  post_id          uuid PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
  role             job_role NOT NULL,
  role_detail      text,
  license_required boolean NOT NULL DEFAULT false,
  license_classes  text[] NOT NULL DEFAULT '{}',
  workday          job_workday NOT NULL DEFAULT 'full_time',
  modality         job_modality NOT NULL DEFAULT 'onsite',
  salary_min       numeric(14,2),
  salary_max       numeric(14,2),
  vacancies        smallint NOT NULL DEFAULT 1,
  CONSTRAINT jb_detail CHECK (role_detail IS NULL OR length(role_detail) <= 80),
  -- Clases de licencia nacional de conducir (A–G con subclase): solo códigos, nunca texto libre
  CONSTRAINT jb_classes CHECK (cardinality(license_classes) <= 8 AND license_classes <@ ARRAY[
    'A','A1','A2','A3','B','B1','B2','C','C1','C2','C3','D','D1','D2','D3','D4','E','E1','E2','F','G','G1','G2','G3']::text[]),
  CONSTRAINT jb_license CHECK (license_required OR cardinality(license_classes) = 0),
  CONSTRAINT jb_salary CHECK ((salary_min IS NULL OR salary_min > 0) AND (salary_max IS NULL OR salary_max > 0)
                          AND (salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min)),
  CONSTRAINT jb_vacancies CHECK (vacancies BETWEEN 1 AND 500)
);
COMMENT ON TABLE job_posts IS 'Puesto de trabajo del rubro. No hay CVs ni documentos: el candidato contacta por la mensajería de Girando.';

CREATE TABLE IF NOT EXISTS post_images (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id          uuid NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  public_id        text NOT NULL,
  secure_url       text NOT NULL,
  storage_provider image_storage_provider NOT NULL,
  position         smallint NOT NULL DEFAULT 0,
  is_cover         boolean NOT NULL DEFAULT false,
  width            integer,
  height           integer,
  bytes            integer,
  status           image_status NOT NULL DEFAULT 'active',
  uploaded_by      uuid REFERENCES users(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pi_position CHECK (position BETWEEN 0 AND 5)
);
CREATE UNIQUE INDEX IF NOT EXISTS post_images_cover_uq ON post_images (post_id) WHERE is_cover AND status = 'active';
CREATE INDEX IF NOT EXISTS post_images_post_idx ON post_images (post_id, position) WHERE status = 'active';

-- ---------------------------------------------------------------------
-- 3. Reglas de posts
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_post_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE me uuid := app.app_current_user_id(); v_kind app.agency_kind; v_owner uuid;
BEGIN
  NEW.public_code := app.gen_public_code(CASE NEW.vertical WHEN 'taxi' THEN 'T' WHEN 'service' THEN 'S' WHEN 'part' THEN 'R' ELSE 'E' END);
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  IF me IS NULL THEN RAISE EXCEPTION 'NO_AUTENTICADO' USING ERRCODE = 'GR403'; END IF;
  IF NEW.status <> 'draft' THEN RAISE EXCEPTION 'LA_PUBLICACION_NACE_EN_BORRADOR' USING ERRCODE = 'GR403'; END IF;
  NEW.created_by := me;
  IF NEW.agency_id IS NULL THEN
    NEW.owner_user_id := me;
    -- Servicios y repuestos se publican desde una cuenta comercial
    IF NEW.vertical IN ('service','part') THEN RAISE EXCEPTION 'REQUIERE_CUENTA_COMERCIAL' USING ERRCODE = 'GR422'; END IF;
  ELSE
    IF NOT app.app_is_agency_member(NEW.agency_id) THEN RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403'; END IF;
    SELECT kind INTO v_kind FROM app.agencies WHERE id = NEW.agency_id;
    IF (NEW.vertical = 'part' AND v_kind <> 'parts_store') OR (NEW.vertical = 'service' AND v_kind <> 'service_provider')
       OR (NEW.vertical = 'taxi' AND v_kind NOT IN ('agency','official_dealer')) THEN
      RAISE EXCEPTION 'RUBRO_NO_PERMITIDO' USING ERRCODE = 'GR422';
    END IF;
    SELECT user_id INTO v_owner FROM app.agency_members WHERE agency_id = NEW.agency_id AND role = 'owner' AND status = 'active' LIMIT 1;
    NEW.owner_user_id := coalesce(v_owner, me);
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a_post_insert ON posts;
CREATE TRIGGER a_post_insert BEFORE INSERT ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_insert();

CREATE OR REPLACE FUNCTION app.tg_post_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  IF (NEW.vertical, NEW.owner_user_id, NEW.agency_id, NEW.created_by, NEW.public_code)
     IS DISTINCT FROM (OLD.vertical, OLD.owner_user_id, OLD.agency_id, OLD.created_by, OLD.public_code) THEN
    RAISE EXCEPTION 'CAMPO_NO_EDITABLE' USING ERRCODE = 'GR403';
  END IF;
  IF NOT (app.can_manage_listing(OLD.owner_user_id, OLD.agency_id) OR app.app_has_staff_role('moderator','admin')) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a_post_guard ON posts;
CREATE TRIGGER a_post_guard BEFORE UPDATE ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_guard();

CREATE OR REPLACE FUNCTION app.tg_post_state() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE
  t text := OLD.status || '>' || NEW.status;
  is_worker boolean := app.app_is_worker();
  is_mod boolean := app.app_has_staff_role('moderator','admin');
  is_owner boolean := app.can_manage_listing(OLD.owner_user_id, OLD.agency_id);
  owner_moves text[] := ARRAY['draft>pending','draft>deleted','pending>draft',
    'published>paused','published>sold','published>deleted','paused>pending','paused>sold','paused>deleted',
    'expired>pending','expired>sold','expired>deleted','requires_changes>pending','requires_changes>deleted','rejected>pending','rejected>deleted'];
  staff_moves text[] := ARRAY['pending>published','pending>rejected','pending>requires_changes','requires_changes>published',
    'published>requires_changes','published>paused','paused>published','paused>deleted','rejected>deleted','published>deleted'];
  system_moves text[] := ARRAY['published>expired','published>paused'];
  v_days int; v_ok boolean;
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;
  IF NOT ((is_owner AND t = ANY (owner_moves)) OR (is_mod AND t = ANY (staff_moves)) OR (is_worker AND t = ANY (system_moves))) THEN
    RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA %', t USING ERRCODE = 'GR403';
  END IF;
  IF NEW.status IN ('requires_changes','rejected') OR (is_mod AND NOT is_owner AND t IN ('published>paused','paused>deleted','rejected>deleted','published>deleted')) THEN
    IF NEW.status_reason IS NULL OR NEW.status_reason IS NOT DISTINCT FROM OLD.status_reason THEN
      RAISE EXCEPTION 'MOTIVO_OBLIGATORIO' USING ERRCODE = 'GR422';
    END IF;
  END IF;
  IF NEW.status = 'pending' THEN
    v_ok := CASE NEW.vertical
      WHEN 'taxi' THEN EXISTS (SELECT 1 FROM app.taxi_posts d WHERE d.post_id = NEW.id) AND NEW.price_amount IS NOT NULL
      WHEN 'service' THEN EXISTS (SELECT 1 FROM app.service_posts d WHERE d.post_id = NEW.id)
      WHEN 'part' THEN EXISTS (SELECT 1 FROM app.part_posts d WHERE d.post_id = NEW.id)
      ELSE EXISTS (SELECT 1 FROM app.job_posts d WHERE d.post_id = NEW.id) END;
    IF NOT v_ok THEN RAISE EXCEPTION 'PUBLICACION_INCOMPLETA' USING ERRCODE = 'GR422'; END IF;
    NEW.submitted_at := now();
  END IF;
  IF NEW.status = 'published' THEN
    v_days := app.setting_int('posts.duration_days_' || NEW.vertical::text,
                              CASE NEW.vertical WHEN 'job' THEN 30 WHEN 'taxi' THEN 60 ELSE 3650 END);
    NEW.published_at := now();
    NEW.first_published_at := coalesce(OLD.first_published_at, now());
    NEW.expires_at := now() + make_interval(days => v_days);
    IF is_mod THEN NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now(); END IF;
  ELSIF NEW.status IN ('rejected','requires_changes') THEN
    NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now();
  ELSIF NEW.status = 'paused' THEN NEW.paused_at := now();
  ELSIF NEW.status = 'sold' THEN NEW.closed_at := now();
  ELSIF NEW.status = 'deleted' THEN NEW.deleted_at := now();
  END IF;
  IF NEW.status NOT IN ('requires_changes','rejected','paused') AND NOT (is_mod AND NEW.status = 'deleted') THEN
    NEW.status_reason := NULL;
  END IF;
  NEW.status_changed_at := now();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS b_post_state ON posts;
CREATE TRIGGER b_post_state BEFORE UPDATE OF status ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_state();

-- Aviso al dueño cuando moderación resuelve
CREATE OR REPLACE FUNCTION app.tg_post_after() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status AND OLD.status = 'pending' AND NEW.status IN ('published','rejected','requires_changes') THEN
    PERFORM app.enqueue_notification(NEW.owner_user_id,
      CASE NEW.status WHEN 'published' THEN 'listing.approved' WHEN 'rejected' THEN 'listing.rejected' ELSE 'listing.changes_requested' END,
      CASE NEW.status WHEN 'published' THEN 'Tu publicación fue aprobada' WHEN 'rejected' THEN 'Tu publicación fue rechazada' ELSE 'Moderación pidió cambios' END,
      NEW.title, 'post', NEW.id, '/mis-publicaciones');
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS z_post_after ON posts;
CREATE TRIGGER z_post_after AFTER UPDATE OF status ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_after();

-- Los sellos (permiso verificado / matrícula verificada) solo los pone moderación; cambiar el dato declarado los quita
CREATE OR REPLACE FUNCTION app.tg_post_detail_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE p app.posts; is_mod boolean := app.app_has_staff_role('moderator','admin'); me uuid := app.app_current_user_id();
BEGIN
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  SELECT * INTO p FROM app.posts WHERE id = NEW.post_id;
  IF p.id IS NULL OR NOT (app.can_manage_listing(p.owner_user_id, p.agency_id) OR is_mod) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  IF TG_TABLE_NAME = 'taxi_posts' THEN
    IF p.vertical <> 'taxi' THEN RAISE EXCEPTION 'VERTICAL_INCORRECTA' USING ERRCODE = 'GR422'; END IF;
    IF TG_OP = 'INSERT' THEN
      NEW.permit_verified_at := NULL; NEW.permit_verified_by := NULL;
    ELSIF NEW.permit_verified_at IS DISTINCT FROM OLD.permit_verified_at THEN
      IF NOT is_mod THEN RAISE EXCEPTION 'SOLO_GIRANDO_VERIFICA' USING ERRCODE = 'GR403'; END IF;
      NEW.permit_verified_by := CASE WHEN NEW.permit_verified_at IS NULL THEN NULL ELSE me END;
    ELSIF (NEW.permit_number, NEW.service_type) IS DISTINCT FROM (OLD.permit_number, OLD.service_type) THEN
      NEW.permit_verified_at := NULL; NEW.permit_verified_by := NULL;
    END IF;
  ELSIF TG_TABLE_NAME = 'service_posts' THEN
    IF p.vertical <> 'service' THEN RAISE EXCEPTION 'VERTICAL_INCORRECTA' USING ERRCODE = 'GR422'; END IF;
    IF TG_OP = 'INSERT' THEN
      NEW.license_verified_at := NULL; NEW.license_verified_by := NULL;
    ELSIF NEW.license_verified_at IS DISTINCT FROM OLD.license_verified_at THEN
      IF NOT is_mod THEN RAISE EXCEPTION 'SOLO_GIRANDO_VERIFICA' USING ERRCODE = 'GR403'; END IF;
      NEW.license_verified_by := CASE WHEN NEW.license_verified_at IS NULL THEN NULL ELSE me END;
    ELSIF NEW.license_number IS DISTINCT FROM OLD.license_number THEN
      NEW.license_verified_at := NULL; NEW.license_verified_by := NULL;
    END IF;
  ELSIF TG_TABLE_NAME = 'part_posts' AND p.vertical <> 'part' THEN RAISE EXCEPTION 'VERTICAL_INCORRECTA' USING ERRCODE = 'GR422';
  ELSIF TG_TABLE_NAME = 'job_posts' AND p.vertical <> 'job' THEN RAISE EXCEPTION 'VERTICAL_INCORRECTA' USING ERRCODE = 'GR422';
  END IF;
  RETURN NEW;
END $$;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['taxi_posts','service_posts','part_posts','job_posts'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS a_post_detail_guard ON app.%I', t);
    EXECUTE format('CREATE TRIGGER a_post_detail_guard BEFORE INSERT OR UPDATE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.tg_post_detail_guard()', t);
    EXECUTE format('DROP TRIGGER IF EXISTS zz_audit ON app.%I', t);
  END LOOP;
END $$;
DROP TRIGGER IF EXISTS posts_updated ON posts;
CREATE TRIGGER posts_updated BEFORE UPDATE ON posts FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
DROP TRIGGER IF EXISTS zz_audit ON posts;
CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON posts FOR EACH ROW EXECUTE FUNCTION tg_audit_row();

-- ---------------------------------------------------------------------
-- 4. Límites: el particular tiene UN cupo gratis en total (vehículo, taxi o empleo)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.active_counts(p_user uuid, p_agency uuid, p_skip uuid DEFAULT NULL,
  OUT vehicles int, OUT taxis int, OUT jobs int, OUT services int, OUT parts int)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT
    (SELECT count(*)::int FROM app.listings l WHERE l.status IN ('pending','published') AND l.id IS DISTINCT FROM p_skip
       AND (CASE WHEN p_agency IS NOT NULL THEN l.agency_id = p_agency ELSE l.owner_user_id = p_user AND l.agency_id IS NULL END)),
    count(*) FILTER (WHERE p.vertical = 'taxi')::int, count(*) FILTER (WHERE p.vertical = 'job')::int,
    count(*) FILTER (WHERE p.vertical = 'service')::int, count(*) FILTER (WHERE p.vertical = 'part')::int
  FROM (SELECT 1) one
  LEFT JOIN app.posts p ON p.status IN ('pending','published') AND p.id IS DISTINCT FROM p_skip
       AND (CASE WHEN p_agency IS NOT NULL THEN p.agency_id = p_agency ELSE p.owner_user_id = p_user AND p.agency_id IS NULL END)
$$;

-- ¿Cuántas usa y cuál es el tope para ESTE tipo de publicación? ('vehicle' | vertical de posts)
CREATE OR REPLACE FUNCTION app.limit_for(p_user uuid, p_agency uuid, p_what text, p_skip uuid,
  OUT used int, OUT max_allowed int, OUT plan_code text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_plan app.plans := app.effective_plan(p_user, p_agency); c record;
BEGIN
  IF v_plan.id IS NULL THEN RAISE EXCEPTION 'PLAN_NO_CONFIGURADO' USING ERRCODE = 'GR409'; END IF;
  SELECT * INTO c FROM app.active_counts(p_user, p_agency, p_skip);
  plan_code := v_plan.code;
  IF p_agency IS NULL THEN                 -- particular: un solo cupo para todo
    used := c.vehicles + c.taxis + c.jobs; max_allowed := v_plan.max_active_listings;
  ELSIF p_what = 'job' THEN
    used := c.jobs; max_allowed := v_plan.max_active_jobs;
  ELSIF p_what IN ('vehicle','taxi') THEN
    used := c.vehicles + c.taxis; max_allowed := v_plan.max_active_listings;
  ELSIF p_what = 'part' THEN
    used := c.parts; max_allowed := v_plan.max_active_listings;
  ELSE
    used := c.services; max_allowed := v_plan.max_active_listings;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION app.tg_listing_limit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v record; v_kind app.agency_kind;
BEGIN
  IF NEW.status NOT IN ('pending','published') THEN RETURN NEW; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status IN ('pending','published') THEN RETURN NEW; END IF;
  PERFORM pg_advisory_xact_lock(hashtext('listing_limit:' || coalesce(NEW.agency_id, NEW.owner_user_id)::text));
  IF NEW.agency_id IS NOT NULL THEN
    SELECT kind INTO v_kind FROM app.agencies WHERE id = NEW.agency_id;
    IF v_kind NOT IN ('agency','official_dealer') THEN RAISE EXCEPTION 'RUBRO_NO_PERMITIDO' USING ERRCODE = 'GR422'; END IF;
  END IF;
  SELECT * INTO v FROM app.limit_for(NEW.owner_user_id, NEW.agency_id, 'vehicle', NEW.id);
  IF v.used >= v.max_allowed THEN
    RAISE EXCEPTION 'LIMITE_ALCANZADO' USING ERRCODE = 'GR409',
      DETAIL = format('plan=%s limite=%s usadas=%s', v.plan_code, v.max_allowed, v.used);
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION app.tg_post_limit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v record; a app.agencies; v_plan app.plans;
BEGIN
  IF NEW.status NOT IN ('pending','published') THEN RETURN NEW; END IF;
  IF OLD.status IN ('pending','published') THEN RETURN NEW; END IF;
  PERFORM pg_advisory_xact_lock(hashtext('listing_limit:' || coalesce(NEW.agency_id, NEW.owner_user_id)::text));
  IF NEW.agency_id IS NOT NULL THEN
    SELECT * INTO a FROM app.agencies WHERE id = NEW.agency_id;
    v_plan := app.effective_plan(NEW.owner_user_id, NEW.agency_id);
    -- Candado de repuestos (y de cualquier plan que exija verificación): pago vigente + cuenta verificada
    IF NEW.vertical = 'part' AND (NOT app.agency_has_granting_subscription(NEW.agency_id) OR a.status <> 'verified') THEN
      RAISE EXCEPTION 'REQUIERE_PAGO_Y_VERIFICACION' USING ERRCODE = 'GR409',
        DETAIL = format('pago=%s verificada=%s', app.agency_has_granting_subscription(NEW.agency_id), a.status = 'verified');
    END IF;
    IF v_plan.requires_verification AND a.status <> 'verified' THEN
      RAISE EXCEPTION 'REQUIERE_PAGO_Y_VERIFICACION' USING ERRCODE = 'GR409', DETAIL = 'verificada=false';
    END IF;
  END IF;
  SELECT * INTO v FROM app.limit_for(NEW.owner_user_id, NEW.agency_id, NEW.vertical::text, NEW.id);
  IF v.used >= v.max_allowed THEN
    RAISE EXCEPTION 'LIMITE_ALCANZADO' USING ERRCODE = 'GR409',
      DETAIL = format('plan=%s limite=%s usadas=%s', v.plan_code, v.max_allowed, v.used);
  END IF;
  -- Servicios: una ficha por rubro y zona
  IF NEW.vertical = 'service' AND EXISTS (
       SELECT 1 FROM app.posts p JOIN app.service_posts d ON d.post_id = p.id
        WHERE p.agency_id = NEW.agency_id AND p.id <> NEW.id AND p.status IN ('pending','published')
          AND p.geo_area_id = NEW.geo_area_id
          AND d.category = (SELECT category FROM app.service_posts WHERE post_id = NEW.id)) THEN
    RAISE EXCEPTION 'FICHA_DUPLICADA' USING ERRCODE = 'GR409', DETAIL = 'Ya hay una ficha de ese rubro en esa zona';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS c_post_limit ON posts;
CREATE TRIGGER c_post_limit BEFORE UPDATE OF status ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_limit();

-- Pérdida o baja de plan: se PAUSA lo que excede (lo más viejo primero). Nunca se borra.
CREATE OR REPLACE FUNCTION app.enforce_plan_limit(p_user uuid, p_agency uuid) RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER SET search_path = app, public AS $$
DECLARE
  v_plan app.plans := app.effective_plan(p_user, p_agency);
  v_n int := 0; v_m int; v_reason constant text := 'Límite del plan: la suscripción ya no otorga el plan';
  v_parts_ok boolean := true;
BEGIN
  -- cupo principal: vehículos + taxis (y empleos si es particular)
  WITH pool AS (
    SELECT 'l' AS k, id, published_at FROM app.listings
     WHERE status = 'published' AND (CASE WHEN p_agency IS NOT NULL THEN agency_id = p_agency ELSE owner_user_id = p_user AND agency_id IS NULL END)
    UNION ALL
    SELECT 'p', id, published_at FROM app.posts
     WHERE status = 'published' AND (vertical = 'taxi' OR (p_agency IS NULL AND vertical = 'job'))
       AND (CASE WHEN p_agency IS NOT NULL THEN agency_id = p_agency ELSE owner_user_id = p_user AND agency_id IS NULL END)),
  ranked AS (SELECT k, id, row_number() OVER (ORDER BY published_at DESC) AS rn FROM pool),
  ul AS (UPDATE app.listings l SET status = 'paused', status_reason = v_reason FROM ranked r
          WHERE r.k = 'l' AND r.id = l.id AND r.rn > v_plan.max_active_listings RETURNING 1),
  up AS (UPDATE app.posts p SET status = 'paused', status_reason = v_reason FROM ranked r
          WHERE r.k = 'p' AND r.id = p.id AND r.rn > v_plan.max_active_listings RETURNING 1)
  SELECT (SELECT count(*) FROM ul) + (SELECT count(*) FROM up) INTO v_n;
  IF p_agency IS NULL THEN RETURN v_n; END IF;

  -- repuestos: sin pago vigente o sin verificación no queda nada publicado
  SELECT app.agency_has_granting_subscription(p_agency) AND status = 'verified' INTO v_parts_ok FROM app.agencies WHERE id = p_agency;
  WITH ranked AS (SELECT id, vertical, row_number() OVER (PARTITION BY vertical ORDER BY published_at DESC) AS rn
                    FROM app.posts WHERE status = 'published' AND agency_id = p_agency AND vertical IN ('part','service','job')),
  up AS (UPDATE app.posts p SET status = 'paused',
                status_reason = CASE WHEN r.vertical = 'part' AND NOT coalesce(v_parts_ok, false)
                                     THEN 'Repuestos: hace falta la suscripción paga y la verificación vigentes' ELSE v_reason END
           FROM ranked r WHERE r.id = p.id AND (
                 (r.vertical = 'part' AND (NOT coalesce(v_parts_ok, false) OR r.rn > v_plan.max_active_listings))
              OR (r.vertical = 'service' AND r.rn > v_plan.max_active_listings)
              OR (r.vertical = 'job' AND r.rn > v_plan.max_active_jobs)) RETURNING 1)
  SELECT count(*) INTO v_m FROM up;
  RETURN v_n + v_m;
END $$;

-- Barrido del worker: cuentas con suscripción cuyo plan cambió y quedaron excedidas
CREATE OR REPLACE FUNCTION app.enforce_all_plan_limits() RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER SET search_path = app, public AS $$
DECLARE a record; v_n int := 0;
BEGIN
  FOR a IN SELECT DISTINCT agency_id FROM app.subscriptions WHERE agency_id IS NOT NULL AND updated_at > now() - interval '3 days' LOOP
    v_n := v_n + coalesce(app.enforce_plan_limit(NULL, a.agency_id), 0);
  END LOOP;
  RETURN v_n;
END $$;

-- ---------------------------------------------------------------------
-- 5. Repuestos: no se pide la verificación presencial sin pago aprobado
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_verifications_parts_gate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_kind app.agency_kind;
BEGIN
  IF NEW.subject_agency_id IS NULL OR app.app_is_worker() THEN RETURN NEW; END IF;
  SELECT kind INTO v_kind FROM app.agencies WHERE id = NEW.subject_agency_id;
  IF v_kind = 'parts_store' AND NOT app.agency_has_granting_subscription(NEW.subject_agency_id) THEN
    RAISE EXCEPTION 'PAGO_REQUERIDO_ANTES_DE_VERIFICAR' USING ERRCODE = 'GR409';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a0_verifications_parts_gate ON verifications;
CREATE TRIGGER a0_verifications_parts_gate BEFORE INSERT ON verifications FOR EACH ROW EXECUTE FUNCTION tg_verifications_parts_gate();

-- ---------------------------------------------------------------------
-- 6. Cambio de plan y compra de promociones
--    Regla de upgrade (sin prorrateo): al aprobarse el pago rige el plan nuevo y el período
--    se reinicia desde la fecha del pago. Downgrade: queda en pending_plan_id y rige en la
--    próxima renovación; lo que excede se pausa.
-- ---------------------------------------------------------------------
ALTER TABLE payments ADD COLUMN IF NOT EXISTS plan_change_to uuid REFERENCES plans(id);
ALTER TABLE payments DROP CONSTRAINT IF EXISTS pay_plan_change;
ALTER TABLE payments ADD CONSTRAINT pay_plan_change CHECK (plan_change_to IS NULL OR subscription_id IS NOT NULL);
COMMENT ON COLUMN payments.plan_change_to IS '[PROPIETARIO] Si no es NULL, este pago es una mejora de plan: al aprobarse la suscripción pasa a ese plan.';
ALTER TABLE promotions ADD COLUMN IF NOT EXISTS target_vertical text;
ALTER TABLE promotions DROP CONSTRAINT IF EXISTS pr_vertical;
ALTER TABLE promotions ADD CONSTRAINT pr_vertical CHECK (target_vertical IS NULL OR target_vertical IN ('vehicles','taxis','services','parts','jobs'));
COMMENT ON COLUMN promotions.target_vertical IS '[PÚBLICO] Sección donde corre el espacio publicitario. NULL = todas.';

CREATE OR REPLACE FUNCTION app.subscription_change_plan(p_sub uuid, p_plan uuid, p_paid_at timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE pl app.plans; v_anchor int;
BEGIN
  SELECT * INTO pl FROM app.plans WHERE id = p_plan;
  IF NOT FOUND THEN RETURN; END IF;
  v_anchor := extract(day FROM p_paid_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::int;
  UPDATE app.subscriptions SET
    plan_id = pl.id, pending_plan_id = NULL, price_amount = pl.price_amount, currency = pl.currency, billing_period = pl.billing_period,
    status = 'active', started_at = coalesce(started_at, p_paid_at), grace_until = NULL, cancel_at_period_end = false,
    billing_anchor_day = v_anchor, current_period_start = p_paid_at,
    current_period_end = app.next_period_end(p_paid_at, pl.billing_period, v_anchor),
    next_renewal_at = CASE WHEN provider = 'mercadopago' THEN app.next_period_end(p_paid_at, pl.billing_period, v_anchor) END
  WHERE id = p_sub;
END $$;

-- Renovación: si había una baja de plan pendiente, el plan nuevo rige desde este período (con su precio)
CREATE OR REPLACE FUNCTION app.subscription_apply_payment(p_sub uuid, p_paid_at timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE
  s app.subscriptions;
  v_window int := app.setting_int('billing.renewal_window_days', 15);
  v_grace int := app.setting_int('billing.grace_days', 10);
  v_start timestamptz; v_anchor int; v_end timestamptz;
  tz constant text := 'America/Argentina/Buenos_Aires';
BEGIN
  SELECT * INTO s FROM app.subscriptions WHERE id = p_sub FOR UPDATE;
  IF NOT FOUND OR s.billing_period = 'none' THEN RETURN; END IF;
  IF s.current_period_end IS NOT NULL
     AND p_paid_at BETWEEN s.current_period_end - make_interval(days => v_window) AND s.current_period_end + make_interval(days => v_grace) THEN
    v_start := s.current_period_end;
    v_anchor := coalesce(s.billing_anchor_day, extract(day FROM s.current_period_end AT TIME ZONE tz)::int);
  ELSIF s.current_period_end IS NOT NULL AND p_paid_at < s.current_period_end - make_interval(days => v_window) THEN
    v_start := coalesce(s.current_period_start, p_paid_at);
    v_anchor := coalesce(s.billing_anchor_day, extract(day FROM v_start AT TIME ZONE tz)::int);
  ELSE
    v_start := p_paid_at;
    v_anchor := extract(day FROM p_paid_at AT TIME ZONE tz)::int;
  END IF;
  v_end := app.next_period_end(v_start, s.billing_period, v_anchor);
  UPDATE app.subscriptions SET
    plan_id = coalesce(pending_plan_id, plan_id), pending_plan_id = NULL,
    status = 'active', started_at = coalesce(started_at, p_paid_at), grace_until = NULL,
    billing_anchor_day = v_anchor,
    current_period_start = CASE WHEN v_end > coalesce(current_period_end, '-infinity') THEN v_start ELSE current_period_start END,
    current_period_end = greatest(coalesce(current_period_end, v_end), v_end),
    next_renewal_at = CASE WHEN provider = 'mercadopago' THEN greatest(coalesce(current_period_end, v_end), v_end) END
  WHERE id = p_sub;
  IF s.pending_plan_id IS NOT NULL THEN
    UPDATE app.subscriptions x SET price_amount = p.price_amount, currency = p.currency
      FROM app.plans p WHERE p.id = s.pending_plan_id AND x.id = p_sub;
    IF app.app_is_worker() THEN PERFORM app.enforce_plan_limit(s.user_id, s.agency_id); END IF;
  END IF;
END $$;

-- Promoción paga: se activa sola al aprobarse el pago (los banners esperan la revisión de la creatividad)
CREATE OR REPLACE FUNCTION app.promotion_apply_payment(p_promo uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE pr app.promotions; v_len interval;
BEGIN
  SELECT * INTO pr FROM app.promotions WHERE id = p_promo FOR UPDATE;
  IF NOT FOUND THEN RETURN; END IF;
  INSERT INTO app.promotion_events (promotion_id, event, from_status, to_status, actor_type) VALUES (pr.id, 'payment_approved', pr.status, pr.status, 'provider');
  IF pr.status <> 'pending' OR pr.type = 'banner_campaign' THEN RETURN; END IF;
  v_len := pr.ends_at - pr.starts_at;
  UPDATE app.promotions SET status = 'active', approved_at = now(),
         starts_at = least(starts_at, now()), ends_at = greatest(ends_at, now() + v_len)
   WHERE id = pr.id;
  INSERT INTO app.promotion_events (promotion_id, event, from_status, to_status, actor_type) VALUES (pr.id, 'activated', 'pending', 'active', 'system');
END $$;

CREATE OR REPLACE FUNCTION app.tg_payments_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status = 'approved' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'approved') THEN
    IF NEW.subscription_id IS NOT NULL AND NEW.plan_change_to IS NOT NULL THEN
      PERFORM app.subscription_change_plan(NEW.subscription_id, NEW.plan_change_to, coalesce(NEW.paid_at, now()));
    ELSIF NEW.subscription_id IS NOT NULL THEN
      PERFORM app.subscription_apply_payment(NEW.subscription_id, coalesce(NEW.paid_at, now()));
    ELSIF NEW.promotion_id IS NOT NULL THEN
      PERFORM app.promotion_apply_payment(NEW.promotion_id);
    END IF;
  ELSIF NEW.status = 'rejected' AND TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM 'rejected' AND NEW.promotion_id IS NOT NULL THEN
    INSERT INTO app.promotion_events (promotion_id, event, actor_type) VALUES (NEW.promotion_id, 'payment_failed', 'provider');
  END IF;
  RETURN NEW;
END $$;

-- El monto de una mejora de plan lo fija el plan nuevo (nunca el cliente)
CREATE OR REPLACE FUNCTION app.tg_payments_plan_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE s app.subscriptions; pl app.plans; cur app.plans;
BEGIN
  IF NEW.plan_change_to IS NULL OR app.app_is_worker() THEN RETURN NEW; END IF;
  SELECT * INTO s FROM app.subscriptions WHERE id = NEW.subscription_id;
  SELECT * INTO pl FROM app.plans WHERE id = NEW.plan_change_to AND is_active;
  SELECT * INTO cur FROM app.plans WHERE id = s.plan_id;
  IF pl.id IS NULL OR pl.audience <> cur.audience OR pl.price_amount <= 0 THEN
    RAISE EXCEPTION 'PLAN_INVALIDO' USING ERRCODE = 'GR422';
  END IF;
  IF NOT app.subscription_grants(s) THEN RAISE EXCEPTION 'SIN_SUSCRIPCION_VIGENTE' USING ERRCODE = 'GR409'; END IF;
  IF pl.max_active_listings <= cur.max_active_listings THEN
    RAISE EXCEPTION 'NO_ES_UNA_MEJORA' USING ERRCODE = 'GR422';   -- las bajas no se pagan: van por pending_plan_id
  END IF;
  NEW.amount := pl.price_amount; NEW.currency := pl.currency;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS b_payments_plan_change ON payments;
CREATE TRIGGER b_payments_plan_change BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION tg_payments_plan_change();

-- El titular solo puede dejar pendiente una BAJA de plan (o anularla). Antes podía escribir cualquier plan.
CREATE OR REPLACE FUNCTION app.tg_subscriptions_pending_plan() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE pl app.plans; cur app.plans;
BEGIN
  IF NEW.pending_plan_id IS NOT DISTINCT FROM OLD.pending_plan_id OR NEW.pending_plan_id IS NULL THEN RETURN NEW; END IF;
  IF app.app_is_worker() OR pg_trigger_depth() > 1 OR app.app_has_staff_role('finance') THEN RETURN NEW; END IF;
  SELECT * INTO pl FROM app.plans WHERE id = NEW.pending_plan_id AND is_active AND is_public;
  SELECT * INTO cur FROM app.plans WHERE id = OLD.plan_id;
  IF pl.id IS NULL OR pl.audience <> cur.audience OR pl.price_amount <= 0 OR pl.max_active_listings >= cur.max_active_listings THEN
    RAISE EXCEPTION 'SOLO_BAJA_DE_PLAN' USING ERRCODE = 'GR403';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS b_subscriptions_pending_plan ON subscriptions;
CREATE TRIGGER b_subscriptions_pending_plan BEFORE UPDATE OF pending_plan_id ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION tg_subscriptions_pending_plan();

-- ---------------------------------------------------------------------
-- 7. RLS + grants
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['posts','taxi_posts','service_posts','part_posts','job_posts','post_images'] LOOP
    EXECUTE format('ALTER TABLE app.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS worker_all ON app.%I', t);
    EXECUTE format('CREATE POLICY worker_all ON app.%I TO girando_worker USING (true) WITH CHECK (true)', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON app.%I TO girando_app', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON app.%I TO girando_worker', t);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION app.can_manage_post_id(p_post uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.posts p WHERE p.id = p_post AND app.can_manage_listing(p.owner_user_id, p.agency_id))
$$;

DROP POLICY IF EXISTS po_select ON posts;
CREATE POLICY po_select ON posts FOR SELECT TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR is_mod());
DROP POLICY IF EXISTS po_insert ON posts;
CREATE POLICY po_insert ON posts FOR INSERT TO girando_app WITH CHECK (can_manage_listing(owner_user_id, agency_id));
DROP POLICY IF EXISTS po_update ON posts;
CREATE POLICY po_update ON posts FOR UPDATE TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR is_mod()) WITH CHECK (true);
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['taxi_posts','service_posts','part_posts','job_posts','post_images'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS pd_select ON app.%I', t);
    EXECUTE format('CREATE POLICY pd_select ON app.%I FOR SELECT TO girando_app USING (app.can_manage_post_id(post_id) OR app.is_mod())', t);
    EXECUTE format('DROP POLICY IF EXISTS pd_insert ON app.%I', t);
    EXECUTE format('CREATE POLICY pd_insert ON app.%I FOR INSERT TO girando_app WITH CHECK (app.can_manage_post_id(post_id))', t);
    EXECUTE format('DROP POLICY IF EXISTS pd_update ON app.%I', t);
    EXECUTE format('CREATE POLICY pd_update ON app.%I FOR UPDATE TO girando_app USING (app.can_manage_post_id(post_id) OR app.is_mod())', t);
  END LOOP;
END $$;

REVOKE EXECUTE ON FUNCTION app.subscription_change_plan(uuid, uuid, timestamptz), app.promotion_apply_payment(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.active_counts(uuid, uuid, uuid), app.limit_for(uuid, uuid, text, uuid), app.audience_for_kind(app.agency_kind),
  app.agency_has_granting_subscription(uuid), app.can_manage_post_id(uuid), app.enforce_all_plan_limits() TO girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- 8. Vista pública de las verticales (una sola, con las columnas de cada detalle)
--    Repuestos solo se ve si la casa está verificada Y tiene la suscripción vigente.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW api_public.posts WITH (security_barrier) AS
SELECT
  p.id, p.public_code, p.vertical, p.title, p.description, p.price_amount, p.currency, p.published_at,
  ga.id AS geo_area_id, ga.name AS locality, gp.name AS province,
  CASE WHEN p.agency_id IS NULL THEN 'particular' ELSE a.kind::text END AS seller_type,
  p.agency_id, a.trade_name AS agency_name, a.slug AS agency_slug, coalesce(a.status = 'verified', false) AS agency_verified,
  CASE WHEN p.agency_id IS NULL AND up.is_public THEN up.display_name END AS seller_display_name,
  (SELECT i.secure_url FROM app.post_images i WHERE i.post_id = p.id AND i.status = 'active' AND i.is_cover) AS cover_url,
  (SELECT jsonb_agg(jsonb_build_object('url', i.secure_url, 'position', i.position, 'is_cover', i.is_cover) ORDER BY i.position)
     FROM app.post_images i WHERE i.post_id = p.id AND i.status = 'active') AS images,
  -- taxis
  t.offer_kind AS taxi_offer_kind, t.service_type AS taxi_service_type, t.permit_number, t.permit_price, t.vehicle_price,
  cv.brand AS vehicle_brand, cv.model AS vehicle_model, cv.version AS vehicle_version, t.vehicle_year, t.fuel AS taxi_fuel,
  t.has_cng, t.has_meter, t.has_gps, t.equipment, t.includes_driver_work, (t.permit_verified_at IS NOT NULL) AS permit_verified,
  -- servicios
  s.category AS service_category, s.coverage_note, s.open_24h, s.at_home, s.vehicle_types, s.license_number,
  (s.license_verified_at IS NOT NULL) AS license_verified,
  -- repuestos
  r.category AS part_category, r.condition AS part_condition, r.brand_id AS part_brand_id, vb.name AS part_vehicle_brand,
  r.model_id AS part_model_id, vm.name AS part_vehicle_model, r.year_from AS part_year_from, r.year_to AS part_year_to,
  r.part_number, r.part_brand, r.in_stock,
  -- empleos
  j.role AS job_role, j.role_detail, j.license_required, j.license_classes, j.workday, j.modality, j.salary_min, j.salary_max, j.vacancies,
  p.search_vector
FROM app.posts p
JOIN app.geo_areas ga ON ga.id = p.geo_area_id
LEFT JOIN app.geo_areas gd ON gd.id = ga.parent_id
LEFT JOIN app.geo_areas gp ON gp.id = CASE WHEN ga.level = 'department' THEN ga.parent_id WHEN ga.level = 'locality' THEN gd.parent_id END
JOIN app.users u ON u.id = p.owner_user_id AND u.status = 'active'
LEFT JOIN app.user_profiles up ON up.user_id = p.owner_user_id
LEFT JOIN app.agencies a ON a.id = p.agency_id
LEFT JOIN app.taxi_posts t ON t.post_id = p.id
LEFT JOIN app.v_catalog_versions cv ON cv.version_id = t.version_id
LEFT JOIN app.service_posts s ON s.post_id = p.id
LEFT JOIN app.part_posts r ON r.post_id = p.id
LEFT JOIN app.vehicle_brands vb ON vb.id = r.brand_id
LEFT JOIN app.vehicle_models vm ON vm.id = r.model_id
LEFT JOIN app.job_posts j ON j.post_id = p.id
WHERE p.status = 'published' AND p.expires_at > now()
  AND (p.agency_id IS NULL OR a.status NOT IN ('suspended','revoked'))
  AND (p.vertical <> 'part' OR (a.status = 'verified' AND EXISTS (
        SELECT 1 FROM app.subscriptions x WHERE x.agency_id = p.agency_id AND app.subscription_grants(x))));
GRANT SELECT ON api_public.posts TO girando_anon, girando_app, girando_worker;

CREATE OR REPLACE VIEW api_public.sponsored WITH (security_barrier) AS
SELECT p.id AS promotion_id, p.type, p.placement, p.priority, p.disclosure_label,
       p.listing_id, p.target_agency_id, p.advertiser_name, p.creative_public_id, p.link_url,
       p.target_brand_id, p.target_model_id, p.target_geo_area_id, p.ends_at, p.target_vertical
FROM app.promotions p
WHERE p.status = 'active' AND now() BETWEEN p.starts_at AND p.ends_at
  AND (p.listing_id IS NULL OR EXISTS (SELECT 1 FROM api_public.listings pl WHERE pl.id = p.listing_id));

-- Una casa de repuestos no pasa a "verificada" sin la suscripción paga vigente (ni siquiera desde el Admin)
CREATE OR REPLACE FUNCTION app.tg_agencies_parts_gate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status = 'verified' AND OLD.status IS DISTINCT FROM 'verified' AND NEW.kind = 'parts_store'
     AND NOT app.agency_has_granting_subscription(NEW.id) THEN
    RAISE EXCEPTION 'PAGO_REQUERIDO_ANTES_DE_VERIFICAR' USING ERRCODE = 'GR409';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a1_agencies_parts_gate ON agencies;
CREATE TRIGGER a1_agencies_parts_gate BEFORE UPDATE OF status ON agencies FOR EACH ROW EXECUTE FUNCTION tg_agencies_parts_gate();

-- Alta de cuenta comercial: el usuario elige el rubro (agencia, repuestos, servicios, empresa).
-- "Concesionaria oficial" lo sigue asignando solo el staff. El rubro no se cambia después.
CREATE OR REPLACE FUNCTION app.tg_agencies_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF app.app_is_worker() OR pg_trigger_depth() > 1 OR app.app_has_staff_role('moderator','admin') THEN RETURN NEW; END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.status := 'pending'; NEW.verified_at := NULL; NEW.status_reason := NULL;
    IF NEW.kind = 'official_dealer' THEN NEW.kind := 'agency'; END IF;
    NEW.created_by := app.app_current_user_id();
    RETURN NEW;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status OR NEW.verified_at IS DISTINCT FROM OLD.verified_at
     OR NEW.status_reason IS DISTINCT FROM OLD.status_reason OR NEW.kind IS DISTINCT FROM OLD.kind
     OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'CAMPO_NO_EDITABLE' USING ERRCODE = 'GR403';
  END IF;
  IF OLD.status = 'verified' AND (NEW.cuit IS DISTINCT FROM OLD.cuit OR NEW.legal_name IS DISTINCT FROM OLD.legal_name) THEN
    RAISE EXCEPTION 'DATOS_FISCALES_VERIFICADOS: pedir cambio a soporte' USING ERRCODE = 'GR409';
  END IF;
  RETURN NEW;
END $$;
