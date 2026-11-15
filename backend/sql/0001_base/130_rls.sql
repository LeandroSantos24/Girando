-- =====================================================================
-- 130 · Row Level Security + grants
-- Principios:
--  * Las tablas de app.* NUNCA se exponen a visitantes: girando_anon solo
--    tiene SELECT sobre vistas api_public.* (datos públicos filtrados).
--  * girando_app (usuario autenticado o staff) ve/escribe solo lo suyo;
--    el staff se reconoce por staff_roles (no por el JWT).
--  * girando_worker (webhooks y jobs) tiene acceso de sistema.
--  * El dueño de las tablas (rol de migraciones) no se usa en runtime.
-- Variante Supabase: reemplazar app.app_current_user_id() por auth.uid()
-- y mapear girando_app → authenticated, girando_anon → anon,
-- girando_worker → service_role (que ya ignora RLS).
-- =====================================================================
SET search_path = app, public;

-- Grants base (RLS decide filas; los grants deciden operaciones)
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA app TO girando_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO girando_worker;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA app TO girando_app, girando_worker;
GRANT DELETE ON favorites, saved_searches, user_blocks, notification_preferences TO girando_app;
REVOKE UPDATE ON audit_logs, listing_status_history, listing_price_history, payment_events, promotion_events,
                 moderation_actions, login_attempts, auth_tokens, analytics_events FROM girando_app;
REVOKE INSERT ON auth_tokens, login_attempts, payment_events, listing_status_history, listing_price_history,
                 listing_stats_daily, exchange_rates, email_events, notifications FROM girando_app;
REVOKE UPDATE ON messages FROM girando_app;
GRANT UPDATE (read_at, deleted_at, visibility) ON messages TO girando_app;
REVOKE ALL ON analytics_events_2026_10, analytics_events_default FROM girando_app, girando_worker;
GRANT INSERT ON analytics_events_2026_10, analytics_events_default TO girando_app, girando_worker;

-- Funciones SECURITY DEFINER: no ejecutables por PUBLIC salvo las necesarias
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO girando_app, girando_worker;

-- Activar RLS en todas las tablas de app
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'app' AND c.relkind IN ('r','p') LOOP
    EXECUTE format('ALTER TABLE app.%I ENABLE ROW LEVEL SECURITY', t.relname);
    EXECUTE format('CREATE POLICY worker_all ON app.%I TO girando_worker USING (true) WITH CHECK (true)', t.relname);
  END LOOP;
END $$;

-- Atajos
CREATE OR REPLACE FUNCTION app.me() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT app.app_current_user_id() $$;
CREATE OR REPLACE FUNCTION app.is_mod() RETURNS boolean LANGUAGE sql STABLE AS $$ SELECT app.app_has_staff_role('moderator','admin') $$;
CREATE OR REPLACE FUNCTION app.can_manage_vehicle(p_vehicle uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.vehicles v WHERE v.id = p_vehicle AND app.can_manage_listing(v.owner_user_id, v.agency_id))
$$;
CREATE OR REPLACE FUNCTION app.can_manage_listing_id(p_listing uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.listings l WHERE l.id = p_listing AND app.can_manage_listing(l.owner_user_id, l.agency_id))
$$;
CREATE OR REPLACE FUNCTION app.is_conversation_participant(p_conv uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.conversations c WHERE c.id = p_conv AND
    (c.buyer_user_id = app.me() OR c.seller_user_id = app.me() OR (c.seller_agency_id IS NOT NULL AND app.app_is_agency_member(c.seller_agency_id))))
$$;
GRANT EXECUTE ON FUNCTION app.me(), app.is_mod(), app.can_manage_vehicle(uuid), app.can_manage_listing_id(uuid), app.is_conversation_participant(uuid) TO girando_app, girando_worker;

-- ---------------------------------------------------------------- identidad
CREATE POLICY users_self_or_staff ON users FOR SELECT TO girando_app USING (id = me() OR app_has_staff_role('admin','support','moderator'));
CREATE POLICY users_update ON users FOR UPDATE TO girando_app USING (id = me() OR app_has_staff_role('admin','support')) WITH CHECK (true);

CREATE POLICY upd_self ON user_personal_data FOR ALL TO girando_app
  USING (user_id = me() OR app_has_staff_role('admin','support')) WITH CHECK (user_id = me());

CREATE POLICY up_select ON user_profiles FOR SELECT TO girando_app USING (user_id = me() OR app_is_staff());
CREATE POLICY up_insert ON user_profiles FOR INSERT TO girando_app WITH CHECK (user_id = me());
CREATE POLICY up_update ON user_profiles FOR UPDATE TO girando_app USING (user_id = me() OR app_has_staff_role('admin','support','moderator')) WITH CHECK (true);

CREATE POLICY sr_select ON staff_roles FOR SELECT TO girando_app USING (user_id = me() OR app_has_staff_role('admin'));
CREATE POLICY sr_manage ON staff_roles FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('superadmin') AND granted_by = me());
CREATE POLICY sr_revoke ON staff_roles FOR UPDATE TO girando_app USING (app_has_staff_role('superadmin')) WITH CHECK (revoked_by = me());

CREATE POLICY sessions_own ON sessions FOR SELECT TO girando_app USING (user_id = me() OR app_has_staff_role('admin','support'));
CREATE POLICY sessions_revoke ON sessions FOR UPDATE TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());

CREATE POLICY la_staff ON login_attempts FOR SELECT TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY ub_own ON user_blocks FOR ALL TO girando_app USING (blocker_user_id = me()) WITH CHECK (blocker_user_id = me());

CREATE POLICY pv_read ON policy_versions FOR SELECT TO girando_app USING (true);
CREATE POLICY pv_admin ON policy_versions FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY cs_own ON consents FOR SELECT TO girando_app USING (user_id = me() OR app_has_staff_role('admin','support'));
CREATE POLICY cs_insert ON consents FOR INSERT TO girando_app WITH CHECK (user_id = me());

-- ---------------------------------------------------------------- ubicaciones
CREATE POLICY geo_read ON geo_areas FOR SELECT TO girando_app USING (true);
CREATE POLICY geo_admin_i ON geo_areas FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin','catalog_editor'));
CREATE POLICY geo_admin_u ON geo_areas FOR UPDATE TO girando_app USING (app_has_staff_role('admin','catalog_editor'));
CREATE POLICY loc_select ON locations FOR SELECT TO girando_app USING (created_by = me() OR is_mod()
  OR EXISTS (SELECT 1 FROM agencies a WHERE a.location_id = locations.id AND app_is_agency_member(a.id)));
CREATE POLICY loc_insert ON locations FOR INSERT TO girando_app WITH CHECK (created_by = me());
CREATE POLICY loc_update ON locations FOR UPDATE TO girando_app USING (created_by = me()
  OR EXISTS (SELECT 1 FROM agencies a WHERE a.location_id = locations.id AND app_is_agency_member(a.id, 'owner','admin')));

-- ---------------------------------------------------------------- agencias
CREATE POLICY ag_select ON agencies FOR SELECT TO girando_app USING (created_by = me() OR app_is_agency_member(id) OR app_is_staff());
CREATE POLICY ag_insert ON agencies FOR INSERT TO girando_app WITH CHECK (me() IS NOT NULL);
CREATE POLICY ag_update ON agencies FOR UPDATE TO girando_app USING (app_is_agency_member(id, 'owner','admin') OR is_mod()) WITH CHECK (true);
CREATE POLICY am_select ON agency_members FOR SELECT TO girando_app USING (user_id = me() OR app_is_agency_member(agency_id) OR app_is_staff());
CREATE POLICY am_insert ON agency_members FOR INSERT TO girando_app
  WITH CHECK ((app_is_agency_member(agency_id, 'owner','admin') AND role <> 'owner') OR app_has_staff_role('admin'));
CREATE POLICY am_update ON agency_members FOR UPDATE TO girando_app
  USING (app_is_agency_member(agency_id, 'owner','admin') OR (user_id = me() AND status = 'invited') OR app_has_staff_role('admin'))
  WITH CHECK (role <> 'owner' OR app_is_agency_member(agency_id, 'owner') OR app_has_staff_role('admin'));
CREATE POLICY er_read ON external_ratings FOR SELECT TO girando_app USING (true);

-- ---------------------------------------------------------------- catálogo
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['vehicle_brands','vehicle_models','vehicle_generations','vehicle_versions','vehicle_engines','vehicle_version_engines'] LOOP
    EXECUTE format('CREATE POLICY cat_read ON app.%I FOR SELECT TO girando_app USING (true)', t);
    EXECUTE format('CREATE POLICY cat_ins ON app.%I FOR INSERT TO girando_app WITH CHECK (app.app_has_staff_role(''catalog_editor'',''admin''))', t);
    EXECUTE format('CREATE POLICY cat_upd ON app.%I FOR UPDATE TO girando_app USING (app.app_has_staff_role(''catalog_editor'',''admin''))', t);
  END LOOP;
END $$;
CREATE POLICY cr_select ON catalog_requests FOR SELECT TO girando_app USING (requested_by = me() OR app_has_staff_role('catalog_editor','admin'));
CREATE POLICY cr_insert ON catalog_requests FOR INSERT TO girando_app WITH CHECK (requested_by = me() AND status = 'pending');
CREATE POLICY cr_update ON catalog_requests FOR UPDATE TO girando_app USING (app_has_staff_role('catalog_editor','admin'));

-- ---------------------------------------------------------------- vehículos y publicaciones
CREATE POLICY veh_select ON vehicles FOR SELECT TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR is_mod());
CREATE POLICY veh_insert ON vehicles FOR INSERT TO girando_app WITH CHECK (can_manage_listing(owner_user_id, agency_id));
CREATE POLICY veh_update ON vehicles FOR UPDATE TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR is_mod())
  WITH CHECK (can_manage_listing(owner_user_id, agency_id) OR is_mod());

CREATE POLICY vi_select ON vehicle_identifiers FOR SELECT TO girando_app USING (can_manage_vehicle(vehicle_id) OR is_mod());
CREATE POLICY vi_insert ON vehicle_identifiers FOR INSERT TO girando_app
  WITH CHECK (can_manage_vehicle(vehicle_id) AND declared_by = me() AND status IN ('declared','pending') AND verified_by IS NULL);
CREATE POLICY vi_update ON vehicle_identifiers FOR UPDATE TO girando_app
  USING (can_manage_vehicle(vehicle_id) OR is_mod())
  WITH CHECK (is_mod() OR (status IN ('declared','pending') AND verified_by IS NULL));

CREATE POLICY li_select ON listings FOR SELECT TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR app_is_staff());
CREATE POLICY li_insert ON listings FOR INSERT TO girando_app WITH CHECK (can_manage_listing(owner_user_id, agency_id));
CREATE POLICY li_update ON listings FOR UPDATE TO girando_app USING (can_manage_listing(owner_user_id, agency_id) OR is_mod()) WITH CHECK (true);

CREATE POLICY lim_select ON listing_images FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());
CREATE POLICY lim_insert ON listing_images FOR INSERT TO girando_app WITH CHECK (can_manage_listing_id(listing_id) AND uploaded_by = me() AND status IN ('uploading','active'));
CREATE POLICY lim_update ON listing_images FOR UPDATE TO girando_app USING (can_manage_listing_id(listing_id) OR is_mod())
  WITH CHECK (status IN ('uploading','active','replaced','deleted'));

CREATE POLICY lc_select ON listing_contacts FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());
CREATE POLICY lc_update ON listing_contacts FOR UPDATE TO girando_app USING (can_manage_listing_id(listing_id));
CREATE POLICY lsh_select ON listing_status_history FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());
CREATE POLICY lph_select ON listing_price_history FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());
CREATE POLICY lsd_select ON listing_stats_daily FOR SELECT TO girando_app USING (can_manage_listing_id(listing_id) OR app_is_staff());

-- ---------------------------------------------------------------- confianza
CREATE POLICY vp_read ON verification_products FOR SELECT TO girando_app USING (status = 'active' OR app_is_staff());
CREATE POLICY vp_admin_i ON verification_products FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY vp_admin_u ON verification_products FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));

CREATE POLICY ver_select ON verifications FOR SELECT TO girando_app USING (
  requested_by = me() OR subject_user_id = me()
  OR (subject_agency_id IS NOT NULL AND app_is_agency_member(subject_agency_id, 'owner','admin'))
  OR (subject_vehicle_id IS NOT NULL AND can_manage_vehicle(subject_vehicle_id))
  OR (subject_listing_id IS NOT NULL AND can_manage_listing_id(subject_listing_id))
  OR is_mod());
CREATE POLICY ver_insert ON verifications FOR INSERT TO girando_app WITH CHECK (
  requested_by = me() AND (
       subject_user_id = me()
    OR (subject_agency_id IS NOT NULL AND app_is_agency_member(subject_agency_id, 'owner','admin'))
    OR (subject_vehicle_id IS NOT NULL AND can_manage_vehicle(subject_vehicle_id))
    OR (subject_listing_id IS NOT NULL AND can_manage_listing_id(subject_listing_id))));
CREATE POLICY ver_update ON verifications FOR UPDATE TO girando_app USING (is_mod()) WITH CHECK (is_mod());

CREATE POLICY doc_select ON documents FOR SELECT TO girando_app USING (
  uploaded_by = me() OR owner_user_id = me()
  OR (owner_agency_id IS NOT NULL AND app_is_agency_member(owner_agency_id, 'owner','admin'))
  OR (owner_vehicle_id IS NOT NULL AND can_manage_vehicle(owner_vehicle_id))
  OR app_has_staff_role('moderator','admin','finance'));
CREATE POLICY doc_insert ON documents FOR INSERT TO girando_app WITH CHECK (
  uploaded_by = me() AND status = 'uploaded' AND reviewed_by IS NULL AND (
       owner_user_id = me()
    OR (owner_agency_id IS NOT NULL AND app_is_agency_member(owner_agency_id, 'owner','admin'))
    OR (owner_vehicle_id IS NOT NULL AND can_manage_vehicle(owner_vehicle_id))));
CREATE POLICY doc_update ON documents FOR UPDATE TO girando_app
  USING (uploaded_by = me() OR app_has_staff_role('moderator','admin','finance'))
  WITH CHECK (app_has_staff_role('moderator','admin','finance') OR (status IN ('uploaded','deleted') AND reviewed_by IS NULL));

CREATE POLICY rv_select ON reviews FOR SELECT TO girando_app USING (reviewer_user_id = me() OR reviewed_user_id = me()
  OR (reviewed_agency_id IS NOT NULL AND app_is_agency_member(reviewed_agency_id)) OR is_mod());
CREATE POLICY rv_insert ON reviews FOR INSERT TO girando_app WITH CHECK (reviewer_user_id = me());
CREATE POLICY rv_update ON reviews FOR UPDATE TO girando_app USING (is_mod());

CREATE POLICY rr_read ON report_reasons FOR SELECT TO girando_app USING (is_active OR app_is_staff());
CREATE POLICY rr_admin_i ON report_reasons FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY rr_admin_u ON report_reasons FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY rp_select ON reports FOR SELECT TO girando_app USING (reporter_user_id = me() OR is_mod());
CREATE POLICY rp_insert ON reports FOR INSERT TO girando_app WITH CHECK (reporter_user_id = me() AND status = 'pending' AND assigned_to IS NULL);
CREATE POLICY rp_update ON reports FOR UPDATE TO girando_app USING (is_mod());
CREATE POLICY ma_select ON moderation_actions FOR SELECT TO girando_app USING (app_is_staff());
CREATE POLICY ma_insert ON moderation_actions FOR INSERT TO girando_app WITH CHECK (is_mod() AND actor_user_id = me());

-- ---------------------------------------------------------------- interacción
CREATE POLICY fav_own ON favorites FOR ALL TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());
CREATE POLICY ss_own ON saved_searches FOR ALL TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());
CREATE POLICY cv_select ON conversations FOR SELECT TO girando_app USING (buyer_user_id = me() OR seller_user_id = me()
  OR (seller_agency_id IS NOT NULL AND app_is_agency_member(seller_agency_id)) OR is_mod());
CREATE POLICY cv_insert ON conversations FOR INSERT TO girando_app WITH CHECK (buyer_user_id = me() AND status = 'open');
CREATE POLICY cv_update ON conversations FOR UPDATE TO girando_app USING (buyer_user_id = me() OR seller_user_id = me()
  OR (seller_agency_id IS NOT NULL AND app_is_agency_member(seller_agency_id)))
  WITH CHECK (status <> 'blocked' OR blocked_by_user_id = me());
-- Mensajes: el staff SOLO ve mensajes de conversaciones con un reporte (acceso auditado por el backend)
-- La comprobación "hay un mensaje reportado" va en una función SECURITY DEFINER: si la política consultara
-- app.messages directamente, se reevaluaría a sí misma (infinite recursion detected in policy for relation "messages").
CREATE OR REPLACE FUNCTION app.conversation_has_message_report(p_conv uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.reports r JOIN app.messages m ON m.id = r.message_id WHERE m.conversation_id = p_conv)
$$;
COMMENT ON FUNCTION app.conversation_has_message_report(uuid) IS
  'RLS: true si la conversación tiene al menos un mensaje reportado. SECURITY DEFINER para no reevaluar la política de messages (evita recursión). Solo devuelve un booleano.';
REVOKE ALL ON FUNCTION app.conversation_has_message_report(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.conversation_has_message_report(uuid) TO girando_app, girando_worker;
CREATE POLICY msg_select ON messages FOR SELECT TO girando_app USING (
  is_conversation_participant(conversation_id)
  OR (is_mod() AND conversation_has_message_report(conversation_id)));
CREATE POLICY msg_insert ON messages FOR INSERT TO girando_app WITH CHECK (sender_user_id = me() AND visibility = 'visible' AND read_at IS NULL);
CREATE POLICY msg_update ON messages FOR UPDATE TO girando_app USING (is_conversation_participant(conversation_id) OR is_mod());

CREATE OR REPLACE FUNCTION app.tg_messages_update_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF app.app_is_worker() OR app.is_mod() THEN RETURN NEW; END IF;
  IF NEW.visibility IS DISTINCT FROM OLD.visibility THEN RAISE EXCEPTION 'SOLO_MODERACION' USING ERRCODE = 'GR403'; END IF;
  IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at AND OLD.sender_user_id <> app.me() THEN RAISE EXCEPTION 'SOLO_EL_AUTOR_BORRA' USING ERRCODE = 'GR403'; END IF;
  IF NEW.read_at IS DISTINCT FROM OLD.read_at AND OLD.sender_user_id = app.me() THEN RAISE EXCEPTION 'SOLO_EL_DESTINATARIO_MARCA_LEIDO' USING ERRCODE = 'GR403'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER a_messages_update_guard BEFORE UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION tg_messages_update_guard();

-- ---------------------------------------------------------------- comercial
CREATE POLICY pl_read ON plans FOR SELECT TO girando_app USING ((is_active AND is_public) OR app_is_staff());
CREATE POLICY pl_admin_i ON plans FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin','finance'));
CREATE POLICY pl_admin_u ON plans FOR UPDATE TO girando_app USING (app_has_staff_role('admin','finance'));

CREATE POLICY sub_select ON subscriptions FOR SELECT TO girando_app USING (user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR app_has_staff_role('finance','admin','support'));
CREATE POLICY sub_insert ON subscriptions FOR INSERT TO girando_app WITH CHECK (user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')));
CREATE POLICY sub_update ON subscriptions FOR UPDATE TO girando_app USING (user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR app_has_staff_role('finance')) WITH CHECK (true);

CREATE POLICY pay_select ON payments FOR SELECT TO girando_app USING (payer_user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id, 'owner','admin')) OR app_has_staff_role('finance','admin'));
CREATE POLICY pay_insert ON payments FOR INSERT TO girando_app WITH CHECK (payer_user_id = me() AND (
     (subscription_id IS NOT NULL AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.id = subscription_id
          AND (s.user_id = me() OR (s.agency_id IS NOT NULL AND app_is_agency_member(s.agency_id, 'owner','admin')))))
  OR (promotion_id IS NOT NULL AND EXISTS (SELECT 1 FROM promotions p WHERE p.id = promotion_id AND p.purchased_by = me()))
  OR (verification_id IS NOT NULL AND EXISTS (SELECT 1 FROM verifications v WHERE v.id = verification_id AND v.requested_by = me()))));
CREATE POLICY pay_update ON payments FOR UPDATE TO girando_app USING (payer_user_id = me() OR app_has_staff_role('finance')) WITH CHECK (true);
CREATE POLICY pe_select ON payment_events FOR SELECT TO girando_app USING (app_has_staff_role('finance','admin'));
CREATE POLICY fx_read ON exchange_rates FOR SELECT TO girando_app USING (true);

CREATE POLICY pp_read ON promotion_products FOR SELECT TO girando_app USING (is_active OR app_is_staff());
CREATE POLICY pp_admin_i ON promotion_products FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY pp_admin_u ON promotion_products FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY pr_select ON promotions FOR SELECT TO girando_app USING (purchased_by = me()
  OR (paying_agency_id IS NOT NULL AND app_is_agency_member(paying_agency_id, 'owner','admin')) OR app_is_staff());
CREATE POLICY pr_insert ON promotions FOR INSERT TO girando_app WITH CHECK (
  (purchased_by = me() AND status = 'pending' AND approved_at IS NULL AND type <> 'banner_campaign'
   AND (listing_id IS NULL OR can_manage_listing_id(listing_id))
   AND (target_agency_id IS NULL OR app_is_agency_member(target_agency_id, 'owner','admin')))
  OR app_has_staff_role('admin'));
CREATE POLICY pr_update ON promotions FOR UPDATE TO girando_app USING (is_mod()) WITH CHECK (is_mod());
CREATE POLICY pev_select ON promotion_events FOR SELECT TO girando_app USING (app_is_staff()
  OR EXISTS (SELECT 1 FROM promotions p WHERE p.id = promotion_id AND p.purchased_by = me()));
CREATE POLICY pev_insert ON promotion_events FOR INSERT TO girando_app WITH CHECK (is_mod() AND actor_user_id = me());

CREATE POLICY sa_select ON sales FOR SELECT TO girando_app USING (seller_user_id = me()
  OR (agency_id IS NOT NULL AND app_is_agency_member(agency_id)) OR app_has_staff_role('admin','finance'));
CREATE POLICY sa_insert ON sales FOR INSERT TO girando_app WITH CHECK (reported_by = me());
CREATE POLICY sa_update ON sales FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));

-- ---------------------------------------------------------------- comunicación
CREATE POLICY nt_read ON notification_types FOR SELECT TO girando_app USING (true);
CREATE POLICY nt_admin ON notification_types FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY np_own ON notification_preferences FOR ALL TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());
CREATE POLICY nf_own ON notifications FOR SELECT TO girando_app USING (user_id = me());
CREATE POLICY nf_read ON notifications FOR UPDATE TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());
CREATE POLICY et_staff ON email_templates FOR SELECT TO girando_app USING (app_is_staff());
CREATE POLICY et_admin_i ON email_templates FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY et_admin_u ON email_templates FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY ee_staff ON email_events FOR SELECT TO girando_app USING (app_has_staff_role('admin','support'));

-- ---------------------------------------------------------------- plataforma
CREATE POLICY al_staff ON audit_logs FOR SELECT TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY al_insert ON audit_logs FOR INSERT TO girando_app WITH CHECK (actor_user_id = me());
CREATE POLICY ae_insert ON analytics_events FOR INSERT TO girando_app WITH CHECK (user_id IS NULL OR user_id = me());
CREATE POLICY ae_staff ON analytics_events FOR SELECT TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY as_read ON app_settings FOR SELECT TO girando_app USING (is_public OR app_is_staff());
CREATE POLICY as_admin_i ON app_settings FOR INSERT TO girando_app WITH CHECK (app_has_staff_role('admin'));
CREATE POLICY as_admin_u ON app_settings FOR UPDATE TO girando_app USING (app_has_staff_role('admin'));
CREATE POLICY rpol_read ON retention_policies FOR SELECT TO girando_app USING (app_is_staff());
CREATE POLICY rpol_admin ON retention_policies FOR UPDATE TO girando_app
  USING (app_has_staff_role('admin')) WITH CHECK (category <> 'audit' OR app_has_staff_role('superadmin'));

-- ---------------------------------------------------------------- notificaciones encoladas por el backend
-- Las notificaciones para OTRO usuario (p.ej. "nuevo mensaje") no se insertan
-- con RLS del emisor: se encolan con esta función controlada.
CREATE OR REPLACE FUNCTION app.enqueue_notification(p_user uuid, p_type text, p_title text, p_body text,
                                                    p_entity_type text DEFAULT NULL, p_entity_id uuid DEFAULT NULL, p_path text DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE t app.notification_types; v_id uuid; v_pref boolean;
BEGIN
  SELECT * INTO t FROM app.notification_types WHERE code = p_type AND is_active;
  IF NOT FOUND THEN RETURN NULL; END IF;
  SELECT enabled INTO v_pref FROM app.notification_preferences WHERE user_id = p_user AND category = t.category AND channel = 'in_app';
  IF t.in_app_enabled AND (t.is_mandatory OR coalesce(v_pref, true)) THEN
    INSERT INTO app.notifications (user_id, type_code, category, title, body, entity_type, entity_id, action_path)
    VALUES (p_user, p_type, t.category, p_title, p_body, p_entity_type, p_entity_id, p_path) RETURNING id INTO v_id;
  END IF;
  -- el email lo encola el worker leyendo notification_types.email_enabled + preferencias + consentimiento
  RETURN v_id;
END $$;
REVOKE EXECUTE ON FUNCTION app.enqueue_notification FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.enqueue_notification TO girando_app, girando_worker;

-- Consentimientos: la fila nueva reemplaza a la vigente
CREATE OR REPLACE FUNCTION app.tg_consents_supersede() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  UPDATE app.consents SET superseded_at = now()
   WHERE consent_type = NEW.consent_type AND superseded_at IS NULL
     AND ((NEW.user_id IS NOT NULL AND user_id = NEW.user_id) OR (NEW.user_id IS NULL AND anonymous_id = NEW.anonymous_id AND user_id IS NULL));
  RETURN NEW;
END $$;
CREATE TRIGGER a_consents_supersede BEFORE INSERT ON consents FOR EACH ROW EXECUTE FUNCTION tg_consents_supersede();
