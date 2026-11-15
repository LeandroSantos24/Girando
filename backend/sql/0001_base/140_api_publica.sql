-- =====================================================================
-- 140 · API pública (vistas de solo lectura)
-- Única superficie accesible para visitantes (girando_anon). Columnas
-- elegidas explícitamente: jamás SELECT *. Si una columna no está acá,
-- no es pública. Ninguna vista incluye: email de login, teléfonos no
-- habilitados, DNI, dirección exacta, patente/VIN/chasis/motor,
-- documentos, pagos, suscripciones ni datos de moderación.
-- =====================================================================
SET search_path = app, public;

-- Publicaciones visibles: published + no vencida + dueño activo + agencia no suspendida/revocada
CREATE VIEW api_public.listings WITH (security_barrier) AS
SELECT
  l.id, l.public_code, l.title, l.description,
  l.price_amount, l.currency, l.condition, l.km,
  l.is_financeable, l.accepts_trade_in, l.video_url,
  l.published_at, l.first_published_at,
  cv.brand_id, cv.brand, cv.model_id, cv.model, cv.generation_id, cv.generation, cv.version_id, cv.version,
  cv.vehicle_type, cv.body_type, cv.doors, cv.seats, cv.transmission, cv.gears, cv.traction, cv.segment,
  e.name AS engine, e.displacement_cc, e.power_hp, coalesce(v.fuel_override, e.fuel) AS fuel,
  v.year, v.color,
  ga.id AS geo_area_id, ga.name AS locality, gp.name AS province, ga.centroid_lat, ga.centroid_lng,
  CASE WHEN l.show_neighborhood THEN loc.neighborhood END AS neighborhood,
  CASE WHEN l.agency_id IS NULL THEN 'particular' ELSE a.kind::text END AS seller_type,
  l.agency_id, a.trade_name AS agency_name, a.slug AS agency_slug, (a.status = 'verified') AS agency_verified,
  CASE WHEN l.agency_id IS NULL AND up.is_public THEN up.display_name END AS seller_display_name,
  CASE WHEN l.agency_id IS NULL THEN (u.identity_verified_at IS NOT NULL) END AS seller_identity_verified,
  (SELECT jsonb_agg(jsonb_build_object('public_id', i.public_id, 'url', i.secure_url, 'provider', i.storage_provider, 'kind', i.kind, 'position', i.position,
                                       'is_cover', i.is_cover, 'width', i.width, 'height', i.height) ORDER BY i.position)
     FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active') AS images,
  (SELECT i.public_id FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_public_id,
  (SELECT i.secure_url FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_url,
  l.search_vector
FROM app.listings l
JOIN app.vehicles v ON v.id = l.vehicle_id
JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
JOIN app.vehicle_engines e ON e.id = v.engine_id
JOIN app.geo_areas ga ON ga.id = l.geo_area_id
LEFT JOIN app.geo_areas gd ON gd.id = ga.parent_id
LEFT JOIN app.geo_areas gp ON gp.id = CASE WHEN ga.level = 'department' THEN ga.parent_id WHEN ga.level = 'locality' THEN gd.parent_id END
LEFT JOIN app.locations loc ON loc.id = l.location_id
JOIN app.users u ON u.id = l.owner_user_id AND u.status = 'active'
LEFT JOIN app.user_profiles up ON up.user_id = l.owner_user_id
LEFT JOIN app.agencies a ON a.id = l.agency_id
WHERE l.status = 'published'
  AND l.expires_at > now()
  AND (l.agency_id IS NULL OR a.status NOT IN ('suspended','revoked'));
COMMENT ON VIEW api_public.listings IS 'Publicaciones visibles para cualquiera. El contacto NO está acá: se pide autenticado a api_public.listing_contact.';

-- Contacto habilitado por el vendedor. La API solo lo sirve a usuarios autenticados y registra listing_contact_reveal.
CREATE VIEW api_public.listing_contact WITH (security_barrier) AS
SELECT c.listing_id,
       CASE WHEN c.show_phone THEN c.phone_e164 END AS phone,
       CASE WHEN c.show_whatsapp THEN c.whatsapp_e164 END AS whatsapp,
       CASE WHEN c.show_email THEN c.email::text END AS email,
       c.instagram_url, c.tiktok_url, c.facebook_url, c.website_url
FROM app.listing_contacts c
JOIN api_public.listings pl ON pl.id = c.listing_id;

-- Agencias visibles
CREATE VIEW api_public.agencies WITH (security_barrier) AS
SELECT a.id, a.slug, a.kind, a.trade_name, a.description, a.logo_public_id, a.cover_public_id,
       a.phone_e164, a.whatsapp_e164, a.email::text AS email, a.website_url, a.instagram_url, a.facebook_url,
       a.tiktok_url, a.youtube_url, a.x_url, a.business_hours,
       loc.street, loc.street_number, ga.name AS locality, ga.id AS geo_area_id,
       (a.status = 'verified') AS is_verified, a.verified_at, date_part('year', a.created_at)::int AS member_since,
       r.girando_rating, r.girando_review_count,
       er.rating AS google_rating, er.review_count AS google_review_count, er.source_url AS google_url, er.synced_at AS google_synced_at
FROM app.agencies a
JOIN app.geo_areas ga ON ga.id = a.geo_area_id
LEFT JOIN app.locations loc ON loc.id = a.location_id
LEFT JOIN LATERAL (SELECT round(avg(rating)::numeric, 1) AS girando_rating, count(*) AS girando_review_count
                     FROM app.reviews WHERE reviewed_agency_id = a.id AND status = 'published') r ON true
LEFT JOIN app.external_ratings er ON er.agency_id = a.id AND er.provider = 'google' AND er.synced_at IS NOT NULL
WHERE a.status IN ('pending','review','verified','rejected');
COMMENT ON VIEW api_public.agencies IS 'Perfil público de agencias (no suspendidas/revocadas). Reputación Girando y Google en columnas separadas; nunca se combinan.';

-- Perfil público de particulares
CREATE VIEW api_public.user_profiles WITH (security_barrier) AS
SELECT up.user_id, up.display_name, up.avatar_public_id, up.bio, ga.name AS locality,
       up.instagram_url, up.tiktok_url, up.facebook_url, up.x_url, up.youtube_url, up.website_url,
       (u.identity_verified_at IS NOT NULL) AS identity_verified,
       date_part('year', u.created_at)::int AS member_since,
       r.girando_rating, r.girando_review_count
FROM app.user_profiles up
JOIN app.users u ON u.id = up.user_id AND u.status = 'active'
LEFT JOIN app.geo_areas ga ON ga.id = up.geo_area_id
LEFT JOIN LATERAL (SELECT round(avg(rating)::numeric, 1) AS girando_rating, count(*) AS girando_review_count
                     FROM app.reviews WHERE reviewed_user_id = up.user_id AND status = 'published') r ON true
WHERE up.is_public;

CREATE VIEW api_public.reviews WITH (security_barrier) AS
SELECT r.id, r.reviewed_user_id, r.reviewed_agency_id, r.rating, r.comment, r.created_at,
       coalesce(CASE WHEN up.is_public THEN up.display_name END, 'Usuario de Girando') AS reviewer_display_name,
       CASE WHEN r.sale_id IS NOT NULL THEN 'sale' ELSE 'inquiry' END AS interaction
FROM app.reviews r
LEFT JOIN app.user_profiles up ON up.user_id = r.reviewer_user_id
WHERE r.status = 'published';

-- Catálogo activo
CREATE VIEW api_public.catalog_versions AS
SELECT cv.*, (SELECT jsonb_agg(jsonb_build_object('engine_id', e.id, 'name', e.name, 'fuel', e.fuel, 'displacement_cc', e.displacement_cc,
                                                  'power_hp', e.power_hp, 'is_default', ve.is_default))
                FROM app.vehicle_version_engines ve JOIN app.vehicle_engines e ON e.id = ve.engine_id
               WHERE ve.version_id = cv.version_id AND ve.status = 'active' AND e.status = 'active') AS engines
FROM app.v_catalog_versions cv WHERE cv.is_active;

CREATE VIEW api_public.geo_areas AS
SELECT id, parent_id, level, name, official_code, centroid_lat, centroid_lng FROM app.geo_areas WHERE is_active;

-- Promociones activas, siempre con su rótulo
CREATE VIEW api_public.sponsored WITH (security_barrier) AS
SELECT p.id AS promotion_id, p.type, p.placement, p.priority, p.disclosure_label,
       p.listing_id, p.target_agency_id, p.advertiser_name, p.creative_public_id, p.link_url,
       p.target_brand_id, p.target_model_id, p.target_geo_area_id, p.ends_at
FROM app.promotions p
WHERE p.status = 'active' AND now() BETWEEN p.starts_at AND p.ends_at
  AND (p.listing_id IS NULL OR EXISTS (SELECT 1 FROM api_public.listings pl WHERE pl.id = p.listing_id));

CREATE VIEW api_public.plans AS
SELECT id, code, name, description, audience, price_amount, currency, billing_period, max_active_listings,
       included_featured_listings, stats_level, includes_verification, max_members, features_display, badge_label, sort_order
FROM app.plans WHERE is_active AND is_public;

CREATE VIEW api_public.settings AS SELECT key, value FROM app.app_settings WHERE is_public;
CREATE VIEW api_public.report_reasons AS SELECT id, code, label, applies_to, requires_description, sort_order FROM app.report_reasons WHERE is_active;
CREATE VIEW api_public.verification_products AS
SELECT id, code, name, description, kind, subject, price_amount, currency, public_disclaimer, includes_physical_inspection
FROM app.verification_products WHERE status = 'active';

GRANT SELECT ON ALL TABLES IN SCHEMA api_public TO girando_anon, girando_app, girando_worker;

-- ---------------------------------------------------------------------
-- Ajustes para la API (permisos mínimos del rol anónimo y funciones auxiliares)
-- ---------------------------------------------------------------------
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
