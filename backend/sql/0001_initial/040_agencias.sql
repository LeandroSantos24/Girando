-- =====================================================================
-- 040 · Agencias / concesionarias y sus miembros
-- Las publicaciones de una agencia pertenecen a la agencia, no al
-- miembro que las cargó. Los datos comerciales de la agencia son
-- independientes de los datos personales de sus miembros.
-- =====================================================================
SET search_path = app, public;

CREATE TABLE agencies (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               text NOT NULL,
  kind               agency_kind NOT NULL DEFAULT 'agency',
  legal_name         text NOT NULL,
  trade_name         text NOT NULL,
  cuit               char(11) NOT NULL,
  tax_condition      tax_condition,
  description        text,
  logo_public_id     text,
  cover_public_id    text,
  phone_e164         text,
  whatsapp_e164      text,
  email              citext,
  website_url        text,
  instagram_url      text,
  facebook_url       text,
  tiktok_url         text,
  youtube_url        text,
  x_url              text,
  location_id        uuid REFERENCES locations(id),
  geo_area_id        uuid NOT NULL REFERENCES geo_areas(id),
  business_hours     jsonb,
  status             agency_status NOT NULL DEFAULT 'pending',
  status_reason      text,
  verified_at        timestamptz,
  created_by         uuid NOT NULL REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ag_slug CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) <= 60),
  CONSTRAINT ag_cuit CHECK (app.is_valid_cuit(cuit)),
  CONSTRAINT ag_names CHECK (length(btrim(legal_name)) BETWEEN 2 AND 150 AND length(btrim(trade_name)) BETWEEN 2 AND 80),
  CONSTRAINT ag_desc_len CHECK (description IS NULL OR length(description) <= 2000),
  CONSTRAINT ag_phone CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT ag_wa CHECK (whatsapp_e164 IS NULL OR whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT ag_email CHECK (email IS NULL OR email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  CONSTRAINT ag_web CHECK (website_url IS NULL OR website_url ~* '^https://\S+$'),
  CONSTRAINT ag_ig  CHECK (instagram_url IS NULL OR instagram_url ~* '^https://(www\.)?instagram\.com/\S+$'),
  CONSTRAINT ag_fb  CHECK (facebook_url IS NULL OR facebook_url ~* '^https://(www\.|m\.)?facebook\.com/\S+$'),
  CONSTRAINT ag_tt  CHECK (tiktok_url IS NULL OR tiktok_url ~* '^https://(www\.)?tiktok\.com/@\S+$'),
  CONSTRAINT ag_yt  CHECK (youtube_url IS NULL OR youtube_url ~* '^https://(www\.)?youtube\.com/\S+$'),
  CONSTRAINT ag_x   CHECK (x_url IS NULL OR x_url ~* '^https://(www\.)?(x|twitter)\.com/\S+$'),
  CONSTRAINT ag_hours CHECK (business_hours IS NULL OR jsonb_typeof(business_hours) = 'array'),
  CONSTRAINT ag_verified_pair CHECK ((status = 'verified') <= (verified_at IS NOT NULL))
);
COMMENT ON TABLE agencies IS 'Agencia o concesionaria (organización). Los datos comerciales son públicos por naturaleza; los fiscales se muestran solo verificados.';
COMMENT ON COLUMN agencies.slug IS '[PÚBLICO] URL pública: girando.app/agencias/{slug}.';
COMMENT ON COLUMN agencies.kind IS '[PÚBLICO] Agencia / Concesionaria oficial. "Concesionaria oficial" requiere verificación específica (contrato de marca).';
COMMENT ON COLUMN agencies.legal_name IS '[PRIVADO] Razón social. Se usa para facturación y verificación.';
COMMENT ON COLUMN agencies.trade_name IS '[PÚBLICO] Nombre comercial.';
COMMENT ON COLUMN agencies.cuit IS '[PRIVADO] CUIT (11 dígitos, validado con dígito verificador). Único entre agencias no revocadas.';
COMMENT ON COLUMN agencies.tax_condition IS '[PRIVADO] Condición fiscal.';
COMMENT ON COLUMN agencies.phone_e164 IS '[PÚBLICO] Teléfono comercial (no el de los miembros).';
COMMENT ON COLUMN agencies.whatsapp_e164 IS '[PÚBLICO] WhatsApp comercial.';
COMMENT ON COLUMN agencies.email IS '[PÚBLICO] Email comercial.';
COMMENT ON COLUMN agencies.location_id IS '[PÚBLICO] Domicilio comercial del local (a diferencia de un particular).';
COMMENT ON COLUMN agencies.geo_area_id IS '[PÚBLICO] Ciudad/departamento.';
COMMENT ON COLUMN agencies.business_hours IS '[PÚBLICO] [{"day":1..7,"open":"09:00","close":"18:00"}]. JSON porque no se filtra por horario; schema validado en backend.';
COMMENT ON COLUMN agencies.status IS '[PÚBLICO como distintivo] pending/review/verified/rejected/suspended/revoked. Solo staff (o el flujo de verificación) lo cambia.';
COMMENT ON COLUMN agencies.status_reason IS '[ADMIN] Motivo del último cambio.';
CREATE UNIQUE INDEX agencies_slug_uq ON agencies (slug);
CREATE UNIQUE INDEX agencies_cuit_uq ON agencies (cuit) WHERE status NOT IN ('rejected','revoked');
CREATE INDEX agencies_status_idx ON agencies (status);
CREATE INDEX agencies_geo_idx ON agencies (geo_area_id);
CREATE TRIGGER agencies_updated BEFORE UPDATE ON agencies FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE agency_members (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id    uuid NOT NULL REFERENCES agencies(id),
  user_id      uuid NOT NULL REFERENCES users(id),
  role         agency_member_role NOT NULL DEFAULT 'seller',
  status       member_status NOT NULL DEFAULT 'invited',
  invited_by   uuid REFERENCES users(id),
  invited_at   timestamptz NOT NULL DEFAULT now(),
  joined_at    timestamptz,
  removed_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT am_joined CHECK ((status = 'active') <= (joined_at IS NOT NULL))
);
COMMENT ON TABLE agency_members IS '[PRIVADO] Usuarios que operan una agencia (N:N usuarios↔agencias con rol). Límite de miembros según plan.';
CREATE UNIQUE INDEX agency_members_uq ON agency_members (agency_id, user_id) WHERE status <> 'removed';
CREATE UNIQUE INDEX agency_one_owner_uq ON agency_members (agency_id) WHERE role = 'owner' AND status = 'active';
CREATE INDEX agency_members_user_idx ON agency_members (user_id) WHERE status = 'active';
CREATE TRIGGER agency_members_updated BEFORE UPDATE ON agency_members FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ¿El usuario actual es miembro activo de la agencia (con alguno de los roles)?
CREATE OR REPLACE FUNCTION app.app_is_agency_member(p_agency uuid, VARIADIC p_roles agency_member_role[] DEFAULT ARRAY['owner','admin','seller']::agency_member_role[])
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.agency_members m
                 WHERE m.agency_id = p_agency AND m.user_id = app.app_current_user_id()
                   AND m.status = 'active' AND m.role = ANY (p_roles))
$$;

-- Reputación externa (Google). NUNCA se promedia con la de Girando.
CREATE TABLE external_ratings (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agency_id       uuid NOT NULL REFERENCES agencies(id),
  provider        text NOT NULL DEFAULT 'google',
  external_place_id text NOT NULL,
  rating          numeric(2,1),
  review_count    integer,
  source_url      text,
  synced_at       timestamptz,
  sync_error      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT er_provider CHECK (provider IN ('google')),
  CONSTRAINT er_rating CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
  CONSTRAINT er_count CHECK (review_count IS NULL OR review_count >= 0),
  UNIQUE (agency_id, provider)
);
COMMENT ON TABLE external_ratings IS '[PÚBLICO] Puntaje y cantidad de Google (Places API), con enlace a la fuente y fecha de sincronización. PENDIENTE DE INTEGRACIÓN REAL.';
