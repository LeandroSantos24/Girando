-- =====================================================================
-- 0009 · Taxis sin límite de antigüedad (decisión del dueño, CONTEXTO.md §2)
-- No había validación por ley; quedaba el piso de año 1980 (más alto que el
-- de vehículos, 1900) y la nota de antigüedad. El año pasa a ser solo un
-- control de plausibilidad, igual que en vehicles, y la nota se elimina.
-- =====================================================================
SET search_path = app, public;

ALTER TABLE taxi_posts DROP CONSTRAINT IF EXISTS tx_year;
ALTER TABLE taxi_posts ADD CONSTRAINT tx_year CHECK (vehicle_year IS NULL OR vehicle_year BETWEEN 1900 AND 2100);

DELETE FROM app_settings WHERE key = 'taxi.vehicle_age_note';
UPDATE app_settings SET value = to_jsonb('La transferencia del permiso requiere autorización de la autoridad de transporte.'::text),
                        description = 'Aviso corto de la sección Taxis (único texto legal de la sección)'
 WHERE key = 'taxi.legal_notice';
