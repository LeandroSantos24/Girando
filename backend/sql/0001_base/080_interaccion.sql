-- =====================================================================
-- 080 · Interacción: favoritos, búsquedas guardadas, conversaciones,
--       mensajes.
-- =====================================================================
SET search_path = app, public;

CREATE TABLE favorites (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id  uuid NOT NULL REFERENCES listings(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, listing_id)
);
COMMENT ON TABLE favorites IS '[PROPIETARIO] Quién guardó qué. Al vendedor solo le llega el CONTEO (nunca quiénes). Métricas históricas vía analytics_events (listing_favorite/unfavorite).';
CREATE INDEX favorites_listing_idx ON favorites (listing_id);

CREATE TABLE saved_searches (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name                  text NOT NULL,
  filters               jsonb NOT NULL,
  filters_version       smallint NOT NULL DEFAULT 1,
  brand_id              uuid REFERENCES vehicle_brands(id),
  model_id              uuid REFERENCES vehicle_models(id),
  geo_area_id           uuid REFERENCES geo_areas(id),
  notification_enabled  boolean NOT NULL DEFAULT false,
  notify_frequency      text NOT NULL DEFAULT 'daily',
  last_notified_at      timestamptz,
  last_seen_listing_published_at timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ss_name CHECK (length(btrim(name)) BETWEEN 1 AND 60),
  CONSTRAINT ss_filters_obj CHECK (jsonb_typeof(filters) = 'object'),
  CONSTRAINT ss_freq CHECK (notify_frequency IN ('instant','daily','weekly'))
);
COMMENT ON TABLE saved_searches IS '[PROPIETARIO] Búsquedas guardadas. filters = el mismo DTO de búsqueda de la API (versionado y validado por Pydantic): marca(s), modelo(s), año min/max, precio min/max+moneda, km, ubicación, combustible, transmisión, carrocería, condición, tipo de vendedor, etc.';
COMMENT ON COLUMN saved_searches.brand_id IS '[SISTEMA] Prefiltro extraído de filters para encontrar rápido qué búsquedas matchean una publicación nueva.';
COMMENT ON COLUMN saved_searches.notification_enabled IS '[PROPIETARIO] "Avisarme cuando aparezca un vehículo que coincida".';
CREATE INDEX ss_user_idx ON saved_searches (user_id);
CREATE INDEX ss_match_idx ON saved_searches (model_id, brand_id) WHERE notification_enabled;
CREATE TRIGGER ss_updated BEFORE UPDATE ON saved_searches FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- conversations: comprador ↔ vendedor (usuario o agencia) sobre UNA publicación
-- ---------------------------------------------------------------------
CREATE TABLE conversations (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id         uuid NOT NULL REFERENCES listings(id),
  buyer_user_id      uuid NOT NULL REFERENCES users(id),
  seller_user_id     uuid NOT NULL REFERENCES users(id),
  seller_agency_id   uuid REFERENCES agencies(id),
  status             conversation_status NOT NULL DEFAULT 'open',
  blocked_by_user_id uuid REFERENCES users(id),
  blocked_at         timestamptz,
  seller_first_reply_at timestamptz,
  last_message_at    timestamptz,
  buyer_archived_at  timestamptz,
  seller_archived_at timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cv_not_self CHECK (buyer_user_id <> seller_user_id),
  CONSTRAINT cv_blocked CHECK ((status = 'blocked') = (blocked_at IS NOT NULL AND blocked_by_user_id IS NOT NULL))
);
COMMENT ON TABLE conversations IS '[PROPIETARIO de ambas partes] Conversación → publicación → vehículo. Si la publicación es de agencia, cualquier miembro activo responde por la agencia.';
COMMENT ON COLUMN conversations.seller_user_id IS '[PRIVADO] Dueño de la publicación al momento de iniciar.';
COMMENT ON COLUMN conversations.seller_first_reply_at IS '[SISTEMA] Habilita calificar ("consulta respondida") y mide tiempo de respuesta.';
CREATE UNIQUE INDEX cv_one_per_buyer_listing_uq ON conversations (listing_id, buyer_user_id);
CREATE INDEX cv_buyer_idx ON conversations (buyer_user_id, last_message_at DESC);
CREATE INDEX cv_seller_idx ON conversations (seller_user_id, last_message_at DESC);
CREATE INDEX cv_agency_idx ON conversations (seller_agency_id, last_message_at DESC) WHERE seller_agency_id IS NOT NULL;
CREATE INDEX cv_buyer_created_idx ON conversations (buyer_user_id, created_at);  -- anti-spam: nuevas por día
CREATE TRIGGER cv_updated BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE messages (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  uuid NOT NULL REFERENCES conversations(id),
  sender_user_id   uuid NOT NULL REFERENCES users(id),
  sender_side      participant_side NOT NULL,
  body             text NOT NULL,
  body_hash        bytea GENERATED ALWAYS AS (digest(lower(btrim(body)), 'sha256')) STORED,
  read_at          timestamptz,
  deleted_at       timestamptz,
  visibility       message_visibility NOT NULL DEFAULT 'visible',
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT msg_body CHECK (length(btrim(body)) BETWEEN 1 AND 2000)
);
COMMENT ON TABLE messages IS '[PROPIETARIO de ambas partes] Mensajes. Borrado lógico por el autor (deleted_at). Staff solo accede ante un reporte (auditado).';
COMMENT ON COLUMN messages.body_hash IS '[SISTEMA] Anti-spam: impide repetir el mismo mensaje seguido y detecta mensajes masivos idénticos.';
COMMENT ON COLUMN messages.read_at IS '[PROPIETARIO] Leído por la contraparte.';
COMMENT ON COLUMN messages.visibility IS '[ADMIN] hidden_by_moderation tras un reporte resuelto.';
CREATE INDEX msg_conversation_idx ON messages (conversation_id, created_at);
CREATE INDEX msg_unread_idx ON messages (conversation_id) WHERE read_at IS NULL AND deleted_at IS NULL;
CREATE INDEX msg_hash_idx ON messages (sender_user_id, body_hash, created_at DESC);

ALTER TABLE reviews ADD CONSTRAINT rv_conversation_fk FOREIGN KEY (conversation_id) REFERENCES conversations(id);
ALTER TABLE reports ADD CONSTRAINT rp_message_fk FOREIGN KEY (message_id) REFERENCES messages(id);
ALTER TABLE moderation_actions ADD CONSTRAINT ma_message_fk FOREIGN KEY (message_id) REFERENCES messages(id);
