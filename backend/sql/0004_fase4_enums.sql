-- =====================================================================
-- 0004 · Fase 4 — valores nuevos de ENUM.
-- Van en una migración propia: PostgreSQL no permite USAR un valor de enum en la
-- misma transacción en la que se agrega. 0005+ ya los pueden usar.
-- =====================================================================
SET search_path = app, public;

-- Carrocería (etiquetas en el frontend): hatchback, sedan, suv, crossover, pickup, wagon=Rural, coupe,
-- convertible=Cabriolet, roadster, mpv=Monovolumen, minivan, panel_van=Furgón, van, light_truck, off_road
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'crossover';
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'roadster';
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'mpv';
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'panel_van';
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'light_truck';
ALTER TYPE body_type ADD VALUE IF NOT EXISTS 'off_road';

-- Cuentas comerciales: la tabla agencies pasa a representar cualquier comercio del rubro
ALTER TYPE agency_kind ADD VALUE IF NOT EXISTS 'parts_store';        -- casa de repuestos
ALTER TYPE agency_kind ADD VALUE IF NOT EXISTS 'service_provider';   -- prestador de servicios
ALTER TYPE agency_kind ADD VALUE IF NOT EXISTS 'company';            -- empresa que publica empleos
ALTER TYPE plan_audience ADD VALUE IF NOT EXISTS 'parts_store';
ALTER TYPE plan_audience ADD VALUE IF NOT EXISTS 'service_provider';
ALTER TYPE plan_audience ADD VALUE IF NOT EXISTS 'company';

-- Publicidad: espacios por página
ALTER TYPE promotion_placement ADD VALUE IF NOT EXISTS 'search_inline';
ALTER TYPE promotion_placement ADD VALUE IF NOT EXISTS 'detail_sidebar';
ALTER TYPE promotion_placement ADD VALUE IF NOT EXISTS 'vertical_top';

-- Eventos medidos desde la App
ALTER TYPE analytics_event_name ADD VALUE IF NOT EXISTS 'post_view';
ALTER TYPE analytics_event_name ADD VALUE IF NOT EXISTS 'post_contact';
ALTER TYPE analytics_event_name ADD VALUE IF NOT EXISTS 'reco_impression';
ALTER TYPE analytics_event_name ADD VALUE IF NOT EXISTS 'reco_click';

-- Reportes y verificación sobre publicaciones de las verticales nuevas
ALTER TYPE report_target ADD VALUE IF NOT EXISTS 'post';
ALTER TYPE verification_subject ADD VALUE IF NOT EXISTS 'post';
ALTER TYPE verification_kind ADD VALUE IF NOT EXISTS 'onsite_visit';       -- visita presencial (repuestos)
ALTER TYPE verification_kind ADD VALUE IF NOT EXISTS 'taxi_permit';        -- permiso de taxi/remis comprobado
ALTER TYPE verification_kind ADD VALUE IF NOT EXISTS 'professional_license'; -- matrícula (p. ej. SSN)
