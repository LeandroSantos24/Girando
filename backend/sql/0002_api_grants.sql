-- 0002 · Ajustes para la API
-- El rol anónimo necesita USAGE del esquema app solo para tipos (casts de enums) y la
-- función inmutable de normalización. NO recibe permisos sobre ninguna tabla de app.
GRANT USAGE ON SCHEMA app TO girando_anon;
GRANT EXECUTE ON FUNCTION app.f_unaccent(text) TO girando_anon;

-- Conteo de favoritos para el dueño de la publicación (sin exponer QUIÉN la guardó)
CREATE OR REPLACE FUNCTION app.listing_favorites_count(p_listing uuid) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT CASE WHEN app.can_manage_listing_id(p_listing) OR app.app_is_staff()
              THEN (SELECT count(*) FROM app.favorites WHERE listing_id = p_listing) END
$$;
REVOKE EXECUTE ON FUNCTION app.listing_favorites_count(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.listing_favorites_count(uuid) TO girando_app, girando_worker;

-- ¿El slug de agencia ya existe? (el usuario no puede ver agencias ajenas por RLS)
CREATE OR REPLACE FUNCTION app.agency_slug_taken(p_slug text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.agencies WHERE slug = p_slug)
$$;
REVOKE EXECUTE ON FUNCTION app.agency_slug_taken(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.agency_slug_taken(text) TO girando_app, girando_worker;
