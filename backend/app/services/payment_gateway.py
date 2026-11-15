"""Puerta única hacia el proveedor de pagos.

  · Con MERCADOPAGO_ACCESS_TOKEN (sandbox o real): Mercado Pago.
  · Sin token y con PAYMENTS_SIMULATOR=true (solo desarrollo y tests, prohibido en producción): simulador local.
    El simulador NO aprueba nada por sí mismo: solo permite disparar a mano el mismo evento que mandaría
    Mercado Pago, que entra por el mismo código que el webhook real (idempotencia incluida).
  · Sin ninguna de las dos: 503 PAGOS_NO_CONFIGURADOS. Nunca se simula una respuesta en silencio.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.config import get_settings
from app.core.errors import err
from app.integrations.external import MercadoPagoService

SIM_PREFIX = "SIM-"


def mode() -> str:
    s = get_settings()
    if s.mercadopago_access_token:
        return "mercadopago"
    if s.payments_simulator and s.env != "production":
        return "simulator"
    return "off"


def require_enabled() -> str:
    m = mode()
    if m == "off":
        raise err(503, "PAGOS_NO_CONFIGURADOS", "Los pagos con Mercado Pago todavía no están habilitados. Tu cuenta sigue con su plan actual.")
    return m


def is_simulated(external_id: str | None) -> bool:
    return bool(external_id) and str(external_id).startswith(SIM_PREFIX)


def create_preapproval(*, reason: str, amount: Decimal, currency: str, payer_email: str, external_reference: str, back_url: str) -> dict:
    """Suscripción recurrente. Devuelve {id, init_point, simulated}."""
    if require_enabled() == "simulator":
        return {"id": f"{SIM_PREFIX}{uuid.uuid4().hex[:16]}", "init_point": None, "simulated": True}
    pre = MercadoPagoService().create_preapproval(reason=reason, amount=amount, currency=currency, payer_email=payer_email,
                                                  external_reference=external_reference, back_url=back_url)
    return {"id": pre.get("id"), "init_point": pre.get("init_point"), "simulated": False}


def create_preference(*, title: str, amount: Decimal, currency: str, payer_email: str, external_reference: str, back_url: str) -> dict:
    """Pago único (mejora de plan, promoción). Devuelve {id, init_point, simulated}."""
    if require_enabled() == "simulator":
        return {"id": f"{SIM_PREFIX}{uuid.uuid4().hex[:16]}", "init_point": None, "simulated": True}
    pref = MercadoPagoService().create_preference(title=title, amount=amount, currency=currency, payer_email=payer_email,
                                                  external_reference=external_reference, back_url=back_url)
    return {"id": pref.get("id"), "init_point": pref.get("init_point") or pref.get("sandbox_init_point"), "simulated": False}
