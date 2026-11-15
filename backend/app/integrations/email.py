"""EmailService: encola en email_events y envía solo si hay proveedor configurado.

Sin proveedor: la fila queda `pending` con last_error = 'provider_not_configured'.
En desarrollo, además, se loguea el enlace de acción (verificar email / recuperar
contraseña) para poder probar el flujo localmente. Eso NO marca el email como enviado.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.core.db import row

log = logging.getLogger("girando.email")


EmailKind = Literal["transactional", "official", "marketing"]


def sender_for(kind: EmailKind) -> str | None:
    """Remitente según el propósito. Marketing sin remitente configurado = no se envía."""
    s = get_settings()
    return {"transactional": s.email_from_transactional, "official": s.email_from_official, "marketing": s.email_from_marketing}[kind]


def has_marketing_consent(conn: Connection, user_id) -> bool:
    """Último consentimiento de marketing del usuario: solo 'granted' habilita envíos comerciales."""
    if not user_id:
        return False
    st = row(conn, """SELECT state::text AS state FROM app.consents WHERE user_id = :u AND consent_type = 'marketing_communications'
                       ORDER BY created_at DESC LIMIT 1""", {"u": user_id})
    return bool(st and st["state"] == "granted")


def queue_email(conn: Connection, template_code: str, to_email: str, to_user_id, event_code: str,
                variables: dict[str, Any], dev_link: str | None = None, kind: EmailKind = "transactional") -> None:
    """Debe ejecutarse con rol worker (email_events no es escribible por usuarios).
    kind decide el remitente: avisos transaccionales (contacto.avisos@), oficiales (contacto.oficial@) o marketing,
    que además exige consentimiento explícito vigente."""
    s = get_settings()
    if kind == "marketing" and not (sender_for("marketing") and has_marketing_consent(conn, to_user_id)):
        log.info("marketing_email_skipped", extra={"template": template_code, "reason": "sin consentimiento o sin remitente"})
        return
    variables = {**variables, "_sender": sender_for(kind), "_reply_to": s.email_contact_address}
    tpl = row(conn, "SELECT id FROM app.email_templates WHERE code = :c AND status = 'active' ORDER BY version DESC LIMIT 1", {"c": template_code})
    if not tpl:
        log.warning("email_template_missing", extra={"template": template_code})
        return
    provider_ready = s.email_provider != "none" and bool(s.email_api_key)
    conn.execute(
        text(
            "INSERT INTO app.email_events (template_id, to_user_id, to_email, event_code, variables, status, last_error)"
            " VALUES (:t, :u, :e, :ev, CAST(:v AS jsonb), 'pending', :le)"),
        {"t": tpl["id"], "u": to_user_id, "e": to_email, "ev": event_code, "v": json.dumps(variables),
         "le": None if provider_ready else "provider_not_configured"},
    )
    if s.is_dev and dev_link:
        log.info("dev_email_link", extra={"template": template_code, "to_domain": to_email.split("@")[-1], "link": dev_link})
