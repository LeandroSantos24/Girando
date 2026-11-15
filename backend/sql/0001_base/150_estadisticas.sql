-- =====================================================================
-- 150 · Estadísticas (vistas derivadas; nada se inventa ni se guarda a mano)
-- Regla Girando: no mostrar promedios con muestras insuficientes
-- (stats.min_sample_size, hoy 3). Con n < mínimo se devuelve el conteo
-- y los promedios en NULL + sample_sufficient = false.
-- =====================================================================
SET search_path = app, public;

-- Base de ventas válidas con importes normalizados a ARS y catálogo resuelto
CREATE VIEW v_sales_base AS
SELECT s.id, s.listing_id, s.seller_user_id, s.agency_id, s.sold_on, date_trunc('month', s.sold_on)::date AS month,
       s.final_price, s.currency, s.final_price * coalesce(s.fx_rate_to_ars, 1) AS final_price_ars,
       l.price_amount AS listed_price, l.currency AS listed_currency,
       l.price_amount * CASE WHEN l.currency = s.currency THEN coalesce(s.fx_rate_to_ars, 1) ELSE NULL END AS listed_price_ars,
       (s.sold_on - l.first_published_at::date) AS days_to_sell,
       s.is_financed, s.financing_type, s.channel, s.attributed_to_girando,
       cv.brand_id, cv.brand, cv.model_id, cv.model, cv.version_id, cv.version, v.year, l.km, l.geo_area_id
FROM sales s
JOIN listings l ON l.id = s.listing_id
JOIN vehicles v ON v.id = s.vehicle_id
JOIN v_catalog_versions cv ON cv.version_id = v.version_id
WHERE s.status = 'reported';

-- Ventas por modelo (panel admin y estadísticas públicas agregadas)
CREATE VIEW v_sales_by_model AS
WITH m AS (SELECT setting_int('stats.min_sample_size', 3) AS n_min)
SELECT b.brand, b.model, b.model_id, count(*) AS sales,
       count(*) >= m.n_min AS sample_sufficient,
       CASE WHEN count(*) >= m.n_min THEN round(avg(b.final_price_ars)) END AS avg_final_price_ars,
       CASE WHEN count(*) >= m.n_min THEN round(avg(b.listed_price_ars)) END AS avg_listed_price_ars,
       CASE WHEN count(*) >= m.n_min THEN round(avg(b.days_to_sell)) END AS avg_days_to_sell,
       count(*) FILTER (WHERE b.is_financed) AS financed_sales,
       count(*) FILTER (WHERE b.attributed_to_girando) AS attributed_sales
FROM v_sales_base b CROSS JOIN m
GROUP BY b.brand, b.model, b.model_id, m.n_min;

CREATE VIEW v_sales_by_brand_month AS
WITH m AS (SELECT setting_int('stats.min_sample_size', 3) AS n_min)
SELECT b.month, b.brand, b.brand_id, count(*) AS sales, sum(b.final_price_ars) AS total_ars,
       CASE WHEN count(*) >= m.n_min THEN round(avg(b.final_price_ars)) END AS avg_final_price_ars
FROM v_sales_base b CROSS JOIN m
GROUP BY b.month, b.brand, b.brand_id, m.n_min;

CREATE VIEW v_sales_by_year AS
WITH m AS (SELECT setting_int('stats.min_sample_size', 3) AS n_min)
SELECT b.year, count(*) AS sales,
       CASE WHEN count(*) >= m.n_min THEN round(avg(b.final_price_ars)) END AS avg_final_price_ars
FROM v_sales_base b CROSS JOIN m GROUP BY b.year, m.n_min;

-- KPIs por vendedor (usuario o agencia) — RLS de las tablas base se aplica
-- porque la vista se define con security_invoker.
CREATE VIEW v_seller_kpis WITH (security_invoker = true) AS
SELECT coalesce(l.agency_id, l.owner_user_id) AS seller_key, (l.agency_id IS NOT NULL) AS is_agency,
       count(*) FILTER (WHERE l.status = 'published') AS active_listings,
       count(*) FILTER (WHERE l.first_published_at IS NOT NULL) AS ever_published,
       count(*) FILTER (WHERE l.status = 'sold') AS sold_listings,
       count(*) FILTER (WHERE l.status = 'expired') AS expired_listings,
       coalesce(sum(st.views), 0) AS views, coalesce(sum(st.favorites), 0) AS favorites,
       coalesce(sum(st.contacts), 0) AS contacts, coalesce(sum(st.shares), 0) AS shares
FROM listings l
LEFT JOIN (SELECT listing_id, sum(views) views, sum(favorites) favorites, sum(contacts) contacts, sum(shares) shares
             FROM listing_stats_daily GROUP BY listing_id) st ON st.listing_id = l.id
GROUP BY coalesce(l.agency_id, l.owner_user_id), (l.agency_id IS NOT NULL);

-- Métricas de una promoción (desde analytics_events; nunca cargadas a mano)
CREATE VIEW v_promotion_metrics WITH (security_invoker = true) AS
SELECT p.id AS promotion_id,
       count(*) FILTER (WHERE e.event_name = 'promotion_impression') AS impressions,
       count(*) FILTER (WHERE e.event_name = 'promotion_view') AS views,
       count(*) FILTER (WHERE e.event_name = 'promotion_click') AS clicks,
       count(*) FILTER (WHERE e.event_name = 'listing_favorite') AS favorites,
       count(*) FILTER (WHERE e.event_name = 'listing_contact') AS contacts
FROM promotions p
LEFT JOIN analytics_events e ON e.promotion_id = p.id AND e.occurred_at BETWEEN p.starts_at AND p.ends_at
GROUP BY p.id;

GRANT SELECT ON v_sales_by_model, v_sales_by_brand_month, v_sales_by_year TO girando_app, girando_worker;
GRANT SELECT ON v_seller_kpis, v_promotion_metrics, v_catalog_versions TO girando_app, girando_worker;
-- v_sales_base expone ventas individuales: solo staff vía backend (worker) — no se otorga a girando_app.
GRANT SELECT ON v_sales_base TO girando_worker;
