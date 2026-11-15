-- =====================================================================
-- 160 · Roles (Admin vs Super Admin), suscripciones y Home (ex 0003, fase 3): Admin vs Super Admin, períodos de suscripción, plan manual,
--        Home administrable, verificación preparada, tracking de clics.
-- Idempotente donde se puede (IF NOT EXISTS / CREATE OR REPLACE / DROP POLICY IF EXISTS).
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- 1. Separación de permisos: lo comercial es del Super Admin (y de finance
--    cuando corresponde). "admin" queda para la operación diaria.
--    El backend valida primero; estas políticas son la última línea.
-- ---------------------------------------------------------------------
DROP POLICY IF EXISTS pl_admin_i ON plans;
DROP POLICY IF EXISTS pl_admin_u ON plans;
CREATE POLICY pl_admin_i ON plans FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));
CREATE POLICY pl_admin_u ON plans FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));

DROP POLICY IF EXISTS sub_select ON subscriptions;
CREATE POLICY sub_select ON subscriptions FOR SELECT TO girando_app USING (user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR app_has_staff_role('finance','support'));

-- Plan asignado a mano por el Super Admin (cortesía / convenio), siempre auditado
DROP POLICY IF EXISTS sub_staff_insert ON subscriptions;
CREATE POLICY sub_staff_insert ON subscriptions FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));

DROP POLICY IF EXISTS pay_select ON payments;
CREATE POLICY pay_select ON payments FOR SELECT TO girando_app USING (payer_user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR app_has_staff_role('finance'));
DROP POLICY IF EXISTS pe_select ON payment_events;
CREATE POLICY pe_select ON payment_events FOR SELECT TO girando_app USING (app_has_staff_role('finance'));

DROP POLICY IF EXISTS pp_admin_i ON promotion_products;
DROP POLICY IF EXISTS pp_admin_u ON promotion_products;
CREATE POLICY pp_admin_i ON promotion_products FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));
CREATE POLICY pp_admin_u ON promotion_products FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));

DROP POLICY IF EXISTS pr_insert ON promotions;
CREATE POLICY pr_insert ON promotions FOR INSERT TO girando_app WITH CHECK (
  (purchased_by = me() AND status = 'pending' AND approved_at IS NULL AND type <> 'banner_campaign'
   AND (listing_id IS NULL OR can_manage_listing_id(listing_id))
   AND (target_agency_id IS NULL OR app_is_agency_member(target_agency_id, 'owner','admin')))
  OR app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS pr_update ON promotions;
CREATE POLICY pr_update ON promotions FOR UPDATE TO girando_app
  USING (app_has_staff_role('superadmin')) WITH CHECK (app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS pev_insert ON promotion_events;
CREATE POLICY pev_insert ON promotion_events FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin') AND actor_user_id = me());

DROP POLICY IF EXISTS sa_select ON sales;
CREATE POLICY sa_select ON sales FOR SELECT TO girando_app USING (seller_user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id)) OR app_has_staff_role('finance'));

DROP POLICY IF EXISTS et_admin_i ON email_templates;
DROP POLICY IF EXISTS et_admin_u ON email_templates;
CREATE POLICY et_admin_i ON email_templates FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));
CREATE POLICY et_admin_u ON email_templates FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS ee_staff ON email_events;
CREATE POLICY ee_staff ON email_events FOR SELECT TO girando_app USING (app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS nt_admin ON notification_types;
CREATE POLICY nt_admin ON notification_types FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));

DROP POLICY IF EXISTS al_staff ON audit_logs;
CREATE POLICY al_staff ON audit_logs FOR SELECT TO girando_app USING (app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS ae_staff ON analytics_events;
CREATE POLICY ae_staff ON analytics_events FOR SELECT TO girando_app USING (app_has_staff_role('finance'));

DROP POLICY IF EXISTS as_admin_i ON app_settings;
DROP POLICY IF EXISTS as_admin_u ON app_settings;
CREATE POLICY as_admin_i ON app_settings FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));
CREATE POLICY as_admin_u ON app_settings FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));
DROP POLICY IF EXISTS rpol_admin ON retention_policies;
CREATE POLICY rpol_admin ON retention_policies FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));

DROP POLICY IF EXISTS vp_admin_i ON verification_products;
DROP POLICY IF EXISTS vp_admin_u ON verification_products;
CREATE POLICY vp_admin_i ON verification_products FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin'));
CREATE POLICY vp_admin_u ON verification_products FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin'));

-- ---------------------------------------------------------------------
-- 2. Eventos reales que faltaban para estadísticas
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ae_agency_idx ON analytics_events (agency_id, event_name, occurred_at) WHERE agency_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- 3. Períodos de suscripción por calendario (no "30 días")
--    Regla documentada en docs/05-suscripciones-y-periodos.md
-- ---------------------------------------------------------------------
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS billing_anchor_day smallint;
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS sub_anchor_day;
ALTER TABLE subscriptions ADD CONSTRAINT sub_anchor_day CHECK (billing_anchor_day IS NULL OR billing_anchor_day BETWEEN 1 AND 31);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS sub_notes_len;
ALTER TABLE subscriptions ADD CONSTRAINT sub_notes_len CHECK (notes IS NULL OR length(notes) <= 500);

-- Fin del período que empieza en p_start: mismo día de mes (ancla) en el mes siguiente
-- (o en el mismo mes del año siguiente), en hora de Argentina. Si el mes no tiene ese día,
-- se usa su último día (31-ene → 28/29-feb → 31-mar con ancla 31).
CREATE OR REPLACE FUNCTION app.next_period_end(p_start timestamptz, p_period app.billing_period, p_anchor_day int DEFAULT NULL)
RETURNS timestamptz LANGUAGE plpgsql STABLE AS $$
DECLARE
  tz constant text := 'America/Argentina/Buenos_Aires';
  l timestamp := p_start AT TIME ZONE tz;
  first_of_target date;
  last_day int;
  d int;
BEGIN
  IF p_start IS NULL OR p_period = 'none' THEN RETURN NULL; END IF;
  first_of_target := (date_trunc('month', l) + CASE p_period WHEN 'year' THEN interval '1 year' ELSE interval '1 month' END)::date;
  last_day := extract(day FROM (first_of_target + interval '1 month' - interval '1 day'))::int;
  d := least(coalesce(p_anchor_day, extract(day FROM l)::int), last_day);
  RETURN ((first_of_target + (d - 1)) + l::time) AT TIME ZONE tz;
END $$;

-- Un pago aprobado de suscripción extiende la cobertura. Idempotente: solo actúa en la
-- transición a 'approved' (ver trigger). Nunca acorta un período.
--   · Primera vez o suscripción vencida hace más de la gracia → arranca en la fecha del pago (nueva ancla).
--   · Renovación (pago entre 15 días antes y la gracia después del fin) → continúa desde el fin actual.
--   · Pago que cae dentro de un período ya informado por el proveedor → no duplica.
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
    v_start := s.current_period_end;                                   -- renovación continua
    v_anchor := coalesce(s.billing_anchor_day, extract(day FROM s.current_period_end AT TIME ZONE tz)::int);
  ELSIF s.current_period_end IS NOT NULL AND p_paid_at < s.current_period_end - make_interval(days => v_window) THEN
    v_start := coalesce(s.current_period_start, p_paid_at);            -- el período vigente ya está cubierto
    v_anchor := coalesce(s.billing_anchor_day, extract(day FROM v_start AT TIME ZONE tz)::int);
  ELSE
    v_start := p_paid_at;                                              -- alta o reactivación tras vencer
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
END $$;

CREATE OR REPLACE FUNCTION app.tg_payments_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.subscription_id IS NOT NULL AND NEW.status = 'approved'
     AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'approved') THEN
    PERFORM app.subscription_apply_payment(NEW.subscription_id, coalesce(NEW.paid_at, now()));
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS z_payments_effects ON payments;
CREATE TRIGGER z_payments_effects AFTER INSERT OR UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION tg_payments_effects();

-- ---------------------------------------------------------------------
-- 4. Agencias: tienda online (Tienda Nube u otra) además del sitio web
-- ---------------------------------------------------------------------
ALTER TABLE agencies ADD COLUMN IF NOT EXISTS store_url text;
ALTER TABLE agencies DROP CONSTRAINT IF EXISTS ag_store;
ALTER TABLE agencies ADD CONSTRAINT ag_store CHECK (store_url IS NULL OR store_url ~* '^https://\S+$');

CREATE OR REPLACE VIEW api_public.agencies WITH (security_barrier) AS
SELECT a.id, a.slug, a.kind, a.trade_name, a.description, a.logo_public_id, a.cover_public_id,
       a.phone_e164, a.whatsapp_e164, a.email::text AS email, a.website_url, a.instagram_url, a.facebook_url,
       a.tiktok_url, a.youtube_url, a.x_url, a.business_hours,
       loc.street, loc.street_number, ga.name AS locality, ga.id AS geo_area_id,
       (a.status = 'verified') AS is_verified, a.verified_at, date_part('year', a.created_at)::int AS member_since,
       r.girando_rating, r.girando_review_count,
       er.rating AS google_rating, er.review_count AS google_review_count, er.source_url AS google_url, er.synced_at AS google_synced_at,
       a.store_url
FROM app.agencies a
JOIN app.geo_areas ga ON ga.id = a.geo_area_id
LEFT JOIN app.locations loc ON loc.id = a.location_id
LEFT JOIN LATERAL (SELECT round(avg(rating)::numeric, 1) AS girando_rating, count(*) AS girando_review_count
                     FROM app.reviews WHERE reviewed_agency_id = a.id AND status = 'published') r ON true
LEFT JOIN app.external_ratings er ON er.agency_id = a.id AND er.provider = 'google' AND er.synced_at IS NOT NULL
WHERE a.status IN ('pending','review','verified','rejected');

-- ---------------------------------------------------------------------
-- 5. Verificación preparada para "Agencia Verificada por Girando"
--    El checklist es configurable por producto; las reglas definitivas se cargan después.
-- ---------------------------------------------------------------------
ALTER TABLE verification_products ADD COLUMN IF NOT EXISTS checklist_template jsonb NOT NULL DEFAULT '[]';
ALTER TABLE verification_products DROP CONSTRAINT IF EXISTS vp_checklist;
ALTER TABLE verification_products ADD CONSTRAINT vp_checklist CHECK (jsonb_typeof(checklist_template) = 'array');
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS checklist jsonb NOT NULL DEFAULT '[]';
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS evidence_notes text;
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS assigned_to uuid REFERENCES users(id);
ALTER TABLE verifications DROP CONSTRAINT IF EXISTS ver_checklist;
ALTER TABLE verifications ADD CONSTRAINT ver_checklist CHECK (jsonb_typeof(checklist) = 'array');
ALTER TABLE verifications DROP CONSTRAINT IF EXISTS ver_evidence_len;
ALTER TABLE verifications ADD CONSTRAINT ver_evidence_len CHECK (evidence_notes IS NULL OR length(evidence_notes) <= 4000);

-- Estado de verificación de una agencia tal como lo ve el producto:
-- none (nunca pidió) · pending · review · verified · rejected · suspended · revoked
CREATE OR REPLACE FUNCTION app.agency_verification_state(p_agency uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT CASE
    WHEN a.status = 'suspended' THEN 'suspended'
    WHEN a.status = 'verified' THEN 'verified'
    WHEN a.status = 'revoked' THEN 'revoked'
    WHEN v.status IS NULL THEN 'none'
    WHEN v.status = 'approved' THEN 'verified'
    ELSE v.status::text END
  FROM app.agencies a
  LEFT JOIN LATERAL (SELECT status FROM app.verifications WHERE subject_agency_id = a.id ORDER BY created_at DESC LIMIT 1) v ON true
  WHERE a.id = p_agency
$$;
GRANT EXECUTE ON FUNCTION app.agency_verification_state(uuid), app.next_period_end(timestamptz, app.billing_period, int) TO girando_app, girando_worker;
REVOKE EXECUTE ON FUNCTION app.subscription_apply_payment(uuid, timestamptz) FROM PUBLIC, girando_app;
GRANT EXECUTE ON FUNCTION app.subscription_apply_payment(uuid, timestamptz) TO girando_worker;

-- ---------------------------------------------------------------------
-- 6. Home administrable (solo lo que tiene sentido editar)
--    Contenido PROPIO de Girando. La publicidad paga va por promotions
--    (siempre rotulada "Patrocinado"/"Publicidad").
-- ---------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'home_block_kind' AND typnamespace = 'app'::regnamespace) THEN
    CREATE TYPE app.home_block_kind AS ENUM ('hero','announcement','cta');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'home_block_status' AND typnamespace = 'app'::regnamespace) THEN
    CREATE TYPE app.home_block_status AS ENUM ('draft','active','archived');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS home_blocks (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind             home_block_kind NOT NULL,
  status           home_block_status NOT NULL DEFAULT 'draft',
  title            text NOT NULL,
  body             text,
  image_public_id  text,
  cta_label        text,
  cta_target       text,
  sort_order       smallint NOT NULL DEFAULT 0,
  starts_at        timestamptz,
  ends_at          timestamptz,
  created_by       uuid NOT NULL REFERENCES users(id),
  updated_by       uuid REFERENCES users(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT hb_title CHECK (length(btrim(title)) BETWEEN 3 AND 90),
  CONSTRAINT hb_body CHECK (body IS NULL OR length(body) <= 280),
  CONSTRAINT hb_cta CHECK ((cta_label IS NULL) = (cta_target IS NULL) AND (cta_label IS NULL OR length(cta_label) BETWEEN 2 AND 30)),
  -- Destinos: pantallas internas conocidas o un https externo
  CONSTRAINT hb_target CHECK (cta_target IS NULL OR cta_target IN ('listado','publicar','planes','registro') OR cta_target ~* '^https://\S+$'),
  CONSTRAINT hb_dates CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS hb_active_idx ON home_blocks (kind, sort_order) WHERE status = 'active';
DROP TRIGGER IF EXISTS hb_updated ON home_blocks;
CREATE TRIGGER hb_updated BEFORE UPDATE ON home_blocks FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
DROP TRIGGER IF EXISTS zz_audit ON home_blocks;
CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON home_blocks FOR EACH ROW EXECUTE FUNCTION tg_audit_row();

ALTER TABLE home_blocks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS worker_all ON home_blocks;
CREATE POLICY worker_all ON home_blocks TO girando_worker USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS hb_staff ON home_blocks;
CREATE POLICY hb_staff ON home_blocks FOR ALL TO girando_app
  USING (app_has_staff_role('superadmin')) WITH CHECK (app_has_staff_role('superadmin'));
GRANT SELECT, INSERT, UPDATE ON home_blocks TO girando_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON home_blocks TO girando_worker;

CREATE OR REPLACE VIEW api_public.home_blocks WITH (security_barrier) AS
SELECT id, kind, title, body, image_public_id, cta_label, cta_target, sort_order
FROM app.home_blocks
WHERE status = 'active' AND (starts_at IS NULL OR starts_at <= now()) AND (ends_at IS NULL OR ends_at > now());
GRANT SELECT ON api_public.home_blocks TO girando_anon, girando_app, girando_worker;
