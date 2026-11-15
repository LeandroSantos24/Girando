-- =====================================================================
-- 050 · Catálogo maestro de vehículos
-- MARCA → MODELO → GENERACIÓN → VERSIÓN ⇄ MOTOR
-- Nada se borra físicamente si está referenciado (FK RESTRICT);
-- se usa status active/inactive. Inactivo = no se ofrece para nuevas
-- publicaciones, pero sigue resolviendo publicaciones históricas.
-- =====================================================================
SET search_path = app, public;

CREATE TABLE vehicle_brands (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  slug        text NOT NULL,
  logo_public_id text,
  status      catalog_status NOT NULL DEFAULT 'active',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vb_slug CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
);
COMMENT ON TABLE vehicle_brands IS '[PÚBLICO] Marcas.';
CREATE UNIQUE INDEX vehicle_brands_name_uq ON vehicle_brands (lower(name));
CREATE UNIQUE INDEX vehicle_brands_slug_uq ON vehicle_brands (slug);
CREATE TRIGGER vb_updated BEFORE UPDATE ON vehicle_brands FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE vehicle_models (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id      uuid NOT NULL REFERENCES vehicle_brands(id) ON DELETE RESTRICT,
  name          text NOT NULL,
  slug          text NOT NULL,
  vehicle_type  vehicle_type NOT NULL,
  default_body_type body_type,
  segment       text,
  status        catalog_status NOT NULL DEFAULT 'active',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vm_slug CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  CONSTRAINT vm_segment CHECK (segment IS NULL OR length(segment) <= 30)
);
COMMENT ON TABLE vehicle_models IS '[PÚBLICO] Modelos de una marca.';
COMMENT ON COLUMN vehicle_models.vehicle_type IS '[PÚBLICO] Auto, Camioneta, Utilitario, Camión, Moto, Cuatriciclo.';
COMMENT ON COLUMN vehicle_models.segment IS '[PÚBLICO] Segmento de mercado (A, B, C, D, E, F o descriptivo).';
CREATE UNIQUE INDEX vehicle_models_uq ON vehicle_models (brand_id, lower(name));
CREATE UNIQUE INDEX vehicle_models_slug_uq ON vehicle_models (brand_id, slug);
CREATE TRIGGER vm_updated BEFORE UPDATE ON vehicle_models FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE vehicle_generations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id    uuid NOT NULL REFERENCES vehicle_models(id) ON DELETE RESTRICT,
  name        text NOT NULL,
  year_from   smallint NOT NULL,
  year_to     smallint,
  status      catalog_status NOT NULL DEFAULT 'active',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vg_years CHECK (year_from BETWEEN 1900 AND 2100 AND (year_to IS NULL OR year_to >= year_from))
);
COMMENT ON TABLE vehicle_generations IS '[PÚBLICO] Generaciones (p.ej. Gol "G4", Corsa "Classic"). year_to NULL = vigente.';
CREATE UNIQUE INDEX vehicle_generations_uq ON vehicle_generations (model_id, lower(name));
CREATE TRIGGER vg_updated BEFORE UPDATE ON vehicle_generations FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE vehicle_engines (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text NOT NULL,
  fuel             fuel_type NOT NULL,
  displacement_cc  integer,
  power_hp         smallint,
  torque_nm        smallint,
  cylinders        smallint,
  aspiration       engine_aspiration,
  battery_kwh      numeric(5,1),
  status           catalog_status NOT NULL DEFAULT 'active',
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ve_cc CHECK (displacement_cc IS NULL OR displacement_cc BETWEEN 49 AND 20000),
  CONSTRAINT ve_hp CHECK (power_hp IS NULL OR power_hp BETWEEN 1 AND 2000),
  CONSTRAINT ve_nm CHECK (torque_nm IS NULL OR torque_nm BETWEEN 1 AND 5000),
  CONSTRAINT ve_cyl CHECK (cylinders IS NULL OR cylinders BETWEEN 1 AND 16),
  CONSTRAINT ve_electric CHECK ((fuel = 'electric') <= (displacement_cc IS NULL))
);
COMMENT ON TABLE vehicle_engines IS '[PÚBLICO] Motores reutilizables entre versiones (p.ej. "1.6 Nafta 8v"). Cilindrada, potencia y combustible viven acá.';
CREATE UNIQUE INDEX vehicle_engines_name_uq ON vehicle_engines (lower(name));
CREATE TRIGGER ve_updated BEFORE UPDATE ON vehicle_engines FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

CREATE TABLE vehicle_versions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_id   uuid NOT NULL REFERENCES vehicle_generations(id) ON DELETE RESTRICT,
  name            text NOT NULL,
  body_type       body_type,
  doors           smallint,
  seats           smallint,
  transmission    transmission_type,
  gears           smallint,
  traction        traction_type,
  origin_country  char(2),
  year_from       smallint,
  year_to         smallint,
  external_code   text,
  status          catalog_status NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vv_doors CHECK (doors IS NULL OR doors BETWEEN 0 AND 6),
  CONSTRAINT vv_seats CHECK (seats IS NULL OR seats BETWEEN 1 AND 60),
  CONSTRAINT vv_gears CHECK (gears IS NULL OR gears BETWEEN 1 AND 12),
  CONSTRAINT vv_years CHECK (year_from IS NULL OR year_to IS NULL OR year_to >= year_from)
);
COMMENT ON TABLE vehicle_versions IS '[PÚBLICO] Versión/terminación (p.ej. "Trendline 1.6", "LTZ 2.8 TD 4x4 AT"). Define carrocería, puertas, transmisión, tracción.';
COMMENT ON COLUMN vehicle_versions.origin_country IS '[PÚBLICO] Origen de fabricación (ISO-3166 alfa-2).';
COMMENT ON COLUMN vehicle_versions.external_code IS '[ADMIN] Código de catálogo externo (p.ej. guías de precios) para futura tasación. Sin integración.';
CREATE UNIQUE INDEX vehicle_versions_uq ON vehicle_versions (generation_id, lower(name));
CREATE TRIGGER vv_updated BEFORE UPDATE ON vehicle_versions FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

-- N:N versión ↔ motor (una versión puede ofrecerse con más de un motor;
-- un motor se usa en muchas versiones).
CREATE TABLE vehicle_version_engines (
  version_id  uuid NOT NULL REFERENCES vehicle_versions(id) ON DELETE RESTRICT,
  engine_id   uuid NOT NULL REFERENCES vehicle_engines(id) ON DELETE RESTRICT,
  is_default  boolean NOT NULL DEFAULT false,
  status      catalog_status NOT NULL DEFAULT 'active',
  PRIMARY KEY (version_id, engine_id)
);
COMMENT ON TABLE vehicle_version_engines IS '[PÚBLICO] Combinaciones válidas versión+motor. vehicles referencia esta combinación (FK compuesta).';
CREATE UNIQUE INDEX vve_default_uq ON vehicle_version_engines (version_id) WHERE is_default;
CREATE INDEX vve_engine_idx ON vehicle_version_engines (engine_id);

-- Pedidos de alta al catálogo (botón "No encuentro mi versión")
CREATE TABLE catalog_requests (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  requested_by  uuid NOT NULL REFERENCES users(id),
  vehicle_type  vehicle_type,
  brand_text    text NOT NULL,
  model_text    text,
  version_text  text,
  year          smallint,
  status        catalog_request_status NOT NULL DEFAULT 'pending',
  resolved_version_id uuid REFERENCES vehicle_versions(id),
  resolved_by   uuid REFERENCES users(id),
  resolved_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE catalog_requests IS '[PROPIETARIO] Texto libre SOLO como pedido al staff; nunca como identidad del vehículo.';
CREATE INDEX catalog_requests_pending_idx ON catalog_requests (created_at) WHERE status = 'pending';

-- Vista de ayuda: jerarquía completa y estado efectivo (inactivo si cualquier ancestro está inactivo)
CREATE VIEW v_catalog_versions AS
SELECT v.id AS version_id, g.id AS generation_id, m.id AS model_id, b.id AS brand_id,
       b.name AS brand, m.name AS model, g.name AS generation, v.name AS version,
       m.vehicle_type, coalesce(v.body_type, m.default_body_type) AS body_type,
       v.doors, v.seats, v.transmission, v.gears, v.traction, m.segment, v.origin_country,
       coalesce(v.year_from, g.year_from) AS year_from, coalesce(v.year_to, g.year_to) AS year_to,
       (b.status = 'active' AND m.status = 'active' AND g.status = 'active' AND v.status = 'active') AS is_active
FROM vehicle_versions v
JOIN vehicle_generations g ON g.id = v.generation_id
JOIN vehicle_models m ON m.id = g.model_id
JOIN vehicle_brands b ON b.id = m.brand_id;
