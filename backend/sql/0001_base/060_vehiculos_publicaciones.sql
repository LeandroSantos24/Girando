-- =====================================================================
-- 060 · Vehículos, identificadores, publicaciones, fotos y contacto
-- Vehículo  = el objeto físico (catálogo + año + datos técnicos propios)
-- Publicación = la oferta (precio, km al publicar, texto, fotos, estado)
-- Un vehículo puede tener varias publicaciones en el tiempo, pero solo
-- una "abierta" a la vez.
-- =====================================================================
SET search_path = app, public;

-- Código público corto y no secuencial (no revela volumen de negocio)
CREATE OR REPLACE FUNCTION app.gen_public_code(prefix text) RETURNS text
LANGUAGE plpgsql VOLATILE AS $$
DECLARE
  alphabet constant text := '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
  b bytea := gen_random_bytes(8);
  out text := '';
BEGIN
  FOR i IN 0..7 LOOP
    out := out || substr(alphabet, (get_byte(b, i) % 32) + 1, 1);
  END LOOP;
  RETURN prefix || '-' || out;
END $$;

-- ---------------------------------------------------------------------
-- vehicles
-- ---------------------------------------------------------------------
CREATE TABLE vehicles (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id    uuid NOT NULL REFERENCES users(id),
  agency_id        uuid REFERENCES agencies(id),
  version_id       uuid REFERENCES vehicle_versions(id) ON DELETE RESTRICT,
  engine_id        uuid REFERENCES vehicle_engines(id) ON DELETE RESTRICT,
  year             smallint,
  color            text,
  fuel_override    fuel_type,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT veh_version_engine_fk FOREIGN KEY (version_id, engine_id)
    REFERENCES vehicle_version_engines (version_id, engine_id) ON DELETE RESTRICT,
  CONSTRAINT veh_engine_needs_version CHECK (engine_id IS NULL OR version_id IS NOT NULL),
  CONSTRAINT veh_year CHECK (year IS NULL OR year BETWEEN 1900 AND 2100),
  CONSTRAINT veh_color CHECK (color IS NULL OR length(color) <= 40)
);
COMMENT ON TABLE vehicles IS 'Vehículo físico. Su identidad es el catálogo (version+engine), nunca texto libre. Marca/modelo/generación se derivan de la versión (no se duplican).';
COMMENT ON COLUMN vehicles.owner_user_id IS '[PRIVADO] Cuenta responsable en Girando (no implica titularidad registral).';
COMMENT ON COLUMN vehicles.agency_id IS '[PÚBLICO vía publicación] Si pertenece al stock de una agencia.';
COMMENT ON COLUMN vehicles.version_id IS '[PÚBLICO] NULL solo en borradores. Obligatorio para enviar a revisión.';
COMMENT ON COLUMN vehicles.engine_id IS '[PÚBLICO] Debe ser una combinación válida de vehicle_version_engines.';
COMMENT ON COLUMN vehicles.year IS '[PÚBLICO] Año modelo. Validado contra el rango de la versión/generación al publicar.';
COMMENT ON COLUMN vehicles.fuel_override IS '[PÚBLICO] Solo si difiere del motor de catálogo (p.ej. conversión a GNC).';
CREATE INDEX vehicles_version_idx ON vehicles (version_id);
CREATE INDEX vehicles_owner_idx ON vehicles (owner_user_id);
CREATE INDEX vehicles_agency_idx ON vehicles (agency_id) WHERE agency_id IS NOT NULL;
CREATE TRIGGER vehicles_updated BEFORE UPDATE ON vehicles FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- vehicle_identifiers: patente, VIN, chasis, motor. SENSIBLES.
-- Una fila por identificador → historial y verificación independiente.
-- ---------------------------------------------------------------------
CREATE TABLE vehicle_identifiers (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id       uuid NOT NULL REFERENCES vehicles(id),
  type             identifier_type NOT NULL,
  value            text NOT NULL,
  country_code     char(2) NOT NULL DEFAULT 'AR',
  status           identifier_status NOT NULL DEFAULT 'declared',
  is_current       boolean NOT NULL DEFAULT true,
  declared_by      uuid NOT NULL REFERENCES users(id),
  verified_by      uuid REFERENCES users(id),
  verified_at      timestamptz,
  rejection_reason text,
  purge_after      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vi_value_norm CHECK (value = app.normalize_plate(value)),
  CONSTRAINT vi_plate_ar CHECK (type <> 'plate' OR country_code <> 'AR' OR app.is_valid_ar_plate(value)),
  CONSTRAINT vi_vin CHECK (type <> 'vin' OR value ~ '^[A-HJ-NPR-Z0-9]{17}$'),
  CONSTRAINT vi_other_len CHECK (type IN ('plate','vin') OR length(value) BETWEEN 5 AND 30),
  CONSTRAINT vi_verified_pair CHECK ((status = 'verified') = (verified_at IS NOT NULL)),
  CONSTRAINT vi_no_self_verify CHECK (verified_by IS NULL OR verified_by <> declared_by)
);
COMMENT ON TABLE vehicle_identifiers IS '[SENSIBLE] Nunca públicos. Solo dueño del vehículo y staff. Se usan para verificación y detección de fraude (mismo VIN/patente en publicaciones de distintos dueños).';
COMMENT ON COLUMN vehicle_identifiers.value IS '[SENSIBLE] Normalizado: mayúsculas, sin espacios ni guiones.';
COMMENT ON COLUMN vehicle_identifiers.status IS '[PRIVADO] declared → pending → verified | rejected.';
COMMENT ON COLUMN vehicle_identifiers.purge_after IS '[SISTEMA] Fecha de borrado por retención (p.ej. patente de vehículo vendido: 24 meses).';
CREATE UNIQUE INDEX vi_current_uq ON vehicle_identifiers (vehicle_id, type) WHERE is_current;
CREATE INDEX vi_lookup_idx ON vehicle_identifiers (type, country_code, value);
CREATE INDEX vi_purge_idx ON vehicle_identifiers (purge_after) WHERE purge_after IS NOT NULL;
CREATE TRIGGER vi_updated BEFORE UPDATE ON vehicle_identifiers FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- listings
-- ---------------------------------------------------------------------
CREATE TABLE listings (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  public_code          text NOT NULL DEFAULT app.gen_public_code('P'),
  owner_user_id        uuid NOT NULL REFERENCES users(id),
  agency_id            uuid REFERENCES agencies(id),
  created_by           uuid NOT NULL REFERENCES users(id),
  vehicle_id           uuid NOT NULL REFERENCES vehicles(id),
  geo_area_id          uuid REFERENCES geo_areas(id),
  location_id          uuid REFERENCES locations(id),
  show_neighborhood    boolean NOT NULL DEFAULT false,
  title                text NOT NULL DEFAULT '',
  description          text,
  price_amount         numeric(14,2),
  currency             currency_code NOT NULL DEFAULT 'ARS',
  condition            vehicle_condition NOT NULL DEFAULT 'used',
  km                   integer,
  is_financeable       boolean NOT NULL DEFAULT false,
  accepts_trade_in     boolean NOT NULL DEFAULT false,
  video_url            text,
  status               listing_status NOT NULL DEFAULT 'draft',
  status_reason        text,
  status_changed_at    timestamptz NOT NULL DEFAULT now(),
  submitted_at         timestamptz,
  first_published_at   timestamptz,
  published_at         timestamptz,
  expires_at           timestamptz,
  paused_at            timestamptz,
  sold_at              timestamptz,
  deleted_at           timestamptz,
  renewal_count        smallint NOT NULL DEFAULT 0,
  reviewed_by          uuid REFERENCES users(id),
  reviewed_at          timestamptz,
  duplicate_of_listing_id uuid REFERENCES listings(id),
  search_vector        tsvector GENERATED ALWAYS AS (
                         setweight(to_tsvector('spanish', app.f_unaccent(coalesce(title, ''))), 'A') ||
                         setweight(to_tsvector('spanish', app.f_unaccent(coalesce(description, ''))), 'B')) STORED,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT li_title_len CHECK (length(title) <= 90),
  CONSTRAINT li_desc_len CHECK (description IS NULL OR length(description) <= 5000),
  CONSTRAINT li_price CHECK (price_amount IS NULL OR (price_amount > 0 AND price_amount < 100000000000)),
  CONSTRAINT li_km CHECK (km IS NULL OR km BETWEEN 0 AND 2000000),
  CONSTRAINT li_video CHECK (video_url IS NULL OR video_url ~* '^https://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_-]{6,}'),
  CONSTRAINT li_publishable CHECK (status IN ('draft','deleted') OR (
      geo_area_id IS NOT NULL AND price_amount IS NOT NULL AND km IS NOT NULL AND length(btrim(title)) >= 5)),
  CONSTRAINT li_sold_at CHECK ((status = 'sold') = (sold_at IS NOT NULL)),
  CONSTRAINT li_deleted_at CHECK ((status = 'deleted') = (deleted_at IS NOT NULL)),
  CONSTRAINT li_published_dates CHECK (status <> 'published' OR (published_at IS NOT NULL AND expires_at IS NOT NULL))
);
COMMENT ON TABLE listings IS 'Publicación (oferta) de un vehículo. Pertenece a la agencia si agency_id no es NULL; si no, al usuario.';
COMMENT ON COLUMN listings.public_code IS '[PÚBLICO] Código corto para URL y soporte (P-7K2M9QXA).';
COMMENT ON COLUMN listings.owner_user_id IS '[PRIVADO] Responsable. En agencias: el dueño de la cuenta/agencia; created_by = el vendedor que la cargó.';
COMMENT ON COLUMN listings.agency_id IS '[PÚBLICO] Agencia dueña de la publicación.';
COMMENT ON COLUMN listings.created_by IS '[ADMIN] Miembro que la creó (trazabilidad dentro de la agencia).';
COMMENT ON COLUMN listings.geo_area_id IS '[PÚBLICO] Ubicación aproximada que se muestra ("Godoy Cruz, Mendoza").';
COMMENT ON COLUMN listings.location_id IS '[PRIVADO] Dirección exacta opcional (para coordinar visitas). Nunca pública.';
COMMENT ON COLUMN listings.title IS '[PÚBLICO] Texto libre del vendedor. No alimenta filtros.';
COMMENT ON COLUMN listings.description IS '[PÚBLICO] Texto libre. Girando no genera texto en nombre del vendedor.';
COMMENT ON COLUMN listings.price_amount IS '[PÚBLICO] Precio publicado. Cambios quedan en listing_price_history.';
COMMENT ON COLUMN listings.km IS '[PÚBLICO] Kilometraje declarado al publicar (no verificado salvo producto de verificación).';
COMMENT ON COLUMN listings.status IS '[PÚBLICO solo "published"] Máquina de estados validada por trigger (ver 120_reglas.sql).';
COMMENT ON COLUMN listings.status_reason IS '[PROPIETARIO] Motivo de moderación visible al vendedor ("las fotos no muestran el vehículo").';
COMMENT ON COLUMN listings.expires_at IS '[PROPIETARIO] published_at + duración configurada (60 días). Aviso 3 días antes.';
COMMENT ON COLUMN listings.duplicate_of_listing_id IS '[ADMIN] Marca de posible duplicado para revisión. No bloquea automáticamente.';
CREATE UNIQUE INDEX listings_code_uq ON listings (public_code);
CREATE UNIQUE INDEX listings_one_open_per_vehicle_uq ON listings (vehicle_id)
  WHERE status IN ('draft','pending','published','paused','requires_changes','expired');
CREATE INDEX listings_published_recent_idx ON listings (published_at DESC) WHERE status = 'published';
CREATE INDEX listings_published_price_idx ON listings (currency, price_amount) WHERE status = 'published';
CREATE INDEX listings_published_geo_idx ON listings (geo_area_id) WHERE status = 'published';
CREATE INDEX listings_published_km_idx ON listings (km) WHERE status = 'published';
CREATE INDEX listings_owner_idx ON listings (owner_user_id, status);
CREATE INDEX listings_agency_idx ON listings (agency_id, status) WHERE agency_id IS NOT NULL;
CREATE INDEX listings_moderation_idx ON listings (submitted_at) WHERE status = 'pending';
CREATE INDEX listings_expiry_idx ON listings (expires_at) WHERE status = 'published';
CREATE INDEX listings_fts_idx ON listings USING gin (search_vector);
CREATE TRIGGER listings_updated BEFORE UPDATE ON listings FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- listing_images (referencias a Cloudinary; nunca binarios en la DB)
-- ---------------------------------------------------------------------
CREATE TABLE listing_images (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id         uuid NOT NULL REFERENCES listings(id),
  storage_provider   image_storage_provider NOT NULL DEFAULT 'cloudinary',
  public_id          text NOT NULL,
  provider_version   bigint,
  provider_asset_id  text,
  secure_url         text NOT NULL,
  etag               text,
  format             text NOT NULL,
  kind               image_kind NOT NULL DEFAULT 'additional',
  position           smallint NOT NULL,
  is_cover           boolean NOT NULL DEFAULT false,
  width              integer NOT NULL,
  height             integer NOT NULL,
  bytes              integer NOT NULL,
  status             image_status NOT NULL DEFAULT 'active',
  uploaded_by        uuid NOT NULL REFERENCES users(id),
  uploaded_at        timestamptz NOT NULL DEFAULT now(),
  purge_after        timestamptz,
  purged_at          timestamptz,
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT lim_format CHECK (format IN ('jpg','jpeg','png','webp')),
  CONSTRAINT lim_bytes CHECK (bytes BETWEEN 1 AND 10485760),
  CONSTRAINT lim_dims CHECK (width BETWEEN 320 AND 12000 AND height BETWEEN 240 AND 12000),
  CONSTRAINT lim_position CHECK (position BETWEEN 1 AND 6),
  CONSTRAINT lim_url CHECK ((storage_provider = 'cloudinary' AND secure_url ~ '^https://res\.cloudinary\.com/')
                         OR (storage_provider = 'local_dev' AND secure_url ~ '^/media/')),
  CONSTRAINT lim_cover_active CHECK (NOT is_cover OR status = 'active'),
  CONSTRAINT lim_purged CHECK ((status = 'purged') = (purged_at IS NOT NULL))
);
COMMENT ON TABLE listing_images IS 'Fotos de la publicación. Máx. 6 activas, JPG/PNG/WEBP, ≤10 MB. Solo referencias al proveedor de almacenamiento (nunca binarios en la DB).';
COMMENT ON COLUMN listing_images.public_id IS '[PÚBLICO] Cloudinary public_id (o clave local en desarrollo) para construir URLs transformadas.';
COMMENT ON COLUMN listing_images.storage_provider IS '[SISTEMA] cloudinary en producción; local_dev SOLO en desarrollo (disco local, nunca en producción).';
COMMENT ON COLUMN listing_images.secure_url IS '[PÚBLICO] URL original devuelta por Cloudinary (solo referencia; el frontend usa transformaciones).';
COMMENT ON COLUMN listing_images.etag IS '[ADMIN] Hash del archivo (MD5 de Cloudinary) para detectar fotos repetidas entre publicaciones.';
COMMENT ON COLUMN listing_images.kind IS '[PÚBLICO] Posición sugerida (frente, trasera, laterales, interior, adicional). No obligatoria.';
COMMENT ON COLUMN listing_images.is_cover IS '[PÚBLICO] Portada. Exactamente una por publicación con fotos (índice parcial único).';
COMMENT ON COLUMN listing_images.status IS '[SISTEMA] uploading → active → replaced/deleted → purge_scheduled → purged (borrado real en Cloudinary).';
COMMENT ON COLUMN listing_images.purge_after IS '[SISTEMA] Cuándo borrar en Cloudinary según retention_policies (vendida: 7 días).';
CREATE UNIQUE INDEX lim_public_id_uq ON listing_images (storage_provider, public_id);
-- EXCLUDE diferible (no índice único) para poder reordenar/cambiar portada en una transacción
ALTER TABLE listing_images ADD CONSTRAINT lim_position_uq EXCLUDE USING btree (listing_id WITH =, position WITH =)
  WHERE (status = 'active') DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE listing_images ADD CONSTRAINT lim_one_cover_uq EXCLUDE USING btree (listing_id WITH =)
  WHERE (is_cover AND status = 'active') DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX lim_purge_idx ON listing_images (purge_after) WHERE status = 'purge_scheduled';
CREATE INDEX lim_etag_idx ON listing_images (etag) WHERE etag IS NOT NULL AND status = 'active';
CREATE TRIGGER lim_updated BEFORE UPDATE ON listing_images FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- listing_contacts: datos de contacto DE LA PUBLICACIÓN (1:1)
-- Por defecto solo se contacta por chat interno.
-- ---------------------------------------------------------------------
CREATE TABLE listing_contacts (
  listing_id      uuid PRIMARY KEY REFERENCES listings(id),
  source          contact_source NOT NULL DEFAULT 'user_profile',
  phone_e164      text,
  show_phone      boolean NOT NULL DEFAULT false,
  whatsapp_e164   text,
  show_whatsapp   boolean NOT NULL DEFAULT false,
  email           citext,
  show_email      boolean NOT NULL DEFAULT false,
  instagram_url   text,
  tiktok_url      text,
  facebook_url    text,
  website_url     text,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT lc_phone CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT lc_wa CHECK (whatsapp_e164 IS NULL OR whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  CONSTRAINT lc_email CHECK (email IS NULL OR email ~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'),
  CONSTRAINT lc_show_needs_value CHECK ((NOT show_phone OR phone_e164 IS NOT NULL) AND (NOT show_whatsapp OR whatsapp_e164 IS NOT NULL) AND (NOT show_email OR email IS NOT NULL)),
  CONSTRAINT lc_ig CHECK (instagram_url IS NULL OR instagram_url ~* '^https://(www\.)?instagram\.com/\S+$'),
  CONSTRAINT lc_tt CHECK (tiktok_url IS NULL OR tiktok_url ~* '^https://(www\.)?tiktok\.com/@\S+$'),
  CONSTRAINT lc_fb CHECK (facebook_url IS NULL OR facebook_url ~* '^https://(www\.|m\.)?facebook\.com/\S+$'),
  CONSTRAINT lc_web CHECK (website_url IS NULL OR website_url ~* '^https://\S+$')
);
COMMENT ON TABLE listing_contacts IS 'Canales de contacto de la publicación, separados de los datos personales. Teléfono/WhatsApp/email se revelan solo si show_*=true y a usuarios autenticados (evento listing_contact_reveal).';
COMMENT ON COLUMN listing_contacts.phone_e164 IS '[PRIVADO salvo show_phone] Copia editable del default del perfil o de la agencia.';
COMMENT ON COLUMN listing_contacts.whatsapp_e164 IS '[PRIVADO salvo show_whatsapp].';
COMMENT ON COLUMN listing_contacts.email IS '[PRIVADO salvo show_email].';
COMMENT ON COLUMN listing_contacts.instagram_url IS '[PÚBLICO] Redes comerciales opcionales.';
CREATE TRIGGER lc_updated BEFORE UPDATE ON listing_contacts FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- ---------------------------------------------------------------------
-- Historiales (append-only)
-- ---------------------------------------------------------------------
CREATE TABLE listing_status_history (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  listing_id    uuid NOT NULL REFERENCES listings(id),
  from_status   listing_status,
  to_status     listing_status NOT NULL,
  reason        text,
  actor_user_id uuid REFERENCES users(id),
  actor_type    actor_type NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE listing_status_history IS '[PROPIETARIO] Cada transición de estado (la escribe el trigger). Base para "tiempo hasta venta", moderación e historial del vendedor.';
CREATE INDEX lsh_listing_idx ON listing_status_history (listing_id, created_at);

CREATE TABLE listing_price_history (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  listing_id    uuid NOT NULL REFERENCES listings(id),
  old_amount    numeric(14,2),
  old_currency  currency_code,
  new_amount    numeric(14,2) NOT NULL,
  new_currency  currency_code NOT NULL,
  changed_by    uuid REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE listing_price_history IS '[PÚBLICO agregado] Cambios de precio. Alimenta "Bajó el precio de un favorito" y estadísticas precio publicado vs final.';
CREATE INDEX lph_listing_idx ON listing_price_history (listing_id, created_at);

-- Visibilidad de columnas restantes (para el diccionario)
COMMENT ON COLUMN listings.currency IS '[PÚBLICO] ARS o USD.';
COMMENT ON COLUMN listings.condition IS '[PÚBLICO] Nuevo / usado.';
COMMENT ON COLUMN listings.is_financeable IS '[PÚBLICO] El vendedor ofrece financiación.';
COMMENT ON COLUMN listings.accepts_trade_in IS '[PÚBLICO] Acepta permuta.';
COMMENT ON COLUMN listings.video_url IS '[PÚBLICO] Video de YouTube opcional (solo youtube.com / youtu.be).';
COMMENT ON COLUMN listings.published_at IS '[PÚBLICO] Inicio del ciclo de publicación actual.';
COMMENT ON COLUMN listings.first_published_at IS '[PÚBLICO] Primera publicación (base de "días hasta la venta").';
COMMENT ON COLUMN listings.show_neighborhood IS '[PROPIETARIO] Mostrar barrio (nunca calle ni número).';
COMMENT ON COLUMN listings.search_vector IS '[SISTEMA] Índice de texto (título + descripción, español, sin tildes).';
COMMENT ON COLUMN listing_images.format IS '[PÚBLICO] jpg/png/webp.';
COMMENT ON COLUMN listing_images.position IS '[PÚBLICO] Orden 1..6 (reordenable sin tocar Cloudinary).';
COMMENT ON COLUMN listing_images.width IS '[PÚBLICO] Ancho en px (para layout/srcset).';
COMMENT ON COLUMN listing_images.height IS '[PÚBLICO] Alto en px.';
COMMENT ON COLUMN listing_images.bytes IS '[ADMIN] Tamaño (≤10 MB).';
COMMENT ON COLUMN vehicles.color IS '[PÚBLICO] Color declarado.';
