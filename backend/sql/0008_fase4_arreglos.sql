-- =====================================================================
-- 0008 · Arreglos de la fase 4: recursión RLS en messages y verificación de repuestos
-- msg_select consultaba app.messages dentro de su propia política
-- ("infinite recursion detected in policy for relation messages").
-- La comprobación "esta conversación tiene un mensaje reportado" pasa a
-- una función SECURITY DEFINER (no reevalúa RLS) y la política la usa.
-- El alcance no cambia: participantes, o moderación SOLO si hay reporte.
-- =====================================================================
SET search_path = app, public;

CREATE OR REPLACE FUNCTION app.conversation_has_message_report(p_conv uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = app, public AS $$
  SELECT EXISTS (SELECT 1 FROM app.reports r JOIN app.messages m ON m.id = r.message_id WHERE m.conversation_id = p_conv)
$$;
COMMENT ON FUNCTION app.conversation_has_message_report(uuid) IS
  'RLS: true si la conversación tiene al menos un mensaje reportado. SECURITY DEFINER para no reevaluar la política de messages (evita recursión). Solo devuelve un booleano.';
REVOKE ALL ON FUNCTION app.conversation_has_message_report(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.conversation_has_message_report(uuid) TO girando_app, girando_worker;

DROP POLICY IF EXISTS msg_select ON messages;
CREATE POLICY msg_select ON messages FOR SELECT TO girando_app USING (
  is_conversation_participant(conversation_id)
  OR (is_mod() AND conversation_has_message_report(conversation_id)));

-- ---------------------------------------------------------------------
-- Verificación de casas de repuestos: el producto 'parts_store' es de tipo
-- 'onsite_visit' y tg_verifications_effects solo propagaba el resultado a la
-- cuenta comercial cuando el tipo era 'agency'. Resultado: la verificación
-- quedaba 'approved' pero la casa de repuestos seguía 'pending' y no podía
-- publicar. Toda verificación cuyo sujeto es una cuenta comercial y cuyo tipo
-- es 'agency' u 'onsite_visit' actualiza el estado de esa cuenta.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app.tg_verifications_effects() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = app, public AS $$
DECLARE k app.verification_kind;
BEGIN
  IF NEW.status IS NOT DISTINCT FROM OLD.status THEN RETURN NEW; END IF;
  SELECT kind INTO k FROM app.verification_products WHERE id = NEW.product_id;
  IF k = 'identity' AND NEW.subject_user_id IS NOT NULL THEN
    UPDATE app.users SET identity_verified_at = CASE WHEN NEW.status = 'approved' THEN now() ELSE NULL END
     WHERE id = NEW.subject_user_id AND NEW.status IN ('approved','revoked');
  ELSIF k IN ('agency','onsite_visit') AND NEW.subject_agency_id IS NOT NULL THEN
    UPDATE app.agencies SET
      status = CASE NEW.status WHEN 'review' THEN 'review' WHEN 'approved' THEN 'verified'
                               WHEN 'rejected' THEN 'rejected' WHEN 'revoked' THEN 'revoked' END::app.agency_status,
      verified_at = CASE WHEN NEW.status = 'approved' THEN now() WHEN NEW.status = 'revoked' THEN NULL ELSE verified_at END,
      status_reason = NEW.decision_reason
     WHERE id = NEW.subject_agency_id AND status NOT IN ('suspended');
  END IF;
  RETURN NEW;
END $$;
