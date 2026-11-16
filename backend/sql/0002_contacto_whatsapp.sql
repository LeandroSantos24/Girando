-- =====================================================================
-- 0002 · Contacto por WhatsApp (CONTEXTO.md §2 y §5)
--   · WhatsApp obligatorio para enviar a revisión (vehículos y verticales).
--   · El número NUNCA sale por las vistas públicas: lo resuelve una función
--     que solo puede ejecutar el rol de sistema (redirect /api/out/wa).
--   · Aperturas de WhatsApp por publicación y por día (resumen, sin personas).
--   · Favoritos: precio al momento de guardar, para avisar la baja de precio.
--   · Muestra mínima para "precio vs mercado" y "demanda del mercado".
-- =====================================================================
SET search_path = app, public;

-- ---------------------------------------------------------------------
-- 1. WhatsApp de contacto en las verticales
-- ---------------------------------------------------------------------
ALTER TABLE posts ADD COLUMN IF NOT EXISTS contact_whatsapp_e164 text;
ALTER TABLE posts DROP CONSTRAINT IF EXISTS po_wa;
ALTER TABLE posts ADD CONSTRAINT po_wa CHECK (contact_whatsapp_e164 IS NULL OR contact_whatsapp_e164 ~ '^\+[1-9][0-9]{7,14}$');
COMMENT ON COLUMN posts.contact_whatsapp_e164 IS '[PRIVADO] WhatsApp de contacto de la publicación. No sale por api_public: solo lo usa el redirect /api/out/wa.';

-- Número efectivo: el de la publicación y, si es de un comercio, el WhatsApp comercial como respaldo.
CREATE OR REPLACE FUNCTION app.listing_whatsapp(p_listing uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT coalesce(c.whatsapp_e164, a.whatsapp_e164)
    FROM app.listings l
    LEFT JOIN app.listing_contacts c ON c.listing_id = l.id
    LEFT JOIN app.agencies a ON a.id = l.agency_id
   WHERE l.id = p_listing
$$;
CREATE OR REPLACE FUNCTION app.post_whatsapp(p_post uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT coalesce(p.contact_whatsapp_e164, a.whatsapp_e164)
    FROM app.posts p LEFT JOIN app.agencies a ON a.id = p.agency_id
   WHERE p.id = p_post
$$;
REVOKE ALL ON FUNCTION app.listing_whatsapp(uuid), app.post_whatsapp(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.listing_whatsapp(uuid), app.post_whatsapp(uuid) TO girando_worker;

-- Destino del redirect: solo publicaciones visibles (las mismas que muestran las vistas públicas).
CREATE OR REPLACE FUNCTION app.whatsapp_target(p_code text)
RETURNS TABLE (kind text, entity_id uuid, agency_id uuid, vertical text, title text, public_code text, whatsapp text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT 'listing', l.id, l.agency_id, 'vehicle',
         coalesce(nullif(trim(concat_ws(' ', l.brand, l.model, l.year::text)), ''), l.title)::text, l.public_code::text, app.listing_whatsapp(l.id)
    FROM api_public.listings l WHERE l.public_code = p_code
  UNION ALL
  SELECT 'post', p.id, p.agency_id, p.vertical::text, p.title::text, p.public_code::text, app.post_whatsapp(p.id)
    FROM api_public.posts p WHERE p.public_code = p_code
  LIMIT 1
$$;
REVOKE ALL ON FUNCTION app.whatsapp_target(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.whatsapp_target(text) TO girando_worker;
COMMENT ON FUNCTION app.whatsapp_target(text) IS 'Resuelve el WhatsApp de una publicación visible por su código. Solo rol de sistema: el número no se expone por ninguna vista.';

-- Obligatorio para enviar a revisión. Lo hace cumplir la base, no la pantalla.
CREATE OR REPLACE FUNCTION app.tg_listing_requires_whatsapp() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status = 'pending' AND OLD.status IS DISTINCT FROM 'pending' AND app.listing_whatsapp(NEW.id) IS NULL THEN
    RAISE EXCEPTION 'WHATSAPP_OBLIGATORIO' USING ERRCODE = 'GR422';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS b_listing_whatsapp ON listings;
CREATE TRIGGER b_listing_whatsapp BEFORE UPDATE OF status ON listings FOR EACH ROW EXECUTE FUNCTION tg_listing_requires_whatsapp();

CREATE OR REPLACE FUNCTION app.tg_post_requires_whatsapp() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  IF NEW.status = 'pending' AND OLD.status IS DISTINCT FROM 'pending' AND app.post_whatsapp(NEW.id) IS NULL THEN
    RAISE EXCEPTION 'WHATSAPP_OBLIGATORIO' USING ERRCODE = 'GR422';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS b_post_whatsapp ON posts;
CREATE TRIGGER b_post_whatsapp BEFORE UPDATE OF status ON posts FOR EACH ROW EXECUTE FUNCTION tg_post_requires_whatsapp();

-- ---------------------------------------------------------------------
-- 2. Aperturas de WhatsApp: resumen por publicación y día (nunca quién)
-- ---------------------------------------------------------------------
ALTER TABLE listing_stats_daily ADD COLUMN IF NOT EXISTS whatsapp_opens integer NOT NULL DEFAULT 0;
COMMENT ON COLUMN listing_stats_daily.whatsapp_opens IS '[PROPIETARIO] Veces que se abrió WhatsApp desde la ficha. No es una consulta confirmada: la charla pasa en WhatsApp.';

CREATE TABLE IF NOT EXISTS post_stats_daily (
  post_id        uuid NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  day            date NOT NULL,
  views          integer NOT NULL DEFAULT 0,
  whatsapp_opens integer NOT NULL DEFAULT 0,
  PRIMARY KEY (post_id, day)
);
COMMENT ON TABLE post_stats_daily IS '[PROPIETARIO] Vistas y aperturas de WhatsApp por publicación de las verticales y día. Dato DERIVADO de analytics_events (job idempotente).';
ALTER TABLE post_stats_daily ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS worker_all ON post_stats_daily;
CREATE POLICY worker_all ON post_stats_daily TO girando_worker USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS psd_select ON post_stats_daily;
CREATE POLICY psd_select ON post_stats_daily FOR SELECT TO girando_app USING (app.can_manage_post_id(post_id) OR app.app_is_staff());
GRANT SELECT ON post_stats_daily TO girando_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON post_stats_daily TO girando_worker;

-- ---------------------------------------------------------------------
-- 3. Favoritos: precio al guardar (para "bajó de precio")
-- ---------------------------------------------------------------------
ALTER TABLE favorites ADD COLUMN IF NOT EXISTS price_at_save numeric(14,2);
ALTER TABLE favorites ADD COLUMN IF NOT EXISTS currency_at_save currency_code;
COMMENT ON COLUMN favorites.price_at_save IS '[PROPIETARIO] Precio publicado cuando el usuario guardó el favorito. Sirve para avisar la baja de precio.';

CREATE OR REPLACE FUNCTION app.tg_favorite_price() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
BEGIN
  SELECT l.price_amount, l.currency INTO NEW.price_at_save, NEW.currency_at_save FROM app.listings l WHERE l.id = NEW.listing_id;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS a_favorite_price ON favorites;
CREATE TRIGGER a_favorite_price BEFORE INSERT ON favorites FOR EACH ROW EXECUTE FUNCTION tg_favorite_price();

-- El aviso de baja de precio a quienes guardaron la publicación ya lo emite la base (170 · zy_listing_favorites_notify).

-- ---------------------------------------------------------------------
-- 4. Precio vs mercado (regla 3: sin muestra suficiente no se muestra nada)
-- ---------------------------------------------------------------------
-- Compara contra publicaciones VISIBLES del mismo modelo y año ±1, normalizadas a pesos (BCRA), sin contar la propia.
CREATE OR REPLACE FUNCTION app.market_price(p_listing uuid)
RETURNS TABLE (sample integer, min_sample integer, sufficient boolean, avg_price_ars numeric, price_ars numeric, ratio_pct numeric, "position" text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  WITH me AS (SELECT id, model_id, year, coalesce(price_ars, CASE WHEN currency = 'ARS' THEN price_amount END) AS p
                FROM api_public.listings WHERE id = p_listing),
       cmp AS (SELECT count(*)::int AS n, avg(coalesce(l.price_ars, CASE WHEN l.currency = 'ARS' THEN l.price_amount END)) AS a
                 FROM api_public.listings l, me
                WHERE l.model_id = me.model_id AND l.year BETWEEN me.year - 1 AND me.year + 1 AND l.id <> me.id
                  AND coalesce(l.price_ars, CASE WHEN l.currency = 'ARS' THEN l.price_amount END) IS NOT NULL),
       m AS (SELECT app.setting_int('market.min_sample_size', 5) AS n_min)
  SELECT cmp.n, m.n_min, (cmp.n >= m.n_min AND me.p IS NOT NULL),
         CASE WHEN cmp.n >= m.n_min AND me.p IS NOT NULL THEN round(cmp.a) END,
         CASE WHEN cmp.n >= m.n_min AND me.p IS NOT NULL THEN round(me.p) END,
         CASE WHEN cmp.n >= m.n_min AND me.p IS NOT NULL THEN round(me.p * 100 / cmp.a, 1) END,
         CASE WHEN cmp.n < m.n_min OR me.p IS NULL THEN NULL
              WHEN me.p <= cmp.a * 0.95 THEN 'below' WHEN me.p >= cmp.a * 1.05 THEN 'above' ELSE 'in_market' END
    FROM me, cmp, m
$$;
REVOKE ALL ON FUNCTION app.market_price(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.market_price(uuid) TO girando_anon, girando_app, girando_worker;
COMMENT ON FUNCTION app.market_price(uuid) IS 'Precio vs mercado: por debajo ≤95 %, en mercado 95–105 %, por encima ≥105 % del promedio de igual modelo y año ±1. Sin muestra suficiente devuelve NULL (la pantalla dice "Sin datos suficientes").';
