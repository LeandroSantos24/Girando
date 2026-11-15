"""Fase 4 · Rutas de cobro: mejora y baja de plan, compra de promociones (destacar una publicación),
reporte para el anunciante y simulador local del proveedor.

Regla de siempre: nada se activa porque el navegador lo pida. Un plan o una promoción cambian solo cuando
la base registra un pago aprobado (triggers de `payments`) o cuando el Super Admin otorga una cortesía auditada.

Cambio de plan (documentado en docs/18):
  · SUBIR: se paga la mejora; al aprobarse rige el plan nuevo y el período se reinicia. Sin prorrateo en esta fase.
  · BAJAR: no se cobra; queda pendiente y rige en la próxima renovación. Lo que excede se pausa, nunca se borra.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import Field, StringConstraints
from sqlalchemy import text

from app.api.deps import CurrentUser, current_user, request_ctx, require_roles
from app.api.routers.billing import GRANTING, _require_agency_admin, process_provider_event
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.integrations import NotConfigured
from app.integrations.external import MercadoPagoService
from app.schemas.common import StrictModel
from app.services import payment_gateway

log = logging.getLogger("girando.payments")
router = APIRouter(prefix="/api", tags=["cobros · fase 4"])
SUPER = require_roles("superadmin")


class PlanIn(StrictModel):
    plan_id: UUID


def _current_sub(conn, agency_id: UUID) -> dict:
    sub = row(conn, """SELECT s.id, s.status::text AS status, s.provider::text AS provider, s.external_subscription_id, s.plan_id,
                              p.max_active_listings, p.price_amount, p.name AS plan_name
                         FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id
                        WHERE s.agency_id = :a ORDER BY s.created_at DESC LIMIT 1""", {"a": agency_id})
    if not sub or sub["status"] not in GRANTING:
        raise err(409, "SIN_SUSCRIPCION_VIGENTE")
    return sub


def _fail_payment(ctx, payment_id) -> None:
    with unit_of_work("worker", None, ctx, reason="El proveedor no devolvió el checkout") as w:
        w.execute(text("UPDATE app.payments SET status = 'canceled', status_detail = 'checkout_no_creado' WHERE id = :p AND status = 'pending'"), {"p": payment_id})


def _checkout(user: CurrentUser, payment_id, title: str, back: str) -> dict:
    """Crea el checkout del proveedor para un pago 'pending' que ya está en la base (el monto lo fijó la base)."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        pay = row(conn, "SELECT amount, currency::text AS currency, external_reference FROM app.payments WHERE id = :p", {"p": payment_id})
    try:
        pref = payment_gateway.create_preference(title=title, amount=pay["amount"], currency=pay["currency"], payer_email=user.email,
                                                 external_reference=pay["external_reference"], back_url=f"{get_settings().public_base_url}/#{back}")
    except (httpx.HTTPError, NotConfigured) as e:
        log.warning("mp_preference_failed", extra={"error": type(e).__name__})
        _fail_payment(user.ctx, payment_id)
        raise err(502, "PROVEEDOR_NO_DISPONIBLE", "Mercado Pago no respondió. Probá de nuevo en unos minutos.") from None
    with unit_of_work("worker", None, user.ctx, reason="Checkout creado en el proveedor de pagos") as w:
        w.execute(text("UPDATE app.payments SET mp_preference_id = :e WHERE id = :p"), {"e": pref["id"], "p": payment_id})
    return {"payment_id": payment_id, "status": "pending", "amount": pay["amount"], "currency": pay["currency"],
            "init_point": pref["init_point"], "simulated": pref["simulated"]}


# --------------------------------------------------------------------------- subir / bajar de plan
@router.post("/me/agencies/{agency_id}/subscription/upgrade", status_code=201)
def upgrade(agency_id: UUID, body: PlanIn, user: CurrentUser = Depends(current_user)):
    """Subir de plan. El límite nuevo rige recién cuando el pago queda aprobado."""
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    payment_gateway.require_enabled()
    with unit_of_work("worker", None, user.ctx, reason="Se reemplaza un pedido de mejora anterior sin pagar") as w:
        w.execute(text("""UPDATE app.payments py SET status = 'canceled', status_detail = 'reemplazado' FROM app.subscriptions s
                           WHERE s.id = py.subscription_id AND s.agency_id = :a AND py.plan_change_to IS NOT NULL AND py.status = 'pending'
                             AND py.payer_user_id = :u"""), {"a": agency_id, "u": user.id})
    with unit_of_work("app", user.id, user.ctx, reason="Pedido de mejora de plan") as conn:
        _require_agency_admin(conn, agency_id)
        sub = _current_sub(conn, agency_id)
        plan = row(conn, "SELECT id, name FROM app.plans WHERE id = :p AND is_active AND is_public", {"p": body.plan_id})
        if not plan:
            raise err(422, "PLAN_INVALIDO")
        pid = scalar(conn, """INSERT INTO app.payments (purpose, subscription_id, payer_user_id, agency_id, provider, amount, plan_change_to)
                              VALUES ('subscription', :s, :u, :a, 'mercadopago', 1, :p) RETURNING id""",     # monto real: lo fija el trigger con el plan nuevo
                     {"s": sub["id"], "u": user.id, "a": agency_id, "p": plan["id"]})
    return {**_checkout(user, pid, f"Girando · mejora a {plan['name']}", "suscripcion"), "from_plan": sub["plan_name"], "to_plan": plan["name"]}


@router.post("/me/agencies/{agency_id}/subscription/downgrade")
def downgrade(agency_id: UUID, body: PlanIn, user: CurrentUser = Depends(current_user)):
    """Bajar de plan: queda pendiente y rige al renovar. Lo que exceda el límite nuevo se pausa (no se borra)."""
    with unit_of_work("app", user.id, user.ctx, reason="Baja de plan pedida por el titular (rige al renovar)") as conn:
        _require_agency_admin(conn, agency_id)
        sub = _current_sub(conn, agency_id)
        conn.execute(text("UPDATE app.subscriptions SET pending_plan_id = :p WHERE id = :s"), {"p": body.plan_id, "s": sub["id"]})   # la base valida que sea una baja
        r = row(conn, """SELECT s.current_period_end, p.name AS pending_plan, p.price_amount, p.currency::text AS currency, p.max_active_listings
                           FROM app.subscriptions s JOIN app.plans p ON p.id = s.pending_plan_id WHERE s.id = :s""", {"s": sub["id"]})
    if sub["provider"] == "mercadopago" and payment_gateway.mode() == "mercadopago" and not payment_gateway.is_simulated(sub["external_subscription_id"]):
        try:   # el próximo cobro tiene que ser por el importe del plan nuevo
            MercadoPagoService().update_preapproval_amount(sub["external_subscription_id"], Decimal(r["price_amount"]), r["currency"])
        except (httpx.HTTPError, NotConfigured):
            raise err(502, "PROVEEDOR_NO_DISPONIBLE", "Registramos la baja, pero Mercado Pago no actualizó el importe. Reintentá en unos minutos.") from None
    return {"ok": True, "pending_plan": r["pending_plan"], "effective_at": r["current_period_end"], "new_limit": r["max_active_listings"]}


@router.delete("/me/agencies/{agency_id}/subscription/downgrade")
def cancel_downgrade(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx, reason="Se anula la baja de plan pendiente") as conn:
        _require_agency_admin(conn, agency_id)
        sub = _current_sub(conn, agency_id)
        conn.execute(text("UPDATE app.subscriptions SET pending_plan_id = NULL WHERE id = :s"), {"s": sub["id"]})
    return {"ok": True}


# --------------------------------------------------------------------------- promociones: destacar una publicación
PRODUCT_COLS = "id, code, name, description, type::text AS type, placement::text AS placement, price_amount, currency::text AS currency, duration_days"


@router.get("/promotion-products")
def promotion_products(request: Request):
    """Productos de promoción a la venta (precios cargados por el Super Admin)."""
    with unit_of_work("worker", None, request_ctx(request)) as conn:
        return {"items": rows(conn, f"SELECT {PRODUCT_COLS} FROM app.promotion_products WHERE is_active AND type <> 'banner_campaign' ORDER BY price_amount")}


class BuyPromotionIn(StrictModel):
    product_code: Annotated[str, StringConstraints(min_length=2, max_length=40)]
    listing_id: UUID | None = None
    agency_id: UUID | None = None


@router.post("/me/promotions", status_code=201)
def buy_promotion(body: BuyPromotionIn, user: CurrentUser = Depends(current_user)):
    """Particular o agencia compra una promoción. Nace 'pending' y se activa sola cuando el pago queda aprobado."""
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    payment_gateway.require_enabled()
    with unit_of_work("app", user.id, user.ctx, reason="Compra de promoción") as conn:
        prod = row(conn, f"SELECT {PRODUCT_COLS} FROM app.promotion_products WHERE code = :c AND is_active AND type <> 'banner_campaign'", {"c": body.product_code})
        if not prod:
            raise err(422, "PRODUCTO_NO_DISPONIBLE", "Esa promoción no está a la venta.")
        listing, target_agency = None, None
        if prod["type"] in ("featured_listing", "promoted_position"):
            listing = row(conn, "SELECT id, agency_id, status::text AS status FROM app.listings WHERE id = :l AND app.can_manage_listing_id(id)", {"l": body.listing_id})
            if not listing or listing["status"] != "published":
                raise err(422, "PUBLICACION_NO_PUBLICADA", "Solo se puede destacar una publicación tuya que esté publicada.")
            if scalar(conn, "SELECT 1 FROM app.promotions WHERE listing_id = :l AND product_id = :p AND status IN ('pending','active','paused') AND ends_at > now()",
                      {"l": listing["id"], "p": prod["id"]}):
                raise err(409, "PROMOCION_EXISTENTE", "Esa publicación ya tiene esta promoción vigente o esperando el pago.")
        else:
            _require_agency_admin(conn, body.agency_id)
            target_agency = body.agency_id
        paying = listing["agency_id"] if listing else target_agency
        prid = scalar(conn, """INSERT INTO app.promotions (product_id, type, placement, listing_id, target_agency_id, purchased_by, paying_agency_id,
                                                          price_amount, currency, starts_at, ends_at)
                               VALUES (:prod, CAST(:t AS app.promotion_type), CAST(:pl AS app.promotion_placement), :l, :ta, :u, :pa, :price,
                                       CAST(:cur AS app.currency_code), now(), now() + make_interval(days => :d)) RETURNING id""",
                      {"prod": prod["id"], "t": prod["type"], "pl": prod["placement"], "l": listing["id"] if listing else None, "ta": target_agency,
                       "u": user.id, "pa": paying, "price": prod["price_amount"], "cur": prod["currency"], "d": prod["duration_days"]})
        pid = scalar(conn, """INSERT INTO app.payments (purpose, promotion_id, payer_user_id, agency_id, provider, amount)
                              VALUES ('promotion', :pr, :u, :a, 'mercadopago', 1) RETURNING id""", {"pr": prid, "u": user.id, "a": paying})
    return {**_checkout(user, pid, f"Girando · {prod['name']}", "promociones"), "promotion_id": prid, "product": prod["name"]}


MY_PROMO_SQL = """SELECT pr.id, pr.type::text AS type, pr.placement::text AS placement, pr.status::text AS status, pr.starts_at, pr.ends_at,
       pr.price_amount, pr.currency::text AS currency, pr.disclosure_label, pp.name AS product, l.public_code AS listing_code, l.title AS listing_title,
       (SELECT py.status::text FROM app.payments py WHERE py.promotion_id = pr.id ORDER BY py.created_at DESC LIMIT 1) AS payment_status,
       (SELECT coalesce(sum(m.impressions), 0) FROM app.my_promotion_metrics(pr.id) m) AS impressions,
       (SELECT coalesce(sum(m.clicks), 0) FROM app.my_promotion_metrics(pr.id) m) AS clicks
  FROM app.promotions pr LEFT JOIN app.promotion_products pp ON pp.id = pr.product_id LEFT JOIN app.listings l ON l.id = pr.listing_id"""


@router.get("/me/promotions")
def my_promotions(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, MY_PROMO_SQL + """ WHERE pr.purchased_by = :u OR (pr.paying_agency_id IS NOT NULL
                                                         AND app.app_is_agency_member(pr.paying_agency_id, 'owner', 'admin'))
                                                       ORDER BY pr.created_at DESC LIMIT 100""", {"u": user.id})}


@router.get("/me/promotions/{promotion_id}/report")
def promotion_report(promotion_id: UUID, user: CurrentUser = Depends(current_user)):
    """Reporte para el anunciante: impresiones y clics REALES por día. Sin datos se informa "Sin datos suficientes"."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        p = row(conn, MY_PROMO_SQL + """ WHERE pr.id = :p AND (pr.purchased_by = :u OR app.app_has_staff_role('superadmin','finance')
                                           OR (pr.paying_agency_id IS NOT NULL AND app.app_is_agency_member(pr.paying_agency_id, 'owner', 'admin')))""",
                {"p": promotion_id, "u": user.id})
        if not p:
            raise err(404, "NO_ENCONTRADA", "Promoción inexistente.")
        days = rows(conn, "SELECT day, impressions, clicks FROM app.my_promotion_metrics(:p)", {"p": promotion_id})
    imp = int(p["impressions"])
    return {"promotion": p, "days": days,
            "ctr": round(int(p["clicks"]) * 100 / imp, 2) if imp >= 100 else None,     # con menos de 100 impresiones un porcentaje engaña
            "note": None if imp else "Sin datos suficientes: la promoción todavía no registró impresiones."}


# --------------------------------------------------------------------------- Super Admin: productos de promoción
class ProductPatch(StrictModel):
    price_amount: Annotated[Decimal, Field(ge=0, lt=Decimal("100000000"), max_digits=12, decimal_places=2)] | None = None
    duration_days: Annotated[int, Field(ge=1, le=365)] | None = None
    is_active: bool | None = None
    name: Annotated[str, StringConstraints(min_length=3, max_length=80)] | None = None


@router.get("/admin/promotion-products")
def admin_products(user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, f"SELECT {PRODUCT_COLS}, is_active FROM app.promotion_products ORDER BY name")}


@router.patch("/admin/promotion-products/{product_id}")
def admin_patch_product(product_id: UUID, body: ProductPatch, user: CurrentUser = Depends(SUPER)):
    d = body.model_dump(exclude_none=True)
    if not d:
        raise err(422, "DATO_INVALIDO", "No hay cambios.")
    with unit_of_work("app", user.id, user.ctx, reason="Edición de producto de promoción") as conn:
        sets = ", ".join(f"{k} = :{k}" for k in d)
        if not conn.execute(text(f"UPDATE app.promotion_products SET {sets} WHERE id = :id"), {**d, "id": product_id}).rowcount:
            raise err(404, "NO_ENCONTRADA", "Producto inexistente.")
        return row(conn, f"SELECT {PRODUCT_COLS}, is_active FROM app.promotion_products WHERE id = :id", {"id": product_id})


# --------------------------------------------------------------------------- simulador local del proveedor
class SimulateIn(StrictModel):
    target: Literal["subscription", "payment"]
    id: UUID
    outcome: Literal["approved", "rejected"] = "approved"
    event_id: Annotated[str, StringConstraints(min_length=4, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")] | None = None


@router.post("/dev/payments/simulate")
def simulate(body: SimulateIn, request: Request, user: CurrentUser = Depends(current_user)):
    """SOLO desarrollo/tests (PAYMENTS_SIMULATOR=true y sin token de Mercado Pago). Dispara el aviso que mandaría el
    proveedor y lo procesa por el MISMO código que el webhook real. Repetir un `event_id` es un aviso duplicado: no hace nada.
    Solo sobre suscripciones o pagos propios (o de cualquiera si sos Super Admin)."""
    if payment_gateway.mode() != "simulator":
        raise err(404, "NO_ENCONTRADA", "Recurso inexistente.")
    eid = body.event_id or uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()
    with unit_of_work("app", user.id, user.ctx) as conn:     # RLS: solo ve lo suyo
        if body.target == "subscription":
            sub = row(conn, "SELECT id, external_subscription_id, price_amount FROM app.subscriptions WHERE id = :i", {"i": body.id})
            if not sub or not payment_gateway.is_simulated(sub["external_subscription_id"]):
                raise err(404, "NO_ENCONTRADA", "Suscripción inexistente o no creada con el simulador.")
            topic = "subscription_authorized_payment"
            res = {"id": f"SIMAP-{eid}", "preapproval_id": sub["external_subscription_id"], "status": "processed", "debit_date": now,
                   "transaction_amount": float(sub["price_amount"]), "payment": {"id": f"SIMPAY-{eid}", "status": body.outcome, "date_approved": now}}
        else:
            pay = row(conn, "SELECT id, external_reference, amount, mp_preference_id FROM app.payments WHERE id = :i AND provider = 'mercadopago'", {"i": body.id})
            if not pay or not payment_gateway.is_simulated(pay["mp_preference_id"]):
                raise err(404, "NO_ENCONTRADA", "Pago inexistente o no creado con el simulador.")
            topic = "payment"
            res = {"id": f"SIMPAY-{eid}", "status": body.outcome, "external_reference": pay["external_reference"], "date_approved": now,
                   "transaction_amount": float(pay["amount"]), "status_detail": "simulado"}
    out = process_provider_event(request_ctx(request), topic=topic, data_id=res["id"], key=f"sim:{topic}:{eid}",
                                 payload={"action": "simulated", "by": str(user.id)}, valid=True, fetch=lambda: res)
    return out
