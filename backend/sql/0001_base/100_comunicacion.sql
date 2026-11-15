-- =====================================================================
-- 100 · Notificaciones y emails
-- evento de dominio → notification_types (config) → notifications (app)
--                                               → email_events (cola) → proveedor
-- Si no hay proveedor de email configurado, email_events queda 'pending'
-- con last_error = 'provider_not_configured'. NUNCA se marca 'sent' sin
-- confirmación del proveedor.
-- =====================================================================
SET search_path = app, public;

CREATE TABLE email_templates (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL,
  version        integer NOT NULL DEFAULT 1,
  locale         text NOT NULL DEFAULT 'es-AR',
  subject        text NOT NULL,
  body_html      text NOT NULL,
  body_text      text NOT NULL,
  variables      text[] NOT NULL DEFAULT '{}',
  is_commercial  boolean NOT NULL DEFAULT false,
  status         template_status NOT NULL DEFAULT 'draft',
  updated_by     uuid REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT et_code CHECK (code ~ '^[a-z][a-z0-9_.]{2,60}$'),
  UNIQUE (code, locale, version)
);
COMMENT ON TABLE email_templates IS '[ADMIN] Plantillas versionadas (bienvenida, verificar email, recuperar contraseña, publicación aprobada/rechazada, nueva consulta, pago aprobado/rechazado, suscripción renovada/cancelada, verificación aprobada...).';
CREATE UNIQUE INDEX et_one_active_uq ON email_templates (code, locale) WHERE status = 'active';
CREATE TRIGGER et_updated BEFORE UPDATE ON email_templates FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE notification_types (
  code              text PRIMARY KEY,
  category          notification_category NOT NULL,
  description       text NOT NULL,
  is_commercial     boolean NOT NULL DEFAULT false,
  is_mandatory      boolean NOT NULL DEFAULT false,
  in_app_enabled    boolean NOT NULL DEFAULT true,
  email_enabled     boolean NOT NULL DEFAULT false,
  push_enabled      boolean NOT NULL DEFAULT false,
  email_template_code text,
  is_active         boolean NOT NULL DEFAULT true,
  updated_by        uuid REFERENCES users(id),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT nt_code CHECK (code ~ '^[a-z][a-z0-9_]*\.[a-z0-9_.]+$'),
  CONSTRAINT nt_mandatory_not_commercial CHECK (NOT (is_mandatory AND is_commercial)),
  CONSTRAINT nt_email_template CHECK (NOT email_enabled OR email_template_code IS NOT NULL)
);
COMMENT ON TABLE notification_types IS '[ADMIN] Catálogo de eventos notificables y sus canales (panel Admin → Notificaciones). Operativas (seguridad, pagos, moderación) son obligatorias; comerciales requieren consentimiento.';
CREATE TRIGGER nt_updated BEFORE UPDATE ON notification_types FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE notification_preferences (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category    notification_category NOT NULL,
  channel     notification_channel NOT NULL,
  enabled     boolean NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, category, channel)
);
COMMENT ON TABLE notification_preferences IS '[PROPIETARIO] Preferencias por categoría/canal. Ausencia de fila = default del tipo. Categorías security/payments/moderation no se pueden apagar (lo valida el backend). marketing además requiere consents vigente.';

CREATE TABLE notifications (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type_code      text NOT NULL REFERENCES notification_types(code),
  category       notification_category NOT NULL,
  title          text NOT NULL,
  body           text NOT NULL,
  entity_type    text,
  entity_id      uuid,
  action_path    text,
  read_at        timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT nf_title CHECK (length(title) <= 120),
  CONSTRAINT nf_body CHECK (length(body) <= 500),
  CONSTRAINT nf_entity_pair CHECK ((entity_type IS NULL) = (entity_id IS NULL)),
  CONSTRAINT nf_entity_type CHECK (entity_type IS NULL OR entity_type IN ('listing','conversation','subscription','payment','verification','agency','sale','promotion','saved_search','report','user')),
  CONSTRAINT nf_path CHECK (action_path IS NULL OR action_path ~ '^/[A-Za-z0-9/_?=&.-]*$')
);
COMMENT ON TABLE notifications IS '[PROPIETARIO] Bandeja in-app. entity_type/entity_id es una referencia de navegación (no FK) porque la notificación debe sobrevivir aunque la entidad se anonimice.';
CREATE INDEX nf_user_idx ON notifications (user_id, created_at DESC);
CREATE INDEX nf_unread_idx ON notifications (user_id) WHERE read_at IS NULL;

CREATE TABLE email_events (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id          uuid NOT NULL REFERENCES email_templates(id),
  notification_id      uuid REFERENCES notifications(id) ON DELETE SET NULL,
  to_user_id           uuid REFERENCES users(id) ON DELETE SET NULL,
  to_email             citext NOT NULL,
  event_code           text NOT NULL,
  variables            jsonb NOT NULL DEFAULT '{}',
  status               email_status NOT NULL DEFAULT 'pending',
  provider             text,
  provider_message_id  text,
  attempts             smallint NOT NULL DEFAULT 0,
  last_error           text,
  scheduled_at         timestamptz NOT NULL DEFAULT now(),
  sent_at              timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ee_sent CHECK ((status = 'sent') = (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)),
  CONSTRAINT ee_failed CHECK (status <> 'failed' OR last_error IS NOT NULL),
  CONSTRAINT ee_vars CHECK (jsonb_typeof(variables) = 'object')
);
COMMENT ON TABLE email_events IS '[ADMIN] Cola/registro de emails. "sent" exige provider_message_id (confirmación real del proveedor). PROVEEDOR PENDIENTE DE CONFIGURAR.';
COMMENT ON COLUMN email_events.to_email IS '[PRIVADO] Destinatario al momento del envío. Retención: operativos.';
COMMENT ON COLUMN email_events.variables IS '[PRIVADO] Variables de la plantilla. No incluir datos sensibles (DNI, documentos, identificadores del vehículo).';
CREATE INDEX ee_queue_idx ON email_events (scheduled_at) WHERE status = 'pending';
CREATE INDEX ee_user_idx ON email_events (to_user_id, created_at DESC);
CREATE UNIQUE INDEX ee_provider_msg_uq ON email_events (provider, provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE TRIGGER ee_updated BEFORE UPDATE ON email_events FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
