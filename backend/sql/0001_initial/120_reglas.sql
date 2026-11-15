-- =====================================================================
-- 120 · Reglas de negocio en la base (última línea de defensa)
-- El backend valida primero y devuelve errores amigables; estos
-- triggers garantizan que ni un bug ni un cliente malicioso rompan
-- invariantes. Códigos de error propios:
--   GR403 acción no permitida para el actor
--   GR409 límite / conflicto de estado (p.ej. LIMITE_ALCANZADO)
--   GR422 datos inválidos para la transición
--   GR429 anti-spam
-- Los triggers BEFORE se disparan en orden alfabético: a_* (guardas)
-- antes que b_* (máquinas de estado).
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- Plan efectivo y límite de publicaciones
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.subscription_grants(s app.subscriptions) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT s.status IN ('active','payment_failed','grace_period')
      OR (s.status = 'canceled' AND s.current_period_end > now())
$$;

CREATE OR REPLACE FUNCTION app.effective_plan(p_user uuid, p_agency uuid) RETURNS app.plans
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = app, public AS $$
DECLARE r app.plans;
BEGIN
  SELECT p.* INTO r
  FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id
  WHERE (CASE WHEN p_agency IS NOT NULL THEN s.agency_id = p_agency ELSE s.user_id = p_user END)
    AND app.subscription_grants(s)
  ORDER BY s.created_at DESC LIMIT 1;
  IF NOT FOUND THEN
    SELECT * INTO r FROM app.plans WHERE audience = 'particular' AND is_default_for_audience AND is_active;
  END IF;
  RETURN r;
END $$;

CREATE OR REPLACE FUNCTION app.tg_listing_limit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_plan app.plans; v_used int;
BEGIN
  IF NEW.status NOT IN ('pending','published') THEN RETURN NEW; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status IN ('pending','published') THEN RETURN NEW; END IF;
  PERFORM pg_advisory_xact_lock(hashtext('listing_limit:' || coalesce(NEW.agency_id, NEW.owner_user_id)::text));
  v_plan := app.effective_plan(NEW.owner_user_id, NEW.agency_id);
  IF v_plan.id IS NULL THEN
    RAISE EXCEPTION 'PLAN_NO_CONFIGURADO' USING ERRCODE = 'GR409';
  END IF;
  SELECT count(*) INTO v_used FROM app.listings l
   WHERE l.status IN ('pending','published') AND l.id <> NEW.id
     AND (CASE WHEN NEW.agency_id IS NOT NULL THEN l.agency_id = NEW.agency_id
               ELSE l.owner_user_id = NEW.owner_user_id AND l.agency_id IS NULL END);
  IF v_used >= v_plan.max_active_listings THEN
    RAISE EXCEPTION 'LIMITE_ALCANZADO' USING ERRCODE = 'GR409',
      DETAIL = format('plan=%s limite=%s usadas=%s', v_plan.code, v_plan.max_active_listings, v_used);
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER c_listing_limit BEFORE INSERT OR UPDATE OF status ON listings
  FOR EACH ROW EXECUTE FUNCTION tg_listing_limit();

-- ---------------------------------------------------------------------
-- ¿El usuario actual puede operar esta publicación como dueño?
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.can_manage_listing(p_owner uuid, p_agency uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT CASE WHEN p_agency IS NOT NULL THEN app.app_is_agency_member(p_agency)
              ELSE p_owner = app.app_current_user_id() END
$$;

-- ---------------------------------------------------------------------
-- Guarda de columnas privilegiadas de listings + renovación
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_listing_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  privileged boolean := app.app_is_worker() OR app.app_has_staff_role('moderator','admin');
  v_days int := app.setting_int('listings.duration_days', 60);
  v_notice int := app.setting_int('listings.expiry_notice_days', 3);
BEGIN
  IF OLD.status IN ('sold','deleted') AND NOT app.app_is_worker() THEN
    RAISE EXCEPTION 'PUBLICACION_CERRADA' USING ERRCODE = 'GR409';
  END IF;
  IF NOT privileged THEN
    IF NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id OR NEW.agency_id IS DISTINCT FROM OLD.agency_id
       OR NEW.created_by IS DISTINCT FROM OLD.created_by OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
       OR NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at
       OR NEW.duplicate_of_listing_id IS DISTINCT FROM OLD.duplicate_of_listing_id
       OR NEW.first_published_at IS DISTINCT FROM OLD.first_published_at OR NEW.published_at IS DISTINCT FROM OLD.published_at
       OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at OR NEW.sold_at IS DISTINCT FROM OLD.sold_at
       OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at OR NEW.paused_at IS DISTINCT FROM OLD.paused_at
       OR NEW.renewal_count IS DISTINCT FROM OLD.renewal_count OR NEW.public_code IS DISTINCT FROM OLD.public_code
       OR (NEW.status_reason IS DISTINCT FROM OLD.status_reason AND NEW.status = OLD.status) THEN
      RAISE EXCEPTION 'CAMPO_NO_EDITABLE' USING ERRCODE = 'GR403';
    END IF;
    -- Renovación: el dueño solo puede extender expires_at dentro de la ventana de aviso
    IF NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
      IF OLD.status <> 'published' OR OLD.expires_at > now() + make_interval(days => v_notice) THEN
        RAISE EXCEPTION 'RENOVACION_NO_DISPONIBLE' USING ERRCODE = 'GR409';
      END IF;
      NEW.expires_at := now() + make_interval(days => v_days);
      NEW.renewal_count := OLD.renewal_count + 1;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_listing_guard BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION tg_listing_guard();

-- ---------------------------------------------------------------------
-- Máquina de estados de listings
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_listing_state() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE
  t text := OLD.status || '>' || NEW.status;
  is_worker boolean := app.app_is_worker();
  is_mod boolean := app.app_has_staff_role('moderator','admin');
  is_owner boolean := app.can_manage_listing(OLD.owner_user_id, OLD.agency_id);
  owner_moves text[] := ARRAY['draft>pending','draft>deleted','pending>draft',
    'published>paused','published>sold','published>deleted',
    'paused>pending','paused>sold','paused>deleted',
    'expired>pending','expired>sold','expired>deleted',
    'requires_changes>pending','requires_changes>deleted','rejected>pending','rejected>deleted'];
  staff_moves text[] := ARRAY['pending>published','pending>rejected','pending>requires_changes',
    'requires_changes>published','published>requires_changes','published>paused',
    'paused>published','paused>deleted','rejected>deleted','published>deleted'];
  system_moves text[] := ARRAY['published>expired','published>paused'];
  v_ver record;
  v_days int := app.setting_int('listings.duration_days', 60);
BEGIN
  IF NEW.status = OLD.status THEN RETURN NEW; END IF;

  IF NOT ((is_owner AND t = ANY (owner_moves)) OR (is_mod AND t = ANY (staff_moves)) OR (is_worker AND t = ANY (system_moves))) THEN
    RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA %', t USING ERRCODE = 'GR403';
  END IF;

  IF NEW.status IN ('requires_changes','rejected') OR (is_mod AND t IN ('published>paused','paused>deleted','rejected>deleted','published>deleted')) THEN
    IF NEW.status_reason IS NULL OR NEW.status_reason = OLD.status_reason THEN
      RAISE EXCEPTION 'MOTIVO_OBLIGATORIO' USING ERRCODE = 'GR422';
    END IF;
  END IF;

  -- Requisitos para enviar a revisión
  IF NEW.status = 'pending' THEN
    SELECT v.version_id, v.engine_id, v.year, cv.year_from, cv.year_to, cv.is_active
      INTO v_ver
      FROM app.vehicles v LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
     WHERE v.id = NEW.vehicle_id;
    IF v_ver.version_id IS NULL OR v_ver.engine_id IS NULL OR v_ver.year IS NULL THEN
      RAISE EXCEPTION 'VEHICULO_INCOMPLETO' USING ERRCODE = 'GR422';
    END IF;
    IF NOT v_ver.is_active AND OLD.status = 'draft' THEN
      RAISE EXCEPTION 'VERSION_INACTIVA' USING ERRCODE = 'GR422';
    END IF;
    IF v_ver.year < v_ver.year_from - 1 OR (v_ver.year_to IS NOT NULL AND v_ver.year > v_ver.year_to + 1) THEN
      RAISE EXCEPTION 'ANIO_FUERA_DE_RANGO' USING ERRCODE = 'GR422';
    END IF;
    NEW.submitted_at := now();
  END IF;

  IF NEW.status = 'published' THEN
    NEW.published_at := now();
    NEW.first_published_at := coalesce(OLD.first_published_at, now());
    NEW.expires_at := now() + make_interval(days => v_days);
    IF is_mod THEN NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now(); END IF;
  ELSIF NEW.status IN ('rejected','requires_changes') THEN
    NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now();
  ELSIF NEW.status = 'paused' THEN
    NEW.paused_at := now();
  ELSIF NEW.status = 'sold' THEN
    IF NOT EXISTS (SELECT 1 FROM app.sales s WHERE s.listing_id = NEW.id AND s.status = 'reported') THEN
      RAISE EXCEPTION 'VENTA_REQUERIDA: usar register_sale()' USING ERRCODE = 'GR422';
    END IF;
    NEW.sold_at := now();
  ELSIF NEW.status = 'deleted' THEN
    NEW.deleted_at := now();
  END IF;
  IF NEW.status NOT IN ('requires_changes','rejected','paused') AND NOT (is_mod AND NEW.status = 'deleted') THEN
    NEW.status_reason := NULL;
  END IF;
  NEW.status_changed_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER b_listing_state BEFORE UPDATE OF status ON listings FOR EACH ROW EXECUTE FUNCTION tg_listing_state();

CREATE OR REPLACE FUNCTION app.tg_listing_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status <> 'draft' AND NOT app.app_is_worker() THEN
    RAISE EXCEPTION 'LAS_PUBLICACIONES_NACEN_EN_BORRADOR' USING ERRCODE = 'GR422';
  END IF;
  IF NOT app.app_is_worker() AND NOT app.can_manage_listing(NEW.owner_user_id, NEW.agency_id) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM app.vehicles v WHERE v.id = NEW.vehicle_id
                 AND v.owner_user_id = NEW.owner_user_id AND v.agency_id IS NOT DISTINCT FROM NEW.agency_id) THEN
    RAISE EXCEPTION 'VEHICULO_DE_OTRO_DUENO' USING ERRCODE = 'GR403';
  END IF;
  NEW.created_by := coalesce(app.app_current_user_id(), NEW.created_by);
  RETURN NEW;
END $$;
CREATE TRIGGER a_listing_insert BEFORE INSERT ON listings FOR EACH ROW EXECUTE FUNCTION tg_listing_insert();

-- Historial de estados + efectos (fotos al vender, contacto por defecto)
CREATE OR REPLACE FUNCTION app.tg_listing_after() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_media interval;
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO app.listing_status_history (listing_id, from_status, to_status, actor_user_id, actor_type)
    VALUES (NEW.id, NULL, NEW.status, app.app_current_user_id(), CASE WHEN app.app_is_worker() THEN 'system' ELSE 'user' END::actor_type);
    INSERT INTO app.listing_contacts (listing_id, source) VALUES (NEW.id, CASE WHEN NEW.agency_id IS NULL THEN 'user_profile' ELSE 'agency' END::contact_source);
    RETURN NEW;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO app.listing_status_history (listing_id, from_status, to_status, reason, actor_user_id, actor_type)
    VALUES (NEW.id, OLD.status, NEW.status, NEW.status_reason, app.app_current_user_id(),
            CASE WHEN app.app_is_worker() THEN 'system' WHEN app.app_is_staff() THEN 'staff' ELSE 'user' END::actor_type);
    IF NEW.status IN ('sold','deleted') THEN
      SELECT duration INTO v_media FROM app.retention_policies
       WHERE code = CASE WHEN NEW.status = 'sold' THEN 'media_sold' ELSE 'media_deleted' END AND is_active;
      UPDATE app.listing_images SET status = 'purge_scheduled', is_cover = false,
             purge_after = now() + coalesce(v_media, interval '7 days')
       WHERE listing_id = NEW.id AND status = 'active';
    END IF;
  END IF;
  IF NEW.price_amount IS DISTINCT FROM OLD.price_amount OR NEW.currency IS DISTINCT FROM OLD.currency THEN
    IF NEW.price_amount IS NOT NULL THEN
      INSERT INTO app.listing_price_history (listing_id, old_amount, old_currency, new_amount, new_currency, changed_by)
      VALUES (NEW.id, OLD.price_amount, OLD.currency, NEW.price_amount, NEW.currency, app.app_current_user_id());
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER z_listing_after AFTER INSERT OR UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION tg_listing_after();

-- ---------------------------------------------------------------------
-- Fotos: máximo 6 activas; la primera es portada
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_listing_images() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_max int := app.setting_int('listings.max_images', 6); v_count int;
BEGIN
  IF NEW.status = 'active' AND (TG_OP = 'INSERT' OR OLD.status <> 'active') THEN
    PERFORM pg_advisory_xact_lock(hashtext('listing_images:' || NEW.listing_id::text));
    SELECT count(*) INTO v_count FROM app.listing_images WHERE listing_id = NEW.listing_id AND status = 'active' AND id <> NEW.id;
    IF v_count >= v_max THEN
      RAISE EXCEPTION 'MAXIMO_FOTOS' USING ERRCODE = 'GR409', DETAIL = format('max=%s', v_max);
    END IF;
    IF v_count = 0 THEN NEW.is_cover := true; END IF;
  END IF;
  IF NEW.status = 'purged' AND NEW.purged_at IS NULL THEN NEW.purged_at := now(); END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_listing_images BEFORE INSERT OR UPDATE ON listing_images FOR EACH ROW EXECUTE FUNCTION tg_listing_images();

-- ---------------------------------------------------------------------
-- Ventas: register_sale() es la ÚNICA forma de marcar "vendida"
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_sales_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE l app.listings;
BEGIN
  SELECT * INTO l FROM app.listings WHERE id = NEW.listing_id FOR UPDATE;
  IF l.status NOT IN ('published','paused','expired') THEN
    RAISE EXCEPTION 'PUBLICACION_NO_VENDIBLE %', l.status USING ERRCODE = 'GR409';
  END IF;
  IF NOT app.app_is_worker() AND NOT app.can_manage_listing(l.owner_user_id, l.agency_id) THEN
    RAISE EXCEPTION 'NO_AUTORIZADO' USING ERRCODE = 'GR403';
  END IF;
  NEW.vehicle_id := l.vehicle_id;
  NEW.seller_user_id := l.owner_user_id;
  NEW.agency_id := l.agency_id;
  NEW.reported_by := coalesce(app.app_current_user_id(), NEW.reported_by);
  IF NEW.currency = 'USD' AND NEW.fx_rate_to_ars IS NULL THEN
    SELECT rate_to_ars INTO NEW.fx_rate_to_ars FROM app.exchange_rates
     WHERE currency = 'USD' AND valid_on <= NEW.sold_on ORDER BY valid_on DESC LIMIT 1;
    IF NEW.fx_rate_to_ars IS NULL THEN RAISE EXCEPTION 'SIN_COTIZACION_USD' USING ERRCODE = 'GR422'; END IF;
  END IF;
  IF NEW.buyer_conversation_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM app.conversations c WHERE c.id = NEW.buyer_conversation_id AND c.listing_id = NEW.listing_id) THEN
    RAISE EXCEPTION 'CONVERSACION_AJENA' USING ERRCODE = 'GR422';
  END IF;
  IF NEW.sold_on > current_date OR NEW.sold_on < coalesce(l.first_published_at::date, l.created_at::date) THEN
    RAISE EXCEPTION 'FECHA_DE_VENTA_INVALIDA' USING ERRCODE = 'GR422';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_sales_before BEFORE INSERT ON sales FOR EACH ROW EXECUTE FUNCTION tg_sales_before();

CREATE OR REPLACE FUNCTION app.register_sale(
  p_listing uuid, p_sold_on date, p_price numeric, p_currency app.currency_code, p_channel app.sale_channel,
  p_is_financed boolean DEFAULT false, p_financing app.financing_type DEFAULT NULL, p_financed_amount numeric DEFAULT NULL,
  p_installments smallint DEFAULT NULL, p_plate text DEFAULT NULL, p_notes text DEFAULT NULL, p_conversation uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path = app, public AS $$
DECLARE v_sale uuid; v_vehicle uuid; v_plate_ret interval;
BEGIN
  INSERT INTO app.sales (listing_id, vehicle_id, seller_user_id, reported_by, sold_on, final_price, currency, is_financed,
                         financing_type, financed_amount, installments, channel, notes, buyer_conversation_id)
  VALUES (p_listing, NULL, NULL, NULL,  -- los completa tg_sales_before desde la publicación
          p_sold_on, p_price, p_currency, p_is_financed, p_financing, p_financed_amount, p_installments, p_channel, p_notes, p_conversation)
  RETURNING id, vehicle_id INTO v_sale, v_vehicle;
  UPDATE app.listings SET status = 'sold' WHERE id = p_listing;
  SELECT duration INTO v_plate_ret FROM app.retention_policies WHERE code = 'plate_after_sale' AND is_active;
  IF p_plate IS NOT NULL THEN
    UPDATE app.vehicle_identifiers SET is_current = false WHERE vehicle_id = v_vehicle AND type = 'plate' AND is_current;
    INSERT INTO app.vehicle_identifiers (vehicle_id, type, value, declared_by)
    VALUES (v_vehicle, 'plate', app.normalize_plate(p_plate), app.app_current_user_id());
  END IF;
  UPDATE app.vehicle_identifiers SET purge_after = now() + coalesce(v_plate_ret, interval '24 months')
   WHERE vehicle_id = v_vehicle AND type = 'plate' AND is_current;
  RETURN v_sale;
END $$;
COMMENT ON FUNCTION app.register_sale IS 'Vendí este vehículo: crea la venta, pasa la publicación a sold, programa borrado de fotos y de la patente según retención. Todo en una transacción.';

-- ---------------------------------------------------------------------
-- Guardas de columnas privilegiadas (users, agencies)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_users_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- pg_trigger_depth() > 1: la escritura viene de otro trigger nuestro (p.ej. verificación aprobada)
  IF app.app_is_worker() OR pg_trigger_depth() > 1 OR app.app_has_staff_role('admin','support') THEN RETURN NEW; END IF;
  IF NEW.status IS DISTINCT FROM OLD.status OR NEW.status_reason IS DISTINCT FROM OLD.status_reason
     OR NEW.email_verified_at IS DISTINCT FROM OLD.email_verified_at OR NEW.phone_verified_at IS DISTINCT FROM OLD.phone_verified_at
     OR NEW.identity_verified_at IS DISTINCT FROM OLD.identity_verified_at OR NEW.failed_login_count IS DISTINCT FROM OLD.failed_login_count
     OR NEW.locked_until IS DISTINCT FROM OLD.locked_until OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
     OR NEW.email IS DISTINCT FROM OLD.email OR NEW.password_hash IS DISTINCT FROM OLD.password_hash
     OR NEW.mfa_secret_encrypted IS DISTINCT FROM OLD.mfa_secret_encrypted OR NEW.last_login_at IS DISTINCT FROM OLD.last_login_at THEN
    RAISE EXCEPTION 'CAMPO_NO_EDITABLE (usar el flujo del servicio de auth)' USING ERRCODE = 'GR403';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_users_guard BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION tg_users_guard();

CREATE OR REPLACE FUNCTION app.tg_agencies_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF app.app_is_worker() OR pg_trigger_depth() > 1 OR app.app_has_staff_role('moderator','admin') THEN RETURN NEW; END IF;
  IF TG_OP = 'INSERT' THEN
    NEW.status := 'pending'; NEW.verified_at := NULL; NEW.status_reason := NULL; NEW.kind := 'agency';
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
CREATE TRIGGER a_agencies_guard BEFORE INSERT OR UPDATE ON agencies FOR EACH ROW EXECUTE FUNCTION tg_agencies_guard();

-- Quien crea la agencia queda como owner
CREATE OR REPLACE FUNCTION app.tg_agencies_owner() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  INSERT INTO app.agency_members (agency_id, user_id, role, status, joined_at)
  VALUES (NEW.id, NEW.created_by, 'owner', 'active', now());
  RETURN NEW;
END $$;
CREATE TRIGGER z_agencies_owner AFTER INSERT ON agencies FOR EACH ROW EXECUTE FUNCTION tg_agencies_owner();

-- ---------------------------------------------------------------------
-- Verificaciones: nadie aprueba lo propio; efectos en users/agencies
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_verifications_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE is_rev boolean := app.app_has_staff_role('moderator','admin');
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' OR NEW.reviewer_id IS NOT NULL THEN
      RAISE EXCEPTION 'LAS_VERIFICACIONES_NACEN_PENDIENTES' USING ERRCODE = 'GR403';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT is_rev THEN RAISE EXCEPTION 'SOLO_STAFF_DECIDE' USING ERRCODE = 'GR403'; END IF;
    IF NOT ((OLD.status||'>'||NEW.status) = ANY (ARRAY['pending>review','review>approved','review>rejected','approved>revoked','pending>rejected'])) THEN
      RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA' USING ERRCODE = 'GR403';
    END IF;
    NEW.reviewer_id := app.app_current_user_id();
    IF NEW.reviewer_id = OLD.requested_by OR NEW.reviewer_id IS NOT DISTINCT FROM OLD.subject_user_id
       OR (OLD.subject_agency_id IS NOT NULL AND EXISTS (SELECT 1 FROM app.agency_members m WHERE m.agency_id = OLD.subject_agency_id AND m.user_id = NEW.reviewer_id AND m.status = 'active')) THEN
      RAISE EXCEPTION 'CONFLICTO_DE_INTERES' USING ERRCODE = 'GR403';
    END IF;
    IF NEW.status = 'review' THEN NEW.review_started_at := now(); END IF;
    IF NEW.status IN ('approved','rejected') THEN NEW.decided_at := now(); END IF;
    IF NEW.status = 'approved' THEN
      NEW.expires_at := (SELECT CASE WHEN p.validity_days IS NULL THEN NULL ELSE now() + make_interval(days => p.validity_days) END
                           FROM app.verification_products p WHERE p.id = NEW.product_id);
    END IF;
    IF NEW.status = 'revoked' THEN NEW.revoked_at := now(); NEW.decided_at := coalesce(NEW.decided_at, now()); END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_verifications_guard BEFORE INSERT OR UPDATE ON verifications FOR EACH ROW EXECUTE FUNCTION tg_verifications_guard();

CREATE OR REPLACE FUNCTION app.tg_verifications_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE k app.verification_kind;
BEGIN
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
  SELECT kind INTO k FROM app.verification_products WHERE id = NEW.product_id;
  IF k = 'identity' AND NEW.subject_user_id IS NOT NULL THEN
    UPDATE app.users SET identity_verified_at = CASE WHEN NEW.status = 'approved' THEN now() ELSE NULL END
     WHERE id = NEW.subject_user_id AND NEW.status IN ('approved','revoked');
  ELSIF k = 'agency' AND NEW.subject_agency_id IS NOT NULL THEN
    UPDATE app.agencies SET
      status = CASE NEW.status WHEN 'review' THEN 'review' WHEN 'approved' THEN 'verified'
                               WHEN 'rejected' THEN 'rejected' WHEN 'revoked' THEN 'revoked' END::app.agency_status,
      verified_at = CASE WHEN NEW.status = 'approved' THEN now() WHEN NEW.status = 'revoked' THEN NULL ELSE verified_at END,
      status_reason = NEW.decision_reason
     WHERE id = NEW.subject_agency_id AND status NOT IN ('suspended');
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER z_verifications_effects AFTER UPDATE ON verifications FOR EACH ROW EXECUTE FUNCTION tg_verifications_effects();

-- ---------------------------------------------------------------------
-- Suscripciones y pagos: nadie se autoconcede nada
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_subscriptions_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF app.app_is_worker() OR pg_trigger_depth() > 1 OR app.app_has_staff_role('finance') THEN RETURN NEW; END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'pending' OR NEW.started_at IS NOT NULL THEN
      RAISE EXCEPTION 'LAS_SUSCRIPCIONES_NACEN_PENDIENTES' USING ERRCODE = 'GR403';
    END IF;
    SELECT price_amount, currency, billing_period INTO NEW.price_amount, NEW.currency, NEW.billing_period
      FROM app.plans WHERE id = NEW.plan_id AND is_active;
    IF NEW.price_amount IS NULL THEN RAISE EXCEPTION 'PLAN_INACTIVO' USING ERRCODE = 'GR422'; END IF;
    NEW.created_by := app.app_current_user_id();
    RETURN NEW;
  END IF;
  -- El titular solo puede pedir cancelar al fin del período
  IF (NEW.status, NEW.plan_id, NEW.price_amount, NEW.current_period_end, NEW.started_at, NEW.grace_until, NEW.external_subscription_id)
     IS DISTINCT FROM (OLD.status, OLD.plan_id, OLD.price_amount, OLD.current_period_end, OLD.started_at, OLD.grace_until, OLD.external_subscription_id) THEN
    RAISE EXCEPTION 'SUSCRIPCION_SOLO_POR_PROVEEDOR_O_FINANZAS' USING ERRCODE = 'GR403';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_subscriptions_guard BEFORE INSERT OR UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION tg_subscriptions_guard();

CREATE OR REPLACE FUNCTION app.tg_payments_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' AND NEW.provider = 'bank_transfer' AND NEW.transfer_reference IS NULL THEN
    NEW.transfer_reference := 'GIR-' || lpad(nextval('app.transfer_reference_seq')::text, 6, '0');
  END IF;
  IF app.app_is_worker() THEN RETURN NEW; END IF;
  IF TG_OP = 'INSERT' THEN
    IF NOT (NEW.status = 'pending' OR (NEW.provider = 'bank_transfer' AND NEW.status = 'submitted')) OR NEW.paid_at IS NOT NULL THEN
      RAISE EXCEPTION 'PAGO_NO_PUEDE_NACER_APROBADO' USING ERRCODE = 'GR403';
    END IF;
    NEW.payer_user_id := app.app_current_user_id();
    -- El monto lo fija la suscripción/promoción/verificación, nunca el cliente
    IF NEW.subscription_id IS NOT NULL THEN
      SELECT price_amount, currency INTO NEW.amount, NEW.currency FROM app.subscriptions WHERE id = NEW.subscription_id;
    ELSIF NEW.promotion_id IS NOT NULL THEN
      SELECT price_amount, currency INTO NEW.amount, NEW.currency FROM app.promotions WHERE id = NEW.promotion_id;
    ELSIF NEW.verification_id IS NOT NULL THEN
      SELECT p.price_amount, p.currency INTO NEW.amount, NEW.currency
        FROM app.verifications v JOIN app.verification_products p ON p.id = v.product_id WHERE v.id = NEW.verification_id;
    END IF;
    IF NEW.status = 'submitted' THEN NEW.transfer_declared_at := now(); END IF;
    RETURN NEW;
  END IF;
  IF app.app_has_staff_role('finance') THEN
    IF NEW.status IS DISTINCT FROM OLD.status AND NEW.provider <> 'bank_transfer' THEN
      RAISE EXCEPTION 'PAGOS_MP_LOS_ACTUALIZA_EL_WEBHOOK' USING ERRCODE = 'GR403';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
      IF NOT ((OLD.status||'>'||NEW.status) = ANY (ARRAY['submitted>approved','submitted>rejected'])) THEN
        RAISE EXCEPTION 'TRANSICION_NO_PERMITIDA' USING ERRCODE = 'GR403';
      END IF;
      NEW.reviewed_by := app.app_current_user_id(); NEW.reviewed_at := now();
      IF NEW.status = 'approved' THEN NEW.paid_at := now(); END IF;
    END IF;
    RETURN NEW;
  END IF;
  -- Titular: solo pasar su transferencia de pending a submitted (avisar) y adjuntar comprobante
  IF NOT (OLD.provider = 'bank_transfer' AND OLD.status = 'pending' AND NEW.status IN ('pending','submitted')
          AND NEW.amount = OLD.amount AND NEW.paid_at IS NULL AND NEW.reviewed_by IS NULL) THEN
    RAISE EXCEPTION 'CAMPO_NO_EDITABLE' USING ERRCODE = 'GR403';
  END IF;
  IF NEW.status = 'submitted' THEN NEW.transfer_declared_at := now(); END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_payments_guard BEFORE INSERT OR UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION tg_payments_guard();

-- Transferencia aprobada por finanzas → activa la suscripción (en la misma transacción)
CREATE OR REPLACE FUNCTION app.tg_payments_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' AND NEW.subscription_id IS NOT NULL
     AND NEW.provider = 'bank_transfer' THEN
    UPDATE app.subscriptions s SET
      plan_id = coalesce(s.pending_plan_id, s.plan_id), pending_plan_id = NULL,
      status = 'active', started_at = coalesce(s.started_at, now()),
      current_period_start = now(),
      current_period_end = now() + CASE s.billing_period WHEN 'year' THEN interval '1 year' ELSE interval '1 month' END,
      next_renewal_at = NULL  -- transferencias no renuevan solas
     WHERE s.id = NEW.subscription_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER z_payments_effects AFTER UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION tg_payments_effects();

-- Pérdida de plan: pausar las publicaciones más antiguas que excedan el límite (job del worker)
CREATE OR REPLACE FUNCTION app.enforce_plan_limit(p_user uuid, p_agency uuid) RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER SET search_path = app, public AS $$
DECLARE v_plan app.plans := app.effective_plan(p_user, p_agency); v_n int;
BEGIN
  WITH ranked AS (
    SELECT id, row_number() OVER (ORDER BY published_at DESC) AS rn
      FROM app.listings
     WHERE status = 'published'
       AND (CASE WHEN p_agency IS NOT NULL THEN agency_id = p_agency ELSE owner_user_id = p_user AND agency_id IS NULL END))
  UPDATE app.listings l SET status = 'paused', status_reason = 'Límite del plan: la suscripción ya no otorga el plan'
    FROM ranked r WHERE r.id = l.id AND r.rn > v_plan.max_active_listings;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN v_n;
END $$;

-- ---------------------------------------------------------------------
-- Mensajería: bloqueos, anti-spam, participantes
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_conversations_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE l app.listings; v_today int; v_max int := app.setting_int('messaging.max_new_conversations_per_day', 10);
BEGIN
  SELECT * INTO l FROM app.listings WHERE id = NEW.listing_id;
  IF l.status <> 'published' THEN RAISE EXCEPTION 'PUBLICACION_NO_DISPONIBLE' USING ERRCODE = 'GR409'; END IF;
  NEW.buyer_user_id := coalesce(app.app_current_user_id(), NEW.buyer_user_id);
  NEW.seller_user_id := l.owner_user_id;
  NEW.seller_agency_id := l.agency_id;
  IF app.can_manage_listing(l.owner_user_id, l.agency_id) THEN
    RAISE EXCEPTION 'NO_PODES_CONSULTAR_TU_PUBLICACION' USING ERRCODE = 'GR422';
  END IF;
  IF EXISTS (SELECT 1 FROM app.user_blocks b WHERE (b.blocker_user_id = NEW.seller_user_id AND b.blocked_user_id = NEW.buyer_user_id)
                                              OR (b.blocker_user_id = NEW.buyer_user_id AND b.blocked_user_id = NEW.seller_user_id)) THEN
    RAISE EXCEPTION 'USUARIO_BLOQUEADO' USING ERRCODE = 'GR403';
  END IF;
  SELECT count(*) INTO v_today FROM app.conversations WHERE buyer_user_id = NEW.buyer_user_id AND created_at > now() - interval '24 hours';
  IF v_today >= v_max THEN RAISE EXCEPTION 'LIMITE_CONVERSACIONES_DIARIAS' USING ERRCODE = 'GR429'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_conversations_before BEFORE INSERT ON conversations FOR EACH ROW EXECUTE FUNCTION tg_conversations_before();

CREATE OR REPLACE FUNCTION app.tg_messages_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE c app.conversations; v_last bytea; me uuid := app.app_current_user_id();
BEGIN
  SELECT * INTO c FROM app.conversations WHERE id = NEW.conversation_id;
  IF c.status = 'blocked' THEN RAISE EXCEPTION 'CONVERSACION_BLOQUEADA' USING ERRCODE = 'GR403'; END IF;
  NEW.sender_user_id := coalesce(me, NEW.sender_user_id);
  IF NEW.sender_user_id = c.buyer_user_id THEN NEW.sender_side := 'buyer';
  ELSIF NEW.sender_user_id = c.seller_user_id OR (c.seller_agency_id IS NOT NULL AND app.app_is_agency_member(c.seller_agency_id)) THEN NEW.sender_side := 'seller';
  ELSE RAISE EXCEPTION 'NO_PARTICIPANTE' USING ERRCODE = 'GR403';
  END IF;
  SELECT body_hash INTO v_last FROM app.messages WHERE conversation_id = c.id AND sender_user_id = NEW.sender_user_id
   ORDER BY created_at DESC LIMIT 1;
  IF v_last IS NOT NULL AND v_last = digest(lower(btrim(NEW.body)), 'sha256') THEN
    RAISE EXCEPTION 'MENSAJE_REPETIDO' USING ERRCODE = 'GR429';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_messages_before BEFORE INSERT ON messages FOR EACH ROW EXECUTE FUNCTION tg_messages_before();

CREATE OR REPLACE FUNCTION app.tg_messages_after() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  UPDATE app.conversations SET last_message_at = NEW.created_at,
         seller_first_reply_at = CASE WHEN NEW.sender_side = 'seller' THEN coalesce(seller_first_reply_at, NEW.created_at) ELSE seller_first_reply_at END
   WHERE id = NEW.conversation_id;
  RETURN NEW;
END $$;
CREATE TRIGGER z_messages_after AFTER INSERT ON messages FOR EACH ROW EXECUTE FUNCTION tg_messages_after();

-- ---------------------------------------------------------------------
-- Reseñas: interacción válida, una por interacción, sujeto correcto
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_reviews_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE c app.conversations; s app.sales;
BEGIN
  NEW.reviewer_user_id := coalesce(app.app_current_user_id(), NEW.reviewer_user_id);
  IF NEW.conversation_id IS NOT NULL THEN
    SELECT * INTO c FROM app.conversations WHERE id = NEW.conversation_id;
    IF c.seller_first_reply_at IS NULL THEN RAISE EXCEPTION 'CONSULTA_SIN_RESPUESTA' USING ERRCODE = 'GR422'; END IF;
    IF NEW.reviewer_user_id = c.buyer_user_id THEN
      IF c.seller_agency_id IS NOT NULL THEN NEW.reviewed_agency_id := c.seller_agency_id; NEW.reviewed_user_id := NULL;
      ELSE NEW.reviewed_user_id := c.seller_user_id; NEW.reviewed_agency_id := NULL; END IF;
    ELSIF NEW.reviewer_user_id = c.seller_user_id THEN
      NEW.reviewed_user_id := c.buyer_user_id; NEW.reviewed_agency_id := NULL;
    ELSE RAISE EXCEPTION 'NO_PARTICIPANTE' USING ERRCODE = 'GR403';
    END IF;
  ELSE
    SELECT * INTO s FROM app.sales WHERE id = NEW.sale_id AND status = 'reported';
    SELECT * INTO c FROM app.conversations WHERE id = s.buyer_conversation_id;
    IF c.id IS NULL OR c.buyer_user_id <> NEW.reviewer_user_id THEN
      RAISE EXCEPTION 'SOLO_EL_COMPRADOR_VINCULADO_CALIFICA_LA_VENTA' USING ERRCODE = 'GR403';
    END IF;
    IF s.agency_id IS NOT NULL THEN NEW.reviewed_agency_id := s.agency_id; NEW.reviewed_user_id := NULL;
    ELSE NEW.reviewed_user_id := s.seller_user_id; NEW.reviewed_agency_id := NULL; END IF;
  END IF;
  NEW.status := 'published';
  RETURN NEW;
END $$;
CREATE TRIGGER a_reviews_before BEFORE INSERT ON reviews FOR EACH ROW EXECUTE FUNCTION tg_reviews_before();

-- Favoritos solo sobre publicaciones visibles
CREATE OR REPLACE FUNCTION app.tg_favorites_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM app.listings WHERE id = NEW.listing_id AND status = 'published') THEN
    RAISE EXCEPTION 'PUBLICACION_NO_DISPONIBLE' USING ERRCODE = 'GR409';
  END IF;
  NEW.user_id := coalesce(app.app_current_user_id(), NEW.user_id);
  RETURN NEW;
END $$;
CREATE TRIGGER a_favorites_before BEFORE INSERT ON favorites FOR EACH ROW EXECUTE FUNCTION tg_favorites_before();

-- ---------------------------------------------------------------------
-- Auditoría automática de tablas críticas (además de la que escribe el backend)
-- El backend setea en la transacción: app.ip, app.user_agent, app.request_id, app.reason
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_audit_row() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE
  redact text[] := ARRAY['password_hash','mfa_secret_encrypted','dni_encrypted','dni_hash','refresh_token_hash','token_hash','value','storage_key'];
  o jsonb; n jsonb; b jsonb := '{}'; a jsonb := '{}'; k text;
  v_actor uuid := app.app_current_user_id();
  v_role text;
BEGIN
  o := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
  n := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
  FOR k IN SELECT jsonb_object_keys(o || n) LOOP
    CONTINUE WHEN k IN ('updated_at','search_vector');
    IF (o -> k) IS DISTINCT FROM (n -> k) THEN
      b := b || jsonb_build_object(k, CASE WHEN k = ANY (redact) THEN '"[REDACTED]"'::jsonb ELSE o -> k END);
      a := a || jsonb_build_object(k, CASE WHEN k = ANY (redact) THEN '"[REDACTED]"'::jsonb ELSE n -> k END);
    END IF;
  END LOOP;
  IF b = '{}'::jsonb AND a = '{}'::jsonb THEN RETURN NULL; END IF;
  SELECT string_agg(role::text, ',') INTO v_role FROM app.staff_roles WHERE user_id = v_actor AND revoked_at IS NULL;
  INSERT INTO app.audit_logs (actor_type, actor_user_id, actor_role, action, entity_type, entity_id, before_data, after_data, reason, ip, user_agent, request_id)
  VALUES (CASE WHEN app.app_is_worker() THEN 'system' WHEN v_role IS NOT NULL THEN 'staff' ELSE 'user' END::app.actor_type,
          v_actor, v_role, TG_TABLE_NAME || '.' || lower(TG_OP), TG_TABLE_NAME,
          CASE WHEN TG_OP = 'DELETE' THEN (o ->> 'id')::uuid ELSE (n ->> 'id')::uuid END,
          NULLIF(b, '{}'::jsonb), NULLIF(a, '{}'::jsonb),
          NULLIF(current_setting('app.reason', true), ''),
          NULLIF(current_setting('app.ip', true), '')::inet,
          NULLIF(current_setting('app.user_agent', true), ''),
          NULLIF(current_setting('app.request_id', true), ''));
  RETURN NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['users','agencies','agency_members','staff_roles','listings','vehicle_identifiers','documents',
                           'verifications','verification_products','plans','subscriptions','payments','promotions','promotion_products',
                           'sales','reviews','reports','app_settings','retention_policies','report_reasons','email_templates','notification_types',
                           'vehicle_brands','vehicle_models','vehicle_generations','vehicle_versions','vehicle_engines']
  LOOP
    EXECUTE format('CREATE TRIGGER zz_audit AFTER INSERT OR UPDATE OR DELETE ON app.%I FOR EACH ROW EXECUTE FUNCTION app.tg_audit_row()', t);
  END LOOP;
END $$;
