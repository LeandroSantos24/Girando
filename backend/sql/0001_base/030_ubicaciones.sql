-- =====================================================================
-- 030 · Ubicaciones
--   geo_areas : jerarquía de referencia (país → provincia → departamento
--               → localidad). Fuente sugerida: API Georef AR (datos
--               oficiales). PÚBLICA. Pendiente de carga (seed real).
--   locations : direcciones concretas (calle, número, lat/lng exactas).
--               PRIVADAS salvo que el dueño sea una agencia (domicilio
--               comercial, se expone vía vista pública de agencias).
-- La publicación muestra geo_area ("Godoy Cruz, Mendoza") y nunca locations.
-- =====================================================================
SET search_path = app, public;

CREATE TABLE geo_areas (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id     uuid REFERENCES geo_areas(id),
  level         geo_level NOT NULL,
  name          text NOT NULL,
  official_code text,
  country_code  char(2) NOT NULL DEFAULT 'AR',
  centroid_lat  numeric(9,6),
  centroid_lng  numeric(9,6),
  is_active     boolean NOT NULL DEFAULT true,
  name_search   text GENERATED ALWAYS AS (lower(app.f_unaccent(name))) STORED,
  CONSTRAINT geo_parent_rule CHECK ((level = 'country') = (parent_id IS NULL)),
  CONSTRAINT geo_lat CHECK (centroid_lat IS NULL OR centroid_lat BETWEEN -90 AND 90),
  CONSTRAINT geo_lng CHECK (centroid_lng IS NULL OR centroid_lng BETWEEN -180 AND 180)
);
COMMENT ON TABLE geo_areas IS '[PÚBLICO] Divisiones geográficas de referencia. Un solo árbol autorreferenciado en vez de 4 tablas.';
COMMENT ON COLUMN geo_areas.official_code IS '[PÚBLICO] Código oficial (INDEC/Georef) para sincronizar sin duplicar.';
COMMENT ON COLUMN geo_areas.centroid_lat IS '[PÚBLICO] Centroide del área: es la única coordenada que se muestra en mapas públicos.';
CREATE UNIQUE INDEX geo_areas_code_uq ON geo_areas (country_code, level, official_code) WHERE official_code IS NOT NULL;
CREATE INDEX geo_areas_parent_idx ON geo_areas (parent_id);
CREATE INDEX geo_areas_name_trgm ON geo_areas USING gin (name_search gin_trgm_ops);

CREATE TABLE locations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  country_code    char(2) NOT NULL DEFAULT 'AR',
  province_id     uuid NOT NULL REFERENCES geo_areas(id),
  department_id   uuid REFERENCES geo_areas(id),
  locality_id     uuid REFERENCES geo_areas(id),
  postal_code     text,
  neighborhood    text,
  street          text,
  street_number   text,
  unit            text,
  lat             numeric(9,6),
  lng             numeric(9,6),
  created_by      uuid REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT loc_cp CHECK (postal_code IS NULL OR postal_code ~ '^([0-9]{4}|[A-Z][0-9]{4}[A-Z]{3})$'),
  CONSTRAINT loc_lat CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  CONSTRAINT loc_lng CHECK (lng IS NULL OR lng BETWEEN -180 AND 180),
  CONSTRAINT loc_latlng_pair CHECK ((lat IS NULL) = (lng IS NULL))
);
COMMENT ON TABLE locations IS 'Dirección exacta. [PRIVADO] por defecto. Nunca se expone para usuarios particulares.';
COMMENT ON COLUMN locations.postal_code IS '[PRIVADO] CP de 4 dígitos o CPA (M5500ABC).';
COMMENT ON COLUMN locations.neighborhood IS '[PRIVADO para particulares] Barrio/zona. El vendedor puede optar por mostrarlo (listings.show_neighborhood).';
COMMENT ON COLUMN locations.street IS '[PRIVADO] Calle.';
COMMENT ON COLUMN locations.street_number IS '[PRIVADO] Altura.';
COMMENT ON COLUMN locations.lat IS '[PRIVADO] Coordenada exacta. Público solo el centroide de geo_areas.';
CREATE INDEX locations_locality_idx ON locations (locality_id);
CREATE TRIGGER locations_updated BEFORE UPDATE ON locations FOR EACH ROW EXECUTE FUNCTION tg_set_updated_at();

ALTER TABLE user_personal_data ADD CONSTRAINT upd_home_location_fk FOREIGN KEY (home_location_id) REFERENCES locations(id);
ALTER TABLE user_profiles      ADD CONSTRAINT up_geo_area_fk     FOREIGN KEY (geo_area_id)      REFERENCES geo_areas(id);
