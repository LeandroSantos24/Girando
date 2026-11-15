-- =====================================================================
-- 170 · Marketplace (ex 0005, fase 4): carrocería, color, precio normalizado,
--        historial de precio público y FINANCIACIÓN POR ENTIDAD.
-- Regla: la financiación es un dato estructurado y moderado, nunca texto libre.
-- Si hay tasa, van las tres (TNA, TEA y CFT); si no hay tasa, no se inventa.
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- 1. Carrocería: 'chassis' (chasis cabina) pasa a 'light_truck'. El valor viejo
--    queda en el enum (PostgreSQL no borra valores) pero ya no se ofrece.
-- ---------------------------------------------------------------------
UPDATE vehicle_versions SET body_type = 'light_truck' WHERE body_type = 'chassis';
UPDATE vehicle_models SET default_body_type = 'light_truck' WHERE default_body_type = 'chassis';

-- ---------------------------------------------------------------------
-- 2. Color como dato filtrable (el texto libre `color` se conserva para mostrar)
-- ---------------------------------------------------------------------
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS color_family text;
ALTER TABLE vehicles DROP CONSTRAINT IF EXISTS veh_color_family;
ALTER TABLE vehicles ADD CONSTRAINT veh_color_family CHECK (color_family IS NULL OR color_family IN
  ('white','black','gray','silver','red','blue','green','yellow','orange','brown','beige','gold','violet','other'));
COMMENT ON COLUMN vehicles.color_family IS '[PÚBLICO] Color normalizado para filtrar. El vendedor lo elige de una lista.';

-- ---------------------------------------------------------------------
-- 3. Entidades de financiación (bancos, financieras, terminales)
-- ---------------------------------------------------------------------
DO $$ BEGIN
  CREATE TYPE financing_entity_kind AS ENUM ('bank','finance_company','automaker','savings_plan_admin','other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE financing_offer_status AS ENUM ('draft','pending','approved','rejected','paused');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE rate_kind AS ENUM ('fixed','variable','mixed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS financing_entities (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               text NOT NULL UNIQUE,
  name               text NOT NULL,
  kind               financing_entity_kind NOT NULL DEFAULT 'bank',
  website_url        text,
  logo_authorized    boolean NOT NULL DEFAULT false,
  logo_public_id     text,
  logo_authorization_note text,
  is_active          boolean NOT NULL DEFAULT true,
  created_by         uuid REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fe_slug CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,60}$'),
  CONSTRAINT fe_name CHECK (length(btrim(name)) BETWEEN 2 AND 80),
  CONSTRAINT fe_web CHECK (website_url IS NULL OR website_url ~* '^https://\S+$'),
  -- El logo solo existe si la entidad lo autorizó, y la autorización tiene que estar anotada
  CONSTRAINT fe_logo_needs_authorization CHECK (logo_public_id IS NULL OR logo_authorized),
  CONSTRAINT fe_authorization_note CHECK (NOT logo_authorized OR length(btrim(coalesce(logo_authorization_note, ''))) >= 5)
);
COMMENT ON TABLE financing_entities IS '[PÚBLICO] Entidades que financian. El logo se muestra solo con logo_authorized = true; si no, va el nombre en texto.';
COMMENT ON COLUMN financing_entities.logo_authorization_note IS '[ADMIN] Quién autorizó el uso de la marca y cuándo (referencia del convenio o del email).';

-- ---------------------------------------------------------------------
-- 4. Ofertas de financiación
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financing_offers (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id                uuid REFERENCES financing_entities(id),
  agency_id                uuid REFERENCES agencies(id),
  created_by               uuid NOT NULL REFERENCES users(id),
  type                     financing_type NOT NULL,
  title                    text NOT NULL,
  currency                 currency_code NOT NULL DEFAULT 'ARS',
  min_down_payment_pct     numeric(5,2),
  min_down_payment_amount  numeric(14,2),
  max_financed_pct         numeric(5,2),
  max_financed_amount      numeric(14,2),
  terms_months             smallint[] NOT NULL,
  tna                      numeric(7,2),
  tea                      numeric(7,2),
  cft                      numeric(7,2),
  rate_kind                rate_kind,
  applies_to_condition     vehicle_condition,
  max_vehicle_age_years    smallint,
  applies_to_all           boolean NOT NULL DEFAULT false,
  valid_from               date NOT NULL DEFAULT current_date,
  valid_until              date NOT NULL,
  conditions               text,
  source                   text NOT NULL,
  source_url               text,
  status                   financing_offer_status NOT NULL DEFAULT 'draft',
  status_reason            text,
  reviewed_by              uuid REFERENCES users(id),
  reviewed_at              timestamptz,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fo_title CHECK (length(btrim(title)) BETWEEN 3 AND 80),
  -- "Propio de la agencia" no necesita entidad; el resto sí
  CONSTRAINT fo_entity CHECK (entity_id IS NOT NULL OR (type = 'dealer_financing' AND agency_id IS NOT NULL)),
  CONSTRAINT fo_pcts CHECK ((min_down_payment_pct IS NULL OR min_down_payment_pct BETWEEN 0 AND 100)
                        AND (max_financed_pct IS NULL OR (max_financed_pct > 0 AND max_financed_pct <= 100))),
  CONSTRAINT fo_amounts CHECK ((min_down_payment_amount IS NULL OR min_down_payment_amount >= 0)
                           AND (max_financed_amount IS NULL OR max_financed_amount > 0)),
  CONSTRAINT fo_terms CHECK (cardinality(terms_months) BETWEEN 1 AND 12 AND 1 <= ALL (terms_months) AND 120 >= ALL (terms_months)),
  -- Tasas: las tres o ninguna (TNA, TEA y CFT) + si es fija o variable
  CONSTRAINT fo_rates_all_or_none CHECK (num_nonnulls(tna, tea, cft) IN (0, 3) AND ((tna IS NULL) = (rate_kind IS NULL))),
  CONSTRAINT fo_rates_range CHECK ((tna IS NULL OR tna BETWEEN 0 AND 999) AND (tea IS NULL OR tea BETWEEN 0 AND 9999) AND (cft IS NULL OR cft BETWEEN 0 AND 9999)),
  CONSTRAINT fo_rates_coherent CHECK (tna IS NULL OR (tea >= tna AND cft >= tna)),
  CONSTRAINT fo_validity CHECK (valid_until >= valid_from AND valid_until <= valid_from + 400),
  CONSTRAINT fo_age CHECK (max_vehicle_age_years IS NULL OR max_vehicle_age_years BETWEEN 0 AND 40),
  CONSTRAINT fo_conditions CHECK (conditions IS NULL OR length(conditions) <= 2000),
  CONSTRAINT fo_source CHECK (length(btrim(source)) BETWEEN 3 AND 300),
  CONSTRAINT fo_source_url CHECK (source_url IS NULL OR source_url ~* '^https://\S+$'),
  CONSTRAINT fo_all_needs_agency CHECK (NOT applies_to_all OR agency_id IS NOT NULL),
  CONSTRAINT fo_reviewed CHECK (status NOT IN ('approved','rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CONSTRAINT fo_reject_reason CHECK (status <> 'rejected' OR status_reason IS NOT NULL)
);
COMMENT ON TABLE financing_offers IS 'Oferta de financiación de una entidad. agency_id NULL = cargada por Girando (convenio). Solo se muestra si status = approved y está vigente.';
COMMENT ON COLUMN financing_offers.source IS '[PÚBLICO] De dónde sale la información (web de la entidad, convenio, lista de la agencia).';
CREATE INDEX IF NOT EXISTS fo_agency_idx ON financing_offers (agency_id, status);
CREATE INDEX IF NOT EXISTS fo_queue_idx ON financing_offers (created_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS fo_visible_idx ON financing_offers (valid_until) WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS listing_financing_offers (
  listing_id  uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  offer_id    uuid NOT NULL REFERENCES financing_offers(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (listing_id, offer_id)
);
CREATE INDEX IF NOT EXISTS lfo_offer_idx ON listing_financing_offers (offer_id);

-- Guardas: quién puede crear/editar y cómo se aprueba
CREATE OR REPLACE FUNCTION app.tg_financing_offers_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE
  is_mod boolean := app.app_has_staff_role('moderator','admin');
  is_owner boolean;
BEGIN
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  is_owner := CASE WHEN NEW.agency_id IS NOT NULL THEN app.app_is_agency_member(NEW.agency_id, 'owner','admin')
                   ELSE app.app_has_staff_role('admin') END;
  IF TG_OP = 'INSERT' THEN
    IF NOT is_owner THEN RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403'; END IF;
    IF NEW.status NOT IN ('draft','pending') THEN RAISE EXCEPTION 'LA_OFERTA_NACE_SIN_APROBAR' USING ERRCODE = 'GR403'; END IF;
    NEW.created_by := app.app_current_user_id();
    NEW.reviewed_by := NULL; NEW.reviewed_at := NULL;
    RETURN NEW;
  END IF;
  IF NEW.agency_id IS DISTINCT FROM OLD.agency_id OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
    RAISE EXCEPTION 'CAMPO_NO_EDITABLE' USING ERRCODE = 'GR403';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NEW.status IN ('approved','rejected') THEN
      IF NOT is_mod THEN RAISE EXCEPTION 'SOLO_MODERACION_APRUEBA' USING ERRCODE = 'GR403'; END IF;
      IF OLD.status NOT IN ('pending','approved','rejected') THEN RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA' USING ERRCODE = 'GR403'; END IF;
      IF NEW.status = 'rejected' AND (NEW.status_reason IS NULL OR btrim(NEW.status_reason) = '') THEN
        RAISE EXCEPTION 'MOTIVO_OBLIGATORIO' USING ERRCODE = 'GR422';
      END IF;
      NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now();
      IF NEW.status = 'approved' THEN NEW.status_reason := NULL; END IF;
    ELSIF NOT (is_owner OR is_mod) THEN
      RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
    ELSIF NOT ((OLD.status || '>' || NEW.status) = ANY (ARRAY['draft>pending','pending>draft','rejected>pending','approved>paused','paused>pending','rejected>draft'])) THEN
      RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA' USING ERRCODE = 'GR403';
    END IF;
  ELSIF NOT (is_owner OR is_mod) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  -- Cambiar las condiciones de una oferta ya aprobada la devuelve a revisión
  IF OLD.status = 'approved' AND NEW.status = 'approved' AND NOT is_mod AND
     (NEW.entity_id, NEW.type, NEW.title, NEW.currency, NEW.min_down_payment_pct, NEW.min_down_payment_amount, NEW.max_financed_pct,
      NEW.max_financed_amount, NEW.terms_months, NEW.tna, NEW.tea, NEW.cft, NEW.rate_kind, NEW.valid_from, NEW.valid_until, NEW.conditions,
      NEW.source, NEW.source_url, NEW.applies_to_condition, NEW.max_vehicle_age_years)
     IS DISTINCT FROM
     (OLD.entity_id, OLD.type, OLD.title, OLD.currency, OLD.min_down_payment_pct, OLD.min_down_payment_amount, OLD.max_financed_pct,
      OLD.max_financed_amount, OLD.terms_months, OLD.tna, OLD.tea, OLD.cft, OLD.rate_kind, OLD.valid_from, OLD.valid_until, OLD.conditions,
      OLD.source, OLD.source_url, OLD.applies_to_condition, OLD.max_vehicle_age_years) THEN
    NEW.status := 'pending'; NEW.reviewed_by := NULL; NEW.reviewed_at := NULL;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a_financing_offers_guard ON financing_offers;
CREATE TRIGGER a_financing_offers_guard BEFORE INSERT OR UPDATE ON financing_offers FOR EACH ROW EXECUTE FUNCTION tg_financing_offers_guard();

-- Una publicación solo puede usar ofertas de su propia agencia o de Girando
CREATE OR REPLACE FUNCTION app.tg_listing_financing_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE l app.listings; o app.financing_offers;
BEGIN
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  SELECT * INTO l FROM app.listings WHERE id = NEW.listing_id;
  SELECT * INTO o FROM app.financing_offers WHERE id = NEW.offer_id;
  IF l.id IS NULL OR o.id IS NULL OR NOT app.can_manage_listing(l.owner_user_id, l.agency_id) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  IF o.agency_id IS NOT NULL AND o.agency_id IS DISTINCT FROM l.agency_id THEN
    RAISE EXCEPTION 'OFERTA_DE_OTRA_AGENCIA' USING ERRCODE = 'GR403';
  END IF;
  IF o.agency_id IS NULL AND o.status <> 'approved' THEN
    RAISE EXCEPTION 'OFERTA_NO_DISPONIBLE' USING ERRCODE = 'GR409';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a_listing_financing_guard ON listing_financing_offers;
CREATE TRIGGER a_listing_financing_guard BEFORE INSERT ON listing_financing_offers FOR EACH ROW EXECUTE FUNCTION tg_listing_financing_guard();

DROP TRIGGER IF EXISTS fe_updated ON financing_entities;
CREATE TRIGGER fe_updated BEFORE UPDATE ON financing_entities FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
DROP TRIGGER IF EXISTS fo_updated ON financing_offers;
CREATE TRIGGER fo_updated BEFORE UPDATE ON financing_offers FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
DROP TRIGGER IF EXISTS zz_audit ON financing_entities;
CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON financing_entities FOR EACH ROW EXECUTE FUNCTION tg_audit_row();
DROP TRIGGER IF EXISTS zz_audit ON financing_offers;
CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON financing_offers FOR EACH ROW EXECUTE FUNCTION tg_audit_row();

-- RLS + grants
ALTER TABLE financing_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE financing_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE listing_financing_offers ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['financing_entities','financing_offers','listing_financing_offers'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS worker_all ON app.%I', t);
    EXECUTE format('CREATE POLICY worker_all ON app.%I TO girando_worker USING (true) WITH CHECK (true)', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON app.%I TO girando_app', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON app.%I TO girando_worker', t);
  END LOOP;
END $$;
GRANT DELETE ON listing_financing_offers TO girando_app;

DROP POLICY IF EXISTS fe_read ON financing_entities;
CREATE POLICY fe_read ON financing_entities FOR SELECT TO girando_app USING (is_active OR app_is_staff());
DROP POLICY IF EXISTS fe_admin_i ON financing_entities;
CREATE POLICY fe_admin_i ON financing_entities FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
DROP POLICY IF EXISTS fe_admin_u ON financing_entities;
CREATE POLICY fe_admin_u ON financing_entities FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));

DROP POLICY IF EXISTS fo_select ON financing_offers;
CREATE POLICY fo_select ON financing_offers FOR SELECT TO girando_app USING (
  (agency_id IS NOT NULL AND app_is_agency_member(agency_id)) OR app_is_staff()
  OR (agency_id IS NULL AND status = 'approved'));
DROP POLICY IF EXISTS fo_insert ON financing_offers;
CREATE POLICY fo_insert ON financing_offers FOR INSERT TO girando_app WITH CHECK (
  (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR (agency_id IS NULL AND app_has_staff_role('admin')));
DROP POLICY IF EXISTS fo_update ON financing_offers;
CREATE POLICY fo_update ON financing_offers FOR UPDATE TO girando_app USING (
  (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR is_mod() OR (agency_id IS NULL AND app_has_staff_role('admin')))
  WITH CHECK (true);

DROP POLICY IF EXISTS lfo_select ON listing_financing_offers;
CREATE POLICY lfo_select ON listing_financing_offers FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());
DROP POLICY IF EXISTS lfo_insert ON listing_financing_offers;
CREATE POLICY lfo_insert ON listing_financing_offers FOR INSERT TO girando_app WITH CHECK (can_manage_listing_id(listing_id));
DROP POLICY IF EXISTS lfo_delete ON listing_financing_offers;
CREATE POLICY lfo_delete ON listing_financing_offers FOR DELETE TO girando_app USING (can_manage_listing_id(listing_id));

-- ---------------------------------------------------------------------
-- 5. Cuota orientativa (sistema francés sobre TNA). Es un cálculo de referencia:
--    no incluye gastos, seguros ni impuestos (eso lo refleja el CFT informado).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.financing_installment(p_principal numeric, p_tna numeric, p_months int) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN p_principal IS NULL OR p_tna IS NULL OR p_months IS NULL OR p_months <= 0 OR p_principal <= 0 THEN NULL
    WHEN p_tna = 0 THEN round(p_principal / p_months, 2)
    ELSE round(p_principal * (p_tna / 1200.0) / (1 - power(1 + p_tna / 1200.0, -p_months)), 2)
  END
$$;
GRANT EXECUTE ON FUNCTION app.financing_installment(numeric, numeric, int) TO girando_anon, girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- 6. Vistas públicas
-- ---------------------------------------------------------------------
-- 6.1 Publicaciones: se agregan color_family y price_ars (precio llevado a pesos con la última
--     cotización BCRA cargada; NULL si la publicación está en USD y no hay cotización).
CREATE OR REPLACE VIEW api_public.listings WITH (security_barrier) AS
SELECT
  l.id, l.public_code, l.title, l.description,
  l.price_amount, l.currency, l.condition, l.km,
  l.is_financeable, l.accepts_trade_in, l.video_url,
  l.published_at, l.first_published_at,
  cv.brand_id, cv.brand, cv.model_id, cv.model, cv.generation_id, cv.generation, cv.version_id, cv.version,
  cv.vehicle_type, cv.body_type, cv.doors, cv.seats, cv.transmission, cv.gears, cv.traction, cv.segment,
  e.name AS engine, e.displacement_cc, e.power_hp, coalesce(v.fuel_override, e.fuel) AS fuel,
  v.year, v.color,
  ga.id AS geo_area_id, ga.name AS locality, gp.name AS province, ga.centroid_lat, ga.centroid_lng,
  CASE WHEN l.show_neighborhood THEN loc.neighborhood END AS neighborhood,
  CASE WHEN l.agency_id IS NULL THEN 'particular' ELSE a.kind::text END AS seller_type,
  l.agency_id, a.trade_name AS agency_name, a.slug AS agency_slug, (a.status = 'verified') AS agency_verified,
  CASE WHEN l.agency_id IS NULL AND up.is_public THEN up.display_name END AS seller_display_name,
  CASE WHEN l.agency_id IS NULL THEN (u.identity_verified_at IS NOT NULL) END AS seller_identity_verified,
  (SELECT jsonb_agg(jsonb_build_object('public_id', i.public_id, 'url', i.secure_url, 'provider', i.storage_provider, 'kind', i.kind, 'position', i.position,
                                       'is_cover', i.is_cover, 'width', i.width, 'height', i.height) ORDER BY i.position)
     FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active') AS images,
  (SELECT i.public_id FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_public_id,
  (SELECT i.secure_url FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_url,
  l.search_vector,
  v.color_family,
  CASE WHEN l.currency = 'ARS' THEN l.price_amount
       ELSE round(l.price_amount * (SELECT x.rate_to_ars FROM app.exchange_rates x WHERE x.currency = l.currency ORDER BY x.valid_on DESC LIMIT 1), 2) END AS price_ars
FROM app.listings l
JOIN app.vehicles v ON v.id = l.vehicle_id
JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
JOIN app.vehicle_engines e ON e.id = v.engine_id
JOIN app.geo_areas ga ON ga.id = l.geo_area_id
LEFT JOIN app.geo_areas gd ON gd.id = ga.parent_id
LEFT JOIN app.geo_areas gp ON gp.id = CASE WHEN ga.level = 'department' THEN ga.parent_id WHEN ga.level = 'locality' THEN gd.parent_id END
LEFT JOIN app.locations loc ON loc.id = l.location_id
JOIN app.users u ON u.id = l.owner_user_id AND u.status = 'active'
LEFT JOIN app.user_profiles up ON up.user_id = l.owner_user_id
LEFT JOIN app.agencies a ON a.id = l.agency_id
WHERE l.status = 'published'
  AND l.expires_at > now()
  AND (l.agency_id IS NULL OR a.status NOT IN ('suspended','revoked'));

-- 6.2 Entidades (el logo sale solo si está autorizado)
CREATE OR REPLACE VIEW api_public.financing_entities AS
SELECT id, slug, name, kind, website_url, logo_authorized,
       CASE WHEN logo_authorized THEN logo_public_id END AS logo_public_id
FROM app.financing_entities WHERE is_active;

-- 6.3 Ofertas visibles: aprobadas y vigentes
CREATE OR REPLACE VIEW api_public.financing_offers WITH (security_barrier) AS
SELECT o.id, o.agency_id, o.entity_id, coalesce(e.name, a.trade_name) AS entity_name, e.kind AS entity_kind,
       coalesce(e.logo_authorized, false) AS logo_authorized,
       CASE WHEN e.logo_authorized THEN e.logo_public_id END AS logo_public_id,
       o.type, o.title, o.currency, o.min_down_payment_pct, o.min_down_payment_amount, o.max_financed_pct, o.max_financed_amount,
       o.terms_months, o.tna, o.tea, o.cft, o.rate_kind, o.applies_to_condition, o.max_vehicle_age_years, o.applies_to_all,
       o.valid_from, o.valid_until, o.conditions, o.source, o.source_url
FROM app.financing_offers o
LEFT JOIN app.financing_entities e ON e.id = o.entity_id
LEFT JOIN app.agencies a ON a.id = o.agency_id
WHERE o.status = 'approved' AND current_date BETWEEN o.valid_from AND o.valid_until
  AND (e.id IS NULL OR e.is_active);

-- 6.4 Ofertas por publicación con los números "con cuánto lo retirás" ya calculados.
--     Solo se calculan montos cuando la moneda de la oferta coincide con la de la publicación.
CREATE OR REPLACE VIEW api_public.listing_financing WITH (security_barrier) AS
SELECT pl.id AS listing_id, o.*,
       c.down_payment, c.financed_amount,
       (SELECT max(t) FROM unnest(o.terms_months) t) AS term_max,
       app.financing_installment(c.financed_amount, o.tna, (SELECT max(t)::int FROM unnest(o.terms_months) t)) AS installment_min
FROM api_public.listings pl
JOIN api_public.financing_offers o
  ON (EXISTS (SELECT 1 FROM app.listing_financing_offers x WHERE x.listing_id = pl.id AND x.offer_id = o.id)
      OR (o.applies_to_all AND o.agency_id = pl.agency_id))
 AND (o.applies_to_condition IS NULL OR o.applies_to_condition = pl.condition)
 AND (o.max_vehicle_age_years IS NULL OR pl.year >= extract(year FROM current_date)::int - o.max_vehicle_age_years)
LEFT JOIN LATERAL (
  SELECT CASE WHEN o.currency = pl.currency THEN pl.price_amount - f.fin END AS down_payment,
         CASE WHEN o.currency = pl.currency THEN f.fin END AS financed_amount
  FROM (SELECT greatest(0, least(
                 pl.price_amount - greatest(coalesce(o.min_down_payment_amount, 0), pl.price_amount * coalesce(o.min_down_payment_pct, 0) / 100),
                 coalesce(o.max_financed_amount, pl.price_amount),
                 pl.price_amount * coalesce(o.max_financed_pct, 100) / 100)) AS fin) f
) c ON true;

-- 6.5 Historial de precio de publicaciones visibles (sin quién lo cambió)
CREATE OR REPLACE VIEW api_public.listing_price_history WITH (security_barrier) AS
SELECT h.listing_id, h.old_amount, h.old_currency, h.new_amount, h.new_currency, h.created_at
FROM app.listing_price_history h
JOIN api_public.listings pl ON pl.id = h.listing_id;

GRANT SELECT ON api_public.financing_entities, api_public.financing_offers, api_public.listing_financing, api_public.listing_price_history
  TO girando_anon, girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- 7. Favoritos: avisar cuando baja el precio o se vende
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_listing_favorites_notify() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE f record;
BEGIN
  IF NEW.status = 'published' AND OLD.status = 'published' AND NEW.currency = OLD.currency
     AND NEW.price_amount < OLD.price_amount THEN
    FOR f IN SELECT user_id FROM app.favorites WHERE listing_id = NEW.id LOOP
      PERFORM app.enqueue_notification(f.user_id, 'favorite.price_drop', 'Bajó de precio un vehículo que guardaste',
                                       NEW.title, 'listing', NEW.id, '/v/' || NEW.public_code);
    END LOOP;
  ELSIF NEW.status = 'sold' AND OLD.status <> 'sold' THEN
    FOR f IN SELECT user_id FROM app.favorites WHERE listing_id = NEW.id LOOP
      PERFORM app.enqueue_notification(f.user_id, 'favorite.sold', 'Se vendió un vehículo que guardaste',
                                       NEW.title, 'listing', NEW.id, NULL);
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS zy_listing_favorites_notify ON listings;
CREATE TRIGGER zy_listing_favorites_notify AFTER UPDATE OF price_amount, status ON listings
  FOR EACH ROW EXECUTE FUNCTION tg_listing_favorites_notify();

-- Índices para los filtros nuevos
CREATE INDEX IF NOT EXISTS vehicles_color_family_idx ON vehicles (color_family) WHERE color_family IS NOT NULL;
CREATE INDEX IF NOT EXISTS vehicles_year_idx ON vehicles (year);

-- Última cotización cargada (para normalizar el filtro de precio entre pesos y dólares)
CREATE OR REPLACE VIEW api_public.exchange_rate AS
SELECT DISTINCT ON (currency) currency, rate_to_ars, source, valid_on
FROM app.exchange_rates ORDER BY currency, valid_on DESC;
GRANT SELECT ON api_public.exchange_rate TO girando_anon, girando_app, girando_worker;
