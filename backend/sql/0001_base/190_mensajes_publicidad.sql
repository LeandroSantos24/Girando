-- =====================================================================
-- 190 · Mensajería y publicidad (ex 0007, fase 4): mensajería para todas las verticales, reportes de posts,
--        historial del usuario, búsquedas guardadas y medición de publicidad.
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- 1. Conversaciones: sobre un vehículo (listing) O sobre una publicación de vertical (post)
-- ---------------------------------------------------------------------
ALTER TABLE conversations ALTER COLUMN listing_id DROP NOT NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS post_id uuid REFERENCES posts(id);
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS cv_one_subject;
ALTER TABLE conversations ADD CONSTRAINT cv_one_subject CHECK (num_nonnulls(listing_id, post_id) = 1);
CREATE UNIQUE INDEX IF NOT EXISTS cv_one_per_buyer_post_uq ON conversations (post_id, buyer_user_id) WHERE post_id IS NOT NULL;
COMMENT ON COLUMN conversations.post_id IS '[PARTICIPANTES] Publicación de vertical (empleo, taxi, servicio, repuesto). En empleos el "buyer" es el candidato.';

CREATE OR REPLACE FUNCTION app.tg_conversations_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE v_owner uuid; v_agency uuid; v_status app.listing_status; v_today int;
        v_max int := app.setting_int('messaging.max_new_conversations_per_day', 10);
BEGIN
  IF NEW.listing_id IS NOT NULL THEN
    SELECT owner_user_id, agency_id, status INTO v_owner, v_agency, v_status FROM app.listings WHERE id = NEW.listing_id;
  ELSE
    SELECT owner_user_id, agency_id, status INTO v_owner, v_agency, v_status FROM app.posts WHERE id = NEW.post_id;
  END IF;
  IF v_status IS DISTINCT FROM 'published' THEN RAISE EXCEPTION 'PUBLICACION_NO_DISPONIBLE' USING ERRCODE = 'GR409'; END IF;
  NEW.buyer_user_id := coalesce(app.app_current_user_id(), NEW.buyer_user_id);
  NEW.seller_user_id := v_owner;
  NEW.seller_agency_id := v_agency;
  IF app.can_manage_listing(v_owner, v_agency) THEN
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

-- Anti-spam por mensaje: bloqueo, repetidos y tope por hora
CREATE OR REPLACE FUNCTION app.tg_messages_before() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE c app.conversations; v_last bytea; me uuid := app.app_current_user_id(); v_hour int;
        v_max int := app.setting_int('messaging.max_messages_per_hour', 60);
BEGIN
  SELECT * INTO c FROM app.conversations WHERE id = NEW.conversation_id;
  IF c.status = 'blocked' THEN RAISE EXCEPTION 'CONVERSACION_BLOQUEADA' USING ERRCODE = 'GR403'; END IF;
  NEW.sender_user_id := coalesce(me, NEW.sender_user_id);
  IF NEW.sender_user_id = c.buyer_user_id THEN NEW.sender_side := 'buyer';
  ELSIF NEW.sender_user_id = c.seller_user_id OR (c.seller_agency_id IS NOT NULL AND app.app_is_agency_member(c.seller_agency_id)) THEN NEW.sender_side := 'seller';
  ELSE RAISE EXCEPTION 'NO_PARTICIPANTE' USING ERRCODE = 'GR403';
  END IF;
  IF EXISTS (SELECT 1 FROM app.user_blocks b WHERE (b.blocker_user_id = c.seller_user_id AND b.blocked_user_id = c.buyer_user_id)
                                              OR (b.blocker_user_id = c.buyer_user_id AND b.blocked_user_id = c.seller_user_id)) THEN
    RAISE EXCEPTION 'USUARIO_BLOQUEADO' USING ERRCODE = 'GR403';
  END IF;
  SELECT body_hash INTO v_last FROM app.messages WHERE conversation_id = c.id AND sender_user_id = NEW.sender_user_id
   ORDER BY created_at DESC LIMIT 1;
  IF v_last IS NOT NULL AND v_last = digest(lower(btrim(NEW.body)), 'sha256') THEN
    RAISE EXCEPTION 'MENSAJE_REPETIDO' USING ERRCODE = 'GR429';
  END IF;
  SELECT count(*) INTO v_hour FROM app.messages WHERE sender_user_id = NEW.sender_user_id AND created_at > now() - interval '1 hour';
  IF v_hour >= v_max THEN RAISE EXCEPTION 'LIMITE_MENSAJES_POR_HORA' USING ERRCODE = 'GR429'; END IF;
  RETURN NEW;
END $$;

-- Aviso al destinatario (sin copiar el texto del mensaje a la notificación)
CREATE OR REPLACE FUNCTION app.tg_messages_after() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE c app.conversations;
BEGIN
  UPDATE app.conversations SET last_message_at = NEW.created_at,
         buyer_archived_at = NULL, seller_archived_at = NULL,
         seller_first_reply_at = CASE WHEN NEW.sender_side = 'seller' THEN coalesce(seller_first_reply_at, NEW.created_at) ELSE seller_first_reply_at END
   WHERE id = NEW.conversation_id RETURNING * INTO c;
  PERFORM app.enqueue_notification(CASE WHEN NEW.sender_side = 'buyer' THEN c.seller_user_id ELSE c.buyer_user_id END,
          'message.new', 'Tenés un mensaje nuevo', 'Abrí tus mensajes para responder.', 'conversation', c.id, '/mensajes/' || c.id::text);
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
-- 2. Reportes sobre publicaciones de verticales
-- ---------------------------------------------------------------------
ALTER TABLE reports ADD COLUMN IF NOT EXISTS post_id uuid REFERENCES posts(id);
ALTER TABLE reports DROP CONSTRAINT IF EXISTS rp_one_target;
ALTER TABLE reports ADD CONSTRAINT rp_one_target CHECK (num_nonnulls(listing_id, reported_user_id, agency_id, message_id, review_id, post_id) = 1);
ALTER TABLE reports DROP CONSTRAINT IF EXISTS rp_target_match;
ALTER TABLE reports ADD CONSTRAINT rp_target_match CHECK (
     (target = 'listing' AND listing_id IS NOT NULL) OR (target = 'user' AND reported_user_id IS NOT NULL)
  OR (target = 'agency' AND agency_id IS NOT NULL)  OR (target = 'message' AND message_id IS NOT NULL)
  OR (target = 'review' AND review_id IS NOT NULL)  OR (target = 'post' AND post_id IS NOT NULL));
CREATE INDEX IF NOT EXISTS reports_post_idx ON reports (post_id) WHERE post_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- 3. Historial del usuario: vistos recientemente (dato funcional de la cuenta, no analítica)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recently_viewed (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id  uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  viewed_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, listing_id)
);
COMMENT ON TABLE recently_viewed IS '[PROPIETARIO] Últimos vehículos que vio un usuario con sesión. Máximo 50 por usuario; el usuario puede borrarlo. Nadie más lo ve.';
CREATE INDEX IF NOT EXISTS rv_user_idx ON recently_viewed (user_id, viewed_at DESC);
ALTER TABLE recently_viewed ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS worker_all ON recently_viewed;
CREATE POLICY worker_all ON recently_viewed TO girando_worker USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS rv_own ON recently_viewed;
CREATE POLICY rv_own ON recently_viewed FOR ALL TO girando_app USING (user_id = me()) WITH CHECK (user_id = me());
GRANT SELECT, INSERT, UPDATE, DELETE ON recently_viewed TO girando_app, girando_worker;

CREATE OR REPLACE FUNCTION app.touch_recently_viewed(p_listing uuid) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path = app, public AS $$
DECLARE me uuid := app.app_current_user_id();
BEGIN
  IF me IS NULL THEN RETURN; END IF;
  INSERT INTO app.recently_viewed (user_id, listing_id) VALUES (me, p_listing)
  ON CONFLICT (user_id, listing_id) DO UPDATE SET viewed_at = now();
  DELETE FROM app.recently_viewed r WHERE r.user_id = me AND r.listing_id IN (
    SELECT listing_id FROM app.recently_viewed WHERE user_id = me ORDER BY viewed_at DESC OFFSET 50);
END $$;
GRANT EXECUTE ON FUNCTION app.touch_recently_viewed(uuid) TO girando_app;

-- ---------------------------------------------------------------------
-- 4. Publicidad: métricas por promoción y por día (solo eventos reales)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_promotion_metrics WITH (security_invoker = true) AS
SELECT p.id AS promotion_id,
       count(*) FILTER (WHERE e.event_name = 'promotion_impression') AS impressions,
       count(*) FILTER (WHERE e.event_name = 'promotion_view') AS views,
       count(*) FILTER (WHERE e.event_name = 'promotion_click') AS clicks,
       count(*) FILTER (WHERE e.event_name = 'listing_favorite') AS favorites,
       count(*) FILTER (WHERE e.event_name = 'listing_contact') AS contacts
FROM promotions p
LEFT JOIN analytics_events e ON e.promotion_id = p.id AND e.occurred_at BETWEEN p.starts_at AND p.ends_at
GROUP BY p.id;

-- Métricas de las promociones del propio anunciante (sin abrir analytics_events a los usuarios)
CREATE OR REPLACE FUNCTION app.my_promotion_metrics(p_promo uuid)
RETURNS TABLE (day date, impressions bigint, clicks bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT (e.occurred_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::date,
         count(*) FILTER (WHERE e.event_name = 'promotion_impression'),
         count(*) FILTER (WHERE e.event_name = 'promotion_click')
    FROM app.promotions p JOIN app.analytics_events e ON e.promotion_id = p.id
   WHERE p.id = p_promo
     AND (p.purchased_by = app.app_current_user_id()
          OR (p.paying_agency_id IS NOT NULL AND app.app_is_agency_member(p.paying_agency_id, 'owner','admin'))
          OR app.app_has_staff_role('superadmin','finance'))
     AND e.event_name IN ('promotion_impression','promotion_click')
   GROUP BY 1 ORDER BY 1
$$;
REVOKE EXECUTE ON FUNCTION app.my_promotion_metrics(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.my_promotion_metrics(uuid) TO girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- 5. Recomendaciones: consentimiento de analítica vigente del usuario
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.has_analytics_consent(p_user uuid, p_anonymous uuid DEFAULT NULL) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT coalesce((SELECT c.state = 'granted' AND coalesce(c.analytics, false)
                     FROM app.consents c
                    WHERE c.consent_type = 'cookies' AND c.superseded_at IS NULL
                      AND ((p_user IS NOT NULL AND c.user_id = p_user) OR (p_user IS NULL AND p_anonymous IS NOT NULL AND c.anonymous_id = p_anonymous AND c.user_id IS NULL))
                    ORDER BY c.created_at DESC LIMIT 1), false)
$$;
GRANT EXECUTE ON FUNCTION app.has_analytics_consent(uuid, uuid) TO girando_app, girando_worker;

-- Índice para "similares"
CREATE INDEX IF NOT EXISTS ae_user_recent_idx ON analytics_events (user_id, occurred_at DESC) WHERE user_id IS NOT NULL;

-- Notificaciones sobre entidades nuevas (publicaciones de verticales y ofertas de financiación)
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS nf_entity_type;
ALTER TABLE notifications ADD CONSTRAINT nf_entity_type CHECK (entity_type IS NULL OR entity_type IN
  ('listing','conversation','subscription','payment','verification','agency','sale','promotion','saved_search','report','user','post','financing_offer'));
