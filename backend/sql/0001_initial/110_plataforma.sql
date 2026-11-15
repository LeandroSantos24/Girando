-- =====================================================================
-- 110 · Plataforma: auditoría, analytics, agregados, configuración,
--       retención.
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- audit_logs: append-only (UPDATE/DELETE bloqueados por trigger y grants)
-- ---------------------------------------------------------------------
CREATE TABLE audit_logs (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  actor_type     actor_type NOT NULL,
  actor_user_id  uuid REFERENCES users(id),
  actor_role     text,
  action         text NOT NULL,
  entity_type    text NOT NULL,
  entity_id      uuid,
  before_data    jsonb,
  after_data     jsonb,
  reason         text,
  ip             inet,
  user_agent     text,
  request_id     text,
  CONSTRAINT al_action CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
  CONSTRAINT al_actor CHECK (actor_type IN ('system','provider') OR actor_user_id IS NOT NULL)
);
COMMENT ON TABLE audit_logs IS '[ADMIN] Registro inmutable: quién, rol, acción, entidad, antes/después (solo campos cambiados, con datos sensibles redactados), IP, user agent, motivo. Retención 10 años.';
COMMENT ON COLUMN audit_logs.before_data IS '[ADMIN] Solo columnas modificadas. DNI, documentos, identificadores y tokens se guardan como "[REDACTED]".';
CREATE INDEX al_entity_idx ON audit_logs (entity_type, entity_id, occurred_at DESC);
CREATE INDEX al_actor_idx ON audit_logs (actor_user_id, occurred_at DESC) WHERE actor_user_id IS NOT NULL;
CREATE INDEX al_time_brin ON audit_logs USING brin (occurred_at);

CREATE OR REPLACE FUNCTION app.tg_audit_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs es append-only' USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER al_no_update BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION tg_audit_immutable();
CREATE TRIGGER al_no_truncate BEFORE TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION tg_audit_immutable();

-- ---------------------------------------------------------------------
-- analytics_events: particionada por mes (volumen alto)
-- ---------------------------------------------------------------------
CREATE TABLE analytics_events (
  id             bigint GENERATED ALWAYS AS IDENTITY,
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  event_name     analytics_event_name NOT NULL,
  user_id        uuid,
  anonymous_id   uuid,
  session_id     uuid,
  platform       client_platform,
  listing_id     uuid,
  agency_id      uuid,
  promotion_id   uuid,
  geo_area_id    uuid,
  properties     jsonb NOT NULL DEFAULT '{}',
  consent_analytics boolean NOT NULL DEFAULT false,
  PRIMARY KEY (id, occurred_at),
  CONSTRAINT ae_props CHECK (jsonb_typeof(properties) = 'object')
) PARTITION BY RANGE (occurred_at);
COMMENT ON TABLE analytics_events IS '[ADMIN] Eventos de producto. Sin FKs (volumen y retención independientes). Si el visitante no aceptó analítica, anonymous_id/session_id van NULL y solo se cuentan eventos agregables (vistas, contactos) para las estadísticas del vendedor.';
COMMENT ON COLUMN analytics_events.properties IS '[ADMIN] Contexto del evento (filtros aplicados, placement, origen). Nunca PII.';
CREATE INDEX ae_listing_idx ON analytics_events (listing_id, event_name, occurred_at) WHERE listing_id IS NOT NULL;
CREATE INDEX ae_promotion_idx ON analytics_events (promotion_id, event_name, occurred_at) WHERE promotion_id IS NOT NULL;
CREATE INDEX ae_name_time_idx ON analytics_events (event_name, occurred_at);
CREATE INDEX ae_time_brin ON analytics_events USING brin (occurred_at);
-- Particiones: un job crea la del mes siguiente; ejemplo:
CREATE TABLE analytics_events_2026_10 PARTITION OF analytics_events FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE analytics_events_default PARTITION OF analytics_events DEFAULT;

-- ---------------------------------------------------------------------
-- listing_stats_daily: agregado RECONSTRUIBLE desde analytics_events
-- ---------------------------------------------------------------------
CREATE TABLE listing_stats_daily (
  listing_id     uuid NOT NULL REFERENCES listings(id),
  day            date NOT NULL,
  impressions    integer NOT NULL DEFAULT 0,
  views          integer NOT NULL DEFAULT 0,
  favorites      integer NOT NULL DEFAULT 0,
  unfavorites    integer NOT NULL DEFAULT 0,
  contacts       integer NOT NULL DEFAULT 0,
  contact_reveals integer NOT NULL DEFAULT 0,
  shares         integer NOT NULL DEFAULT 0,
  promotion_clicks integer NOT NULL DEFAULT 0,
  PRIMARY KEY (listing_id, day)
);
COMMENT ON TABLE listing_stats_daily IS '[PROPIETARIO] Métricas por publicación y día. Dato DERIVADO (lo escribe un job idempotente); se puede recalcular desde analytics_events. Existe solo por performance del panel del vendedor.';
CREATE INDEX lsd_day_idx ON listing_stats_daily (day);

-- ---------------------------------------------------------------------
-- app_settings: parámetros de negocio editables sin deploy
-- ---------------------------------------------------------------------
CREATE TABLE app_settings (
  key          text PRIMARY KEY,
  value        jsonb NOT NULL,
  description  text NOT NULL,
  is_public    boolean NOT NULL DEFAULT false,
  updated_by   uuid REFERENCES users(id),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT as_key CHECK (key ~ '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$')
);
COMMENT ON TABLE app_settings IS '[ADMIN] Parámetros: duración de publicación, aviso de vencimiento, máx. fotos, límites anti-spam, muestra mínima para promedios, días de gracia, datos bancarios para transferencias. is_public=true se expone al frontend.';
CREATE TRIGGER as_updated BEFORE UPDATE ON app_settings FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE OR REPLACE FUNCTION app.setting_int(p_key text, p_default int) RETURNS int
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT coalesce((SELECT (value #>> '{}')::int FROM app.app_settings WHERE key = p_key), p_default)
$$;

-- ---------------------------------------------------------------------
-- retention_policies
-- ---------------------------------------------------------------------
CREATE TABLE retention_policies (
  code          text PRIMARY KEY,
  label         text NOT NULL,
  category      retention_category NOT NULL,
  duration      interval NOT NULL,
  starts_from   text NOT NULL,
  action        retention_action NOT NULL,
  is_active     boolean NOT NULL DEFAULT true,
  approved_for_production boolean NOT NULL DEFAULT false,
  updated_by    uuid REFERENCES users(id),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT rp_audit_min CHECK (category <> 'audit' OR duration >= interval '5 years')
);
COMMENT ON TABLE retention_policies IS '[ADMIN] Política de retención configurable. approved_for_production=false hasta revisión legal (Ley 25.326). Borrar multimedia u operativos nunca toca auditoría ni ventas.';
CREATE TRIGGER rpol_updated BEFORE UPDATE ON retention_policies FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();
