"""Suscripciones de agencias con Mercado Pago (preapproval) + webhook.

Regla central: una suscripción NUNCA se activa porque el frontend lo diga.
    Mercado Pago → webhook (firma x-signature válida) → GET al recurso en MP (la verdad)
    → backend (rol worker) → PostgreSQL (subscriptions/payments) → plan efectivo → permisos.
El titular solo puede CREAR una suscripción 'pending' (la base fija precio y estado) y pedir la baja.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, current_user, request_ctx, require_roles
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.integrations import NotConfigured
from app.integrations.external import MercadoPagoService
from app.schemas.common import StrictModel
from app.services import payment_gateway
from app.services.account_service import plan_usage

log = logging.getLogger("girando.billing")
router = APIRouter(tags=["suscripciones y pagos"])
GRANTING = ("active", "payment_failed", "grace_period")


class SubscribeIn(StrictModel):
    plan_id: UUID


def _require_agency_admin(conn, agency_id: UUID) -> None:
    if not scalar(conn, "SELECT app.app_is_agency_member(:a, 'owner', 'admin')", {"a": agency_id}):
        raise err(403, "NO_AUTORIZADO", "Solo el titular o un administrador de la agencia gestiona la suscripción.")


SUB_SQL = """SELECT s.id, s.status::text AS status, s.provider::text AS provider, s.price_amount, s.currency::text AS currency,
                    s.billing_period::text AS billing_period, s.started_at, s.current_period_start, s.current_period_end, s.grace_until,
                    s.cancel_at_period_end, s.canceled_at, s.ended_at, s.created_at, p.id AS plan_id, p.name AS plan_name, p.max_active_listings,
                    pp.id AS pending_plan_id, pp.name AS pending_plan_name
               FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.plans pp ON pp.id = s.pending_plan_id"""


@router.get("/api/me/agencies/{agency_id}/billing")
def my_billing(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
            raise err(404, "NO_ENCONTRADA", "La agencia no existe o no sos miembro.")
        agency = row(conn, """SELECT a.id, a.trade_name, a.status::text AS status, a.kind::text AS kind,
                                     (SELECT v.status::text FROM app.verifications v WHERE v.subject_agency_id = a.id ORDER BY v.created_at DESC LIMIT 1) AS verification_status
                                FROM app.agencies a WHERE a.id = :a""", {"a": agency_id})
        sub = row(conn, SUB_SQL + " WHERE s.agency_id = :a ORDER BY s.created_at DESC LIMIT 1", {"a": agency_id})
        # Comprobantes: altas y renovaciones, mejoras de plan y promociones de la cuenta
        payments = rows(conn, """SELECT py.id, py.status::text AS status, py.provider::text AS provider, py.amount, py.currency::text AS currency,
                                        py.paid_at, py.created_at, py.purpose::text AS purpose, (py.plan_change_to IS NOT NULL) AS is_plan_change,
                                        coalesce(np.name, p.name, pp.name, 'Promoción') AS concept
                                   FROM app.payments py
                                   LEFT JOIN app.subscriptions s ON s.id = py.subscription_id LEFT JOIN app.plans p ON p.id = s.plan_id
                                   LEFT JOIN app.plans np ON np.id = py.plan_change_to
                                   LEFT JOIN app.promotions pr ON pr.id = py.promotion_id LEFT JOIN app.promotion_products pp ON pp.id = pr.product_id
                                  WHERE py.agency_id = :a OR s.agency_id = :a ORDER BY py.created_at DESC LIMIT 50""", {"a": agency_id})
        plans = rows(conn, """SELECT id, code, name, price_amount, currency::text AS currency, billing_period::text AS billing_period,
                                     max_active_listings, max_active_jobs, requires_verification, features_display
                                FROM api_public.plans WHERE audience = app.audience_for_kind(CAST(:k AS app.agency_kind)) AND price_amount > 0
                               ORDER BY sort_order, price_amount""", {"k": agency["kind"]})
        mode = payment_gateway.mode()
        return {"agency": agency, "usage": plan_usage(conn, user.id, agency_id), "subscription": sub, "payments": payments, "plans": plans,
                "payments_enabled": mode != "off", "payments_mode": mode}


@router.post("/api/me/agencies/{agency_id}/subscription", status_code=201)
def subscribe(agency_id: UUID, body: SubscribeIn, user: CurrentUser = Depends(current_user)):
    """Alta de suscripción de una cuenta comercial (agencia, concesionaria o casa de repuestos).
    Nace 'pending': no otorga nada hasta que el proveedor informa un pago aprobado."""
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    payment_gateway.require_enabled()  # antes de tocar la base: no dejamos suscripciones colgadas
    s = get_settings()
    with unit_of_work("app", user.id, user.ctx) as conn:
        _require_agency_admin(conn, agency_id)
        plan = row(conn, """SELECT p.id, p.name, p.price_amount FROM app.plans p JOIN app.agencies a ON a.id = :a
                             WHERE p.id = :p AND p.is_active AND p.is_public AND p.price_amount > 0
                               AND p.audience = app.audience_for_kind(a.kind)""", {"p": body.plan_id, "a": agency_id})
        if not plan:
            raise err(422, "PLAN_INVALIDO")
        cur = row(conn, "SELECT id, status::text AS status FROM app.subscriptions WHERE agency_id = :a ORDER BY created_at DESC LIMIT 1", {"a": agency_id})
    if cur and cur["status"] in GRANTING:
        raise err(409, "SUSCRIPCION_EXISTENTE", "La cuenta ya tiene una suscripción vigente. Para cambiar de plan usá “Subir de plan” o “Bajar de plan”.")
    if cur and cur["status"] == "pending":  # un intento anterior sin pagar se reemplaza
        with unit_of_work("worker", None, user.ctx, reason="Reemplazo de suscripción pendiente sin pago") as w:
            w.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s AND status = 'pending'"), {"s": cur["id"]})
    with unit_of_work("app", user.id, user.ctx, reason="Alta de suscripción") as conn:
        sub_id = scalar(conn, """INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, price_amount, currency, billing_period)
                                 VALUES (:p, :a, :u, 'mercadopago', 0, 'ARS', 'month') RETURNING id""",
                        {"p": plan["id"], "a": agency_id, "u": user.id})  # el trigger fija precio/moneda/período desde el plan
        sub = row(conn, "SELECT price_amount, currency::text AS currency FROM app.subscriptions WHERE id = :s", {"s": sub_id})
    try:
        pre = payment_gateway.create_preapproval(reason=f"Girando · {plan['name']}", amount=sub["price_amount"], currency=sub["currency"],
                                                 payer_email=user.email, external_reference=str(sub_id), back_url=f"{s.public_base_url}/#suscripcion")
    except (httpx.HTTPError, NotConfigured) as e:
        log.warning("mp_preapproval_failed", extra={"error": type(e).__name__})
        with unit_of_work("worker", None, user.ctx, reason="Preapproval rechazado por Mercado Pago") as w:
            w.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": sub_id})
        raise err(502, "PROVEEDOR_NO_DISPONIBLE", "Mercado Pago no respondió. Probá de nuevo en unos minutos.") from None
    with unit_of_work("worker", None, user.ctx, reason="Preapproval creado en el proveedor de pagos") as w:
        w.execute(text("UPDATE app.subscriptions SET external_subscription_id = :e WHERE id = :s"), {"e": pre["id"], "s": sub_id})
    return {"subscription_id": sub_id, "status": "pending", "init_point": pre["init_point"], "simulated": pre["simulated"],
            "plan": plan["name"], "amount": sub["price_amount"], "currency": sub["currency"]}


@router.post("/api/me/agencies/{agency_id}/subscription/cancel")
def cancel(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    """Cancelar: el plan sigue hasta el fin del período pago y después vence (lo que exceda se pausa, no se borra)."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        _require_agency_admin(conn, agency_id)
        sub = row(conn, """SELECT id, status::text AS status, external_subscription_id, provider::text AS provider, current_period_end
                             FROM app.subscriptions WHERE agency_id = :a ORDER BY created_at DESC LIMIT 1""", {"a": agency_id})
    if not sub or sub["status"] not in ("pending", *GRANTING):
        raise err(409, "SIN_SUSCRIPCION", "No hay una suscripción para cancelar.")
    if sub["status"] == "pending":
        with unit_of_work("worker", None, user.ctx, reason="Baja de suscripción sin pago") as w:
            w.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": sub["id"]})
        return {"ok": True, "status": "expired"}
    with unit_of_work("app", user.id, user.ctx, reason="Baja de suscripción pedida por el titular") as conn:
        conn.execute(text("UPDATE app.subscriptions SET cancel_at_period_end = true WHERE id = :s"), {"s": sub["id"]})
    if sub["provider"] != "mercadopago":       # plan asignado por Girando / transferencia: no se renueva solo, vence al terminar
        return {"ok": True, "status": "cancel_requested", "effective_at": sub["current_period_end"]}
    if payment_gateway.is_simulated(sub["external_subscription_id"]):
        if payment_gateway.mode() != "simulator":
            raise err(503, "PAGOS_NO_CONFIGURADOS", "Registramos tu pedido de baja, pero el proveedor de pagos no está configurado para confirmarla.")
        # Mismo camino que el aviso real: el proveedor informa el preapproval cancelado
        res = {"id": sub["external_subscription_id"], "status": "cancelled", "external_reference": str(sub["id"])}
        process_provider_event(user.ctx, topic="subscription_preapproval", data_id=res["id"], key=f"sim:cancel:{sub['id']}",
                               payload={"action": "simulated_cancel", "by": str(user.id)}, valid=True, fetch=lambda: res)
        return {"ok": True, "status": "canceled", "effective_at": sub["current_period_end"]}
    mp = MercadoPagoService()
    if not mp.token or not sub["external_subscription_id"]:
        raise err(503, "PAGOS_NO_CONFIGURADOS", "Registramos tu pedido de baja, pero Mercado Pago no está configurado para confirmarla.")
    try:   # La baja efectiva la confirma Mercado Pago por webhook (preapproval → cancelled)
        mp.cancel_preapproval(sub["external_subscription_id"])
    except httpx.HTTPError:
        raise err(502, "PROVEEDOR_NO_DISPONIBLE", "Mercado Pago no respondió. Probá de nuevo en unos minutos.") from None
    return {"ok": True, "status": "cancel_requested", "effective_at": sub["current_period_end"]}


# --------------------------------------------------------------------------- webhook
def now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _apply_preapproval(w, res: dict) -> UUID | None:
    sub = row(w, "SELECT id, status::text AS status, current_period_end FROM app.subscriptions WHERE id::text = :r OR external_subscription_id = :e",
              {"r": str(res.get("external_reference") or ""), "e": str(res.get("id") or "")})
    if not sub:
        return None
    st = res.get("status")
    if st == "authorized":
        # La fecha de cobro la decide Mercado Pago: si informa next_payment_date, esa es el fin del período.
        # Sin esa fecha se usa el mes calendario (ver app.next_period_end), nunca "30 días".
        mp_end = _parse_dt(res.get("next_payment_date"))
        w.execute(text("""UPDATE app.subscriptions SET status = 'active', started_at = coalesce(started_at, now()),
                             current_period_start = coalesce(current_period_start, now()),
                             billing_anchor_day = coalesce(billing_anchor_day, extract(day FROM coalesce(CAST(:end AS timestamptz), now()) AT TIME ZONE 'America/Argentina/Buenos_Aires')::int),
                             current_period_end = coalesce(CAST(:end AS timestamptz), current_period_end, app.next_period_end(now(), billing_period)),
                             next_renewal_at = coalesce(CAST(:end AS timestamptz), next_renewal_at), external_subscription_id = :e
                          WHERE id = :s"""), {"end": mp_end, "e": str(res.get("id")), "s": sub["id"]})
    elif st == "cancelled":
        if sub["current_period_end"]:
            w.execute(text("UPDATE app.subscriptions SET status = 'canceled', canceled_at = now() WHERE id = :s"), {"s": sub["id"]})
        else:
            w.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": sub["id"]})
    return sub["id"]


PAY_MAP = {"approved": "approved", "rejected": "rejected", "cancelled": "canceled", "refunded": "refunded", "charged_back": "charged_back",
           "in_process": "in_process", "pending": "pending", "processed": "approved", "recycling": "in_process", "scheduled": "pending"}


def _apply_authorized_payment(w, res: dict) -> tuple[UUID | None, UUID | None]:
    sub = row(w, "SELECT id, created_by, agency_id, status::text AS status FROM app.subscriptions WHERE external_subscription_id = :e",
              {"e": str(res.get("preapproval_id") or "")})
    if not sub:
        return None, None
    pay = res.get("payment") or {}
    st = PAY_MAP.get(str(pay.get("status") or res.get("status")), "pending")
    mp_id = str(pay.get("id") or res.get("id"))
    pid = scalar(w, "SELECT id FROM app.payments WHERE mp_payment_id = :m", {"m": mp_id})
    paid_at = _parse_dt(pay.get("date_approved") or res.get("debit_date")) or now_utc()
    if pid:
        w.execute(text("UPDATE app.payments SET status = CAST(:st AS app.payment_status), paid_at = CASE WHEN :st = 'approved' THEN coalesce(paid_at, :pa) END WHERE id = :p"),
                  {"st": st, "p": pid, "pa": paid_at})
    else:
        pid = scalar(w, """INSERT INTO app.payments (purpose, subscription_id, payer_user_id, agency_id, provider, status, amount, currency, mp_payment_id,
                                                  mp_preapproval_id, paid_at, provider_snapshot)
                           SELECT 'subscription', s.id, s.created_by, s.agency_id, 'mercadopago', CAST(:st AS app.payment_status), coalesce(:amt, s.price_amount), s.currency,
                                  :m, :pre, CASE WHEN :st = 'approved' THEN CAST(:pa AS timestamptz) END, CAST(:snap AS jsonb)
                             FROM app.subscriptions s WHERE s.id = :s RETURNING id""",
                     {"st": st, "amt": res.get("transaction_amount"), "m": mp_id, "pre": str(res.get("preapproval_id")), "s": sub["id"], "pa": paid_at,
                      "snap": json.dumps({k: res.get(k) for k in ("id", "status", "transaction_amount", "currency_id", "date_created", "debit_date")})})
    # El período lo extiende la base (trigger z_payments_effects → app.subscription_apply_payment) solo en la
    # TRANSICIÓN a approved: un webhook repetido no extiende dos veces.
    if st == "rejected" and sub["status"] == "active":
        w.execute(text("UPDATE app.subscriptions SET status = 'payment_failed' WHERE id = :s"), {"s": sub["id"]})
    return sub["id"], pid


def _apply_single_payment(w, res: dict) -> tuple[UUID | None, UUID | None]:
    """Pago único (mejora de plan o promoción): se concilia por external_reference con un pago 'pending' que
    creó la API. El efecto (cambiar el plan, activar la promoción) lo aplica la base en la TRANSICIÓN a approved."""
    pay = row(w, "SELECT id, subscription_id, status::text AS status, amount FROM app.payments WHERE external_reference = :r AND provider = 'mercadopago'",
              {"r": str(res.get("external_reference") or "")})
    if not pay:
        return None, None
    st = PAY_MAP.get(str(res.get("status")), "pending")
    if pay["status"] == "approved" and st in ("approved", "pending", "in_process", "rejected", "canceled"):
        return pay["subscription_id"], pay["id"]   # ya aplicado: un aviso tardío o repetido no lo deshace ni lo reaplica
    amount = res.get("transaction_amount")
    if st == "approved" and amount is not None and abs(float(amount) - float(pay["amount"])) > 0.009:
        st = "rejected"                             # el proveedor cobró otro importe: no se activa nada
        res = {**res, "status_detail": "importe_distinto"}
    w.execute(text("""UPDATE app.payments SET status = CAST(:st AS app.payment_status), mp_payment_id = coalesce(mp_payment_id, :m),
                             status_detail = :sd, paid_at = CASE WHEN :st = 'approved' THEN coalesce(paid_at, CAST(:pa AS timestamptz)) END,
                             provider_snapshot = CAST(:snap AS jsonb)
                       WHERE id = :p"""),
              {"st": st, "m": str(res.get("id") or "") or None, "sd": str(res.get("status_detail") or "")[:100] or None,
               "pa": _parse_dt(res.get("date_approved")) or now_utc(), "p": pay["id"],
               "snap": json.dumps({k: res.get(k) for k in ("id", "status", "status_detail", "transaction_amount", "external_reference", "date_approved")}, default=str)})
    return pay["subscription_id"], pay["id"]


TOPICS = ("subscription_preapproval", "subscription_authorized_payment", "payment")


def process_provider_event(ctx, *, topic: str, data_id: str, key: str, payload: dict, valid: bool, fetch, req_id: str | None = None):
    """Camino ÚNICO para los avisos del proveedor de pagos (webhook real y simulador local).
    1) Se registra el aviso con su clave de idempotencia: si ya estaba, no se hace nada (el webhook puede llegar dos veces).
    2) Sin firma válida no se procesa. 3) `fetch()` trae el recurso desde el proveedor (la verdad no es el payload).
    4) La base aplica los efectos en sus triggers, solo en la transición a `approved`."""
    try:
        with unit_of_work("worker", None, ctx, reason="Aviso del proveedor de pagos") as w:
            ev = scalar(w, """INSERT INTO app.payment_events (provider, topic, action, resource_id, request_id, idempotency_key, signature_valid, processing_status, payload, error)
                              VALUES ('mercadopago', :t, :a, :r, :rq, :k, :v, CAST(:ps AS app.provider_event_status), CAST(:p AS jsonb), :e) RETURNING id""",
                       {"t": topic or "unknown", "a": payload.get("action"), "r": data_id or "-", "rq": req_id, "k": key[:200], "v": valid,
                        "ps": "received" if valid else "ignored", "p": json.dumps(payload)[:20000], "e": None if valid else "firma inválida o ausente"})
    except IntegrityError:
        return {"ok": True, "duplicate": True}  # idempotencia: ya lo recibimos
    if not valid:
        return JSONResponse({"error": {"code": "FIRMA_INVALIDA", "message": "Firma inválida."}}, status_code=401)
    try:
        if topic not in TOPICS:
            with unit_of_work("worker", None, ctx) as w:
                w.execute(text("UPDATE app.payment_events SET processing_status = 'ignored', processed_at = now() WHERE id = :i"), {"i": ev})
            return {"ok": True, "ignored": True}
        res = fetch()
        with unit_of_work("worker", None, ctx, reason=f"Proveedor de pagos: {topic}") as w:
            if topic == "subscription_preapproval":
                sub_id, pay_id = _apply_preapproval(w, res), None
            elif topic == "subscription_authorized_payment":
                sub_id, pay_id = _apply_authorized_payment(w, res)
            else:
                sub_id, pay_id = _apply_single_payment(w, res)
            w.execute(text("""UPDATE app.payment_events SET processing_status = CAST(:ps AS app.provider_event_status), processed_at = now(),
                                  subscription_id = :s, payment_id = :p, resource_snapshot = CAST(:snap AS jsonb) WHERE id = :i"""),
                      {"ps": "processed" if (sub_id or pay_id) else "ignored", "s": sub_id, "p": pay_id, "i": ev,
                       "snap": json.dumps({k: res.get(k) for k in ("id", "status", "external_reference", "preapproval_id", "next_payment_date", "transaction_amount")}, default=str)})
        return {"ok": True}
    except Exception as e:  # el proveedor reintenta ante 5xx
        log.exception("provider_event_failed")
        with unit_of_work("worker", None, ctx) as w:
            w.execute(text("UPDATE app.payment_events SET processing_status = 'failed', error = :e WHERE id = :i"), {"e": type(e).__name__, "i": ev})
        return JSONResponse({"error": {"code": "ERROR_PROCESANDO", "message": "Reintentar."}}, status_code=500)


@router.post("/api/webhooks/mercadopago", include_in_schema=True)
async def mp_webhook(request: Request):
    ratelimit.hit(ratelimit.GLOBAL_IP, "mp-webhook")
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    topic = request.query_params.get("type") or request.query_params.get("topic") or payload.get("type") or ""
    data_id = request.query_params.get("data.id") or str((payload.get("data") or {}).get("id") or payload.get("id") or "")
    req_id = request.headers.get("x-request-id")
    mp = MercadoPagoService()
    valid = bool(data_id) and mp.verify_signature(request.headers.get("x-signature"), req_id, data_id)
    key = f"{topic}:{data_id}:{req_id or payload.get('action') or ''}"
    return process_provider_event(request_ctx(request), topic=topic, data_id=data_id, key=key, payload=payload, valid=valid, req_id=req_id,
                                  fetch=lambda: mp.get_resource(topic, data_id))


# --------------------------------------------------------------------------- admin (solo lectura: el estado lo cambia el proveedor)
FINANCE = require_roles("finance")  # finance + superadmin


@router.get("/api/admin/subscriptions")
def admin_subscriptions(user: CurrentUser = Depends(FINANCE)):
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        items = rows(conn, SUB_SQL.replace("FROM app.subscriptions s", ", a.trade_name AS agency FROM app.subscriptions s LEFT JOIN app.agencies a ON a.id = s.agency_id")
                     + " ORDER BY s.created_at DESC LIMIT 200")
        return {"items": items}


@router.get("/api/admin/payments")
def admin_payments(user: CurrentUser = Depends(FINANCE)):
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT py.id, py.status::text AS status, py.provider::text AS provider, py.amount, py.currency::text AS currency,
                                              py.paid_at, py.created_at, py.mp_payment_id, a.trade_name AS agency, coalesce(np.name, p.name) AS plan,
                                              py.purpose::text AS purpose, (py.plan_change_to IS NOT NULL) AS is_plan_change
                                         FROM app.payments py LEFT JOIN app.subscriptions s ON s.id = py.subscription_id
                                         LEFT JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.plans np ON np.id = py.plan_change_to
                                         LEFT JOIN app.agencies a ON a.id = py.agency_id
                                        ORDER BY py.created_at DESC LIMIT 200""")}
