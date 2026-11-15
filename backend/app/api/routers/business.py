"""/api/admin — Negocio (Super Admin): visión general, finanzas, planes asignados a mano,
promociones y contenido de la Home. También el detalle de verificaciones (operación).

Reglas:
  · Todo número sale de PostgreSQL (eventos, pagos, suscripciones reales). Sin estimaciones.
  · Una promoción paga solo se activa con un pago aprobado; las cortesías tienen precio 0 y quedan auditadas.
  · El plan asignado a mano (cortesía/convenio) no pasa por Mercado Pago y no se renueva solo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field, StringConstraints, field_validator, model_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, require_roles, staff_user
from app.core import ratelimit
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.schemas.common import StrictModel, clean_text


def _rl(user: CurrentUser = Depends(staff_user)) -> CurrentUser:
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    return user


router = APIRouter(prefix="/api/admin", tags=["admin · negocio"], dependencies=[Depends(_rl)])
SUPER = require_roles("superadmin")
FINANCE = require_roles("finance")
MOD = require_roles("moderator", "admin")
TZ = "America/Argentina/Buenos_Aires"
Reason = Annotated[str, StringConstraints(min_length=3, max_length=500)]


# --------------------------------------------------------------------------- visión del dueño
@router.get("/business")
def business(user: CurrentUser = Depends(FINANCE)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        out = {
            "users": row(conn, """SELECT count(*) FILTER (WHERE status <> 'deleted') AS total, count(*) FILTER (WHERE status = 'active') AS active,
                                         count(*) FILTER (WHERE created_at > now() - interval '30 days') AS new_30d FROM app.users"""),
            "agencies": {r["state"]: r["n"] for r in rows(conn, """SELECT app.agency_verification_state(id) AS state, count(*) AS n
                                                                   FROM app.agencies GROUP BY 1""")},
            "listings": row(conn, """SELECT count(*) FILTER (WHERE status = 'published') AS published, count(*) FILTER (WHERE status = 'pending') AS pending,
                                            count(*) FILTER (WHERE status IN ('draft','paused','requires_changes','expired')) AS inventory,
                                            count(*) FILTER (WHERE status = 'sold') AS sold FROM app.listings"""),
            # Suscripciones que hoy otorgan plan. MRR solo con lo que se cobra (manual = cortesía, no suma).
            "subscriptions": rows(conn, """SELECT p.code, p.name, p.max_active_listings, s.provider::text AS provider, count(*) AS n,
                                                  sum(CASE WHEN s.provider = 'manual' THEN 0
                                                           WHEN s.billing_period = 'year' THEN s.price_amount / 12 ELSE s.price_amount END) AS mrr_ars
                                             FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id
                                            WHERE app.subscription_grants(s) GROUP BY 1, 2, 3, 4 ORDER BY 1"""),
            "subscriptions_by_status": {r["status"]: r["n"] for r in rows(conn, "SELECT status::text AS status, count(*) AS n FROM app.subscriptions GROUP BY 1")},
            "plans": rows(conn, """SELECT p.id, p.code, p.name, p.audience::text AS audience, p.price_amount, p.max_active_listings, p.is_active,
                                          (SELECT count(*) FROM app.subscriptions s WHERE s.plan_id = p.id AND app.subscription_grants(s)) AS active_subscriptions
                                     FROM app.plans p ORDER BY p.audience, p.sort_order"""),
            "payments": row(conn, f"""SELECT count(*) FILTER (WHERE status IN ('pending','in_process')) AS pending,
                                             count(*) FILTER (WHERE status = 'submitted') AS transfers_to_review,
                                             coalesce(sum(amount) FILTER (WHERE status = 'approved' AND currency = 'ARS'
                                                 AND date_trunc('month', paid_at AT TIME ZONE '{TZ}') = date_trunc('month', now() AT TIME ZONE '{TZ}')), 0) AS collected_month_ars,
                                             coalesce(sum(amount) FILTER (WHERE status = 'approved' AND currency = 'ARS' AND paid_at > now() - interval '30 days'), 0) AS collected_30d_ars
                                        FROM app.payments"""),
            "promotions": rows(conn, """SELECT pr.id, pr.type::text AS type, pr.placement::text AS placement, pr.status::text AS status, pr.ends_at,
                                               coalesce(l.title, a.trade_name, pr.advertiser_name) AS target, pr.price_amount
                                          FROM app.promotions pr LEFT JOIN app.listings l ON l.id = pr.listing_id LEFT JOIN app.agencies a ON a.id = pr.target_agency_id
                                         WHERE pr.status IN ('active','paused','pending') ORDER BY pr.status, pr.ends_at LIMIT 50"""),
            "home_blocks": rows(conn, """SELECT id, kind::text AS kind, title, status::text AS status, starts_at, ends_at FROM app.home_blocks
                                          WHERE status = 'active' ORDER BY kind, sort_order"""),
            "expiring": rows(conn, """SELECT s.id, a.trade_name, p.name AS plan, s.provider::text AS provider, s.current_period_end
                                        FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.agencies a ON a.id = s.agency_id
                                       WHERE app.subscription_grants(s) AND s.current_period_end < now() + interval '15 days'
                                       ORDER BY s.current_period_end LIMIT 50"""),
            # Eventos reales de los últimos 30 días (si no hay, no se muestra nada)
            "events_30d": {r["e"]: r["n"] for r in rows(conn, """SELECT event_name::text AS e, count(*) AS n FROM app.analytics_events
                                                                 WHERE occurred_at > now() - interval '30 days' GROUP BY 1""")},
        }
        return out


# --------------------------------------------------------------------------- finanzas
@router.get("/finance/summary")
def finance_summary(months: int = Query(6, ge=1, le=24), user: CurrentUser = Depends(FINANCE)):
    """Administración comercial interna (no es contabilidad fiscal).
    facturado = pagos emitidos en el mes (no cancelados) · cobrado = aprobados por fecha de cobro ·
    pendiente = pending/in_process · por verificar = transferencias informadas · rechazado = rejected/charged_back."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        by_month = rows(conn, f"""
            WITH m AS (SELECT generate_series(date_trunc('month', now() AT TIME ZONE '{TZ}') - make_interval(months => :n - 1),
                                              date_trunc('month', now() AT TIME ZONE '{TZ}'), interval '1 month')::date AS month)
            SELECT m.month,
                   coalesce(sum(p.amount) FILTER (WHERE p.status NOT IN ('canceled') AND date_trunc('month', p.created_at AT TIME ZONE '{TZ}')::date = m.month), 0) AS billed,
                   coalesce(sum(p.amount) FILTER (WHERE p.status = 'approved' AND date_trunc('month', p.paid_at AT TIME ZONE '{TZ}')::date = m.month), 0) AS collected,
                   coalesce(sum(p.amount) FILTER (WHERE p.status IN ('pending','in_process') AND date_trunc('month', p.created_at AT TIME ZONE '{TZ}')::date = m.month), 0) AS pending,
                   coalesce(sum(p.amount) FILTER (WHERE p.status = 'submitted' AND date_trunc('month', p.created_at AT TIME ZONE '{TZ}')::date = m.month), 0) AS to_verify,
                   coalesce(sum(p.amount) FILTER (WHERE p.status IN ('rejected','charged_back') AND date_trunc('month', p.created_at AT TIME ZONE '{TZ}')::date = m.month), 0) AS rejected
              FROM m LEFT JOIN app.payments p ON p.currency = 'ARS'
             GROUP BY m.month ORDER BY m.month""", {"n": months})
        breakdown = rows(conn, """SELECT purpose::text AS purpose, provider::text AS provider, status::text AS status, count(*) AS n, sum(amount) AS amount
                                    FROM app.payments WHERE created_at > now() - make_interval(months => :n)
                                   GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""", {"n": months})
        transfers = rows(conn, """SELECT py.id, py.transfer_reference, py.amount, py.transfer_declared_at, a.trade_name
                                    FROM app.payments py LEFT JOIN app.agencies a ON a.id = py.agency_id
                                   WHERE py.status = 'submitted' ORDER BY py.transfer_declared_at LIMIT 100""")
        renewals = rows(conn, """SELECT s.id, a.trade_name, p.name AS plan, s.status::text AS status, s.provider::text AS provider,
                                        s.price_amount, s.current_period_end, s.cancel_at_period_end
                                   FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.agencies a ON a.id = s.agency_id
                                  WHERE app.subscription_grants(s) ORDER BY s.current_period_end LIMIT 200""")
        comps = scalar(conn, "SELECT count(*) FROM app.subscriptions s WHERE s.provider = 'manual' AND app.subscription_grants(s)")
        return {"months": months, "currency": "ARS", "by_month": by_month, "breakdown": breakdown, "transfers_to_review": transfers,
                "subscriptions": renewals, "manual_active": comps,
                "note": "Montos en pesos. Los pagos en otra moneda no se convierten acá."}


# --------------------------------------------------------------------------- plan asignado a mano
class GrantPlanIn(StrictModel):
    plan_id: UUID
    notes: Reason

    @field_validator("notes")
    @classmethod
    def _c(cls, v):
        return clean_text(v)


@router.post("/agencies/{agency_id}/plan", status_code=201)
def grant_plan(agency_id: UUID, body: GrantPlanIn, user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx, reason=f"Plan asignado manualmente: {body.notes}") as conn:
        if not scalar(conn, "SELECT 1 FROM app.agencies WHERE id = :a", {"a": agency_id}):
            raise err(404, "NO_ENCONTRADA", "Agencia inexistente.")
        plan = row(conn, "SELECT id, billing_period::text AS period FROM app.plans WHERE id = :p AND audience = 'agency' AND is_active", {"p": body.plan_id})
        if not plan:
            raise err(422, "PLAN_INVALIDO", "Elegí un plan de agencia activo.")
        cur = row(conn, """SELECT id, provider::text AS provider, status::text AS status FROM app.subscriptions
                            WHERE agency_id = :a AND status IN ('pending','active','payment_failed','grace_period','canceled')
                            ORDER BY created_at DESC LIMIT 1""", {"a": agency_id})
        if cur and cur["provider"] != "manual" and cur["status"] != "pending":
            raise err(409, "SUSCRIPCION_PAGA_VIGENTE", "La agencia tiene una suscripción paga vigente. Cancelala primero en su proveedor.")
        if cur:
            conn.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": cur["id"]})
        period = plan["period"] if plan["period"] != "none" else "month"
        sid = scalar(conn, f"""INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, status, price_amount, currency, billing_period,
                                                             started_at, current_period_start, current_period_end, billing_anchor_day, notes)
                               VALUES (:p, :a, :u, 'manual', 'active', 0, 'ARS', CAST(:per AS app.billing_period), now(), now(),
                                       app.next_period_end(now(), CAST(:per AS app.billing_period)),
                                       extract(day FROM now() AT TIME ZONE '{TZ}')::int, :n) RETURNING id""",
                     {"p": plan["id"], "a": agency_id, "u": user.id, "per": period, "n": body.notes})
        owner = scalar(conn, "SELECT user_id FROM app.agency_members WHERE agency_id = :a AND role = 'owner' AND status = 'active'", {"a": agency_id})
        if owner:
            conn.execute(text("SELECT app.enqueue_notification(:u, 'subscription.activated', 'Tu plan está activo', 'Girando te asignó un plan. Ya podés publicar según su límite.', 'agency', :a, '/suscripcion')"),
                         {"u": owner, "a": agency_id})
    return {"ok": True, "subscription_id": sid}


class EndPlanIn(StrictModel):
    reason: Reason


@router.post("/agencies/{agency_id}/plan/end")
def end_plan(agency_id: UUID, body: EndPlanIn, user: CurrentUser = Depends(SUPER)):
    note = clean_text(body.reason)
    with unit_of_work("app", user.id, user.ctx, reason=note) as conn:
        sid = scalar(conn, """SELECT id FROM app.subscriptions WHERE agency_id = :a AND provider = 'manual'
                               AND status IN ('active','grace_period','payment_failed','canceled') ORDER BY created_at DESC LIMIT 1""", {"a": agency_id})
        if not sid:
            raise err(409, "SIN_PLAN_MANUAL", "La agencia no tiene un plan asignado manualmente.")
        conn.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": sid})
    with unit_of_work("worker", None, user.ctx, reason="Plan finalizado: pausar lo que excede el límite") as w:
        paused = scalar(w, "SELECT app.enforce_plan_limit(NULL, :a)", {"a": agency_id})
    return {"ok": True, "paused_listings": paused}


# --------------------------------------------------------------------------- promociones
PROMO_TYPES = Literal["featured_listing", "promoted_position", "featured_agency", "banner_campaign"]
PLACEMENTS = Literal["home_featured", "home_banner", "search_top", "search_brand_model", "agency_directory"]


class PromotionIn(StrictModel):
    type: PROMO_TYPES
    placement: PLACEMENTS
    listing_code: Annotated[str, StringConstraints(pattern=r"^P-[A-Z0-9]{8}$")] | None = None
    agency_id: UUID | None = None
    advertiser_name: Annotated[str, StringConstraints(min_length=2, max_length=80)] | None = None
    link_url: Annotated[str, StringConstraints(max_length=300, pattern=r"^https://\S+$")] | None = None
    creative_public_id: Annotated[str, StringConstraints(max_length=300)] | None = None
    starts_at: datetime
    ends_at: datetime
    price_amount: Annotated[float, Field(ge=0, le=100_000_000)] = 0
    priority: Annotated[int, Field(ge=0, le=100)] = 0
    disclosure_label: Literal["Patrocinado", "Publicidad"] = "Patrocinado"
    notes: Annotated[str, StringConstraints(max_length=300)] | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("La fecha de fin tiene que ser posterior a la de inicio")
        if self.type in ("featured_listing", "promoted_position") and not self.listing_code:
            raise ValueError("Indicá el código de la publicación (P-XXXXXXXX)")
        if self.type == "featured_agency" and not self.agency_id:
            raise ValueError("Elegí la agencia a destacar")
        if self.type == "banner_campaign" and not (self.advertiser_name and self.link_url):
            raise ValueError("Un banner necesita anunciante y enlace https")
        return self


PROMO_SQL = """SELECT pr.id, pr.type::text AS type, pr.placement::text AS placement, pr.status::text AS status, pr.priority, pr.disclosure_label,
                      pr.starts_at, pr.ends_at, pr.price_amount, pr.currency::text AS currency, pr.status_reason, pr.approved_at, pr.created_at,
                      pr.advertiser_name, pr.link_url, pr.creative_public_id, l.public_code AS listing_code, l.title AS listing_title,
                      a.trade_name AS agency_name, pp.name AS product,
                      (SELECT py.status::text FROM app.payments py WHERE py.promotion_id = pr.id ORDER BY py.created_at DESC LIMIT 1) AS payment_status
                 FROM app.promotions pr LEFT JOIN app.listings l ON l.id = pr.listing_id LEFT JOIN app.agencies a ON a.id = pr.target_agency_id
                 LEFT JOIN app.promotion_products pp ON pp.id = pr.product_id"""


@router.get("/promotions")
def promotions(status: str | None = None, user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, PROMO_SQL + " WHERE CAST(:s AS text) IS NULL OR pr.status::text = :s ORDER BY pr.created_at DESC LIMIT 200", {"s": status}),
                "products": rows(conn, """SELECT id, code, name, type::text AS type, placement::text AS placement, price_amount, duration_days, is_active
                                            FROM app.promotion_products ORDER BY name""")}


@router.post("/promotions", status_code=201)
def create_promotion(body: PromotionIn, user: CurrentUser = Depends(SUPER)):
    d = body.model_dump()
    with unit_of_work("app", user.id, user.ctx, reason=f"Alta de promoción{(': ' + clean_text(body.notes)) if body.notes else ''}") as conn:
        listing_id = None
        if body.listing_code:
            listing_id = scalar(conn, "SELECT id FROM app.listings WHERE public_code = :c AND status = 'published'", {"c": body.listing_code})
            if not listing_id:
                raise err(422, "PUBLICACION_NO_PUBLICADA", "La publicación no existe o no está publicada.")
        pid = scalar(conn, """INSERT INTO app.promotions (type, placement, listing_id, target_agency_id, advertiser_name, link_url, creative_public_id,
                                                         purchased_by, price_amount, starts_at, ends_at, priority, disclosure_label)
                              VALUES (CAST(:type AS app.promotion_type), CAST(:placement AS app.promotion_placement), :l, :agency_id,
                                      :advertiser_name, :link_url, :creative_public_id, :u, :price_amount, :starts_at, :ends_at, :priority, :disclosure_label)
                              RETURNING id""", {**d, "l": listing_id, "u": user.id,
                                                "agency_id": d["agency_id"] if body.type == "featured_agency" else None,
                                                "advertiser_name": d["advertiser_name"] if body.type == "banner_campaign" else None,
                                                "link_url": d["link_url"] if body.type == "banner_campaign" else None})
        conn.execute(text("""INSERT INTO app.promotion_events (promotion_id, event, to_status, actor_user_id, actor_type, reason)
                             VALUES (:p, 'created', 'pending', :u, 'staff', :r)"""), {"p": pid, "u": user.id, "r": body.notes})
        return row(conn, PROMO_SQL + " WHERE pr.id = :p", {"p": pid})


PROMO_MOVES = {  # acción: (desde, hacia, evento)
    "activate": (("pending",), "active", "activated"),
    "pause": (("active",), "paused", "paused"),
    "resume": (("paused",), "active", "resumed"),
    "finish": (("active", "paused"), "finished", "finished"),
    "cancel": (("pending", "active", "paused"), "canceled", "canceled"),
}


class PromoActionIn(StrictModel):
    reason: Reason | None = None


@router.post("/promotions/{promotion_id}/{action}")
def promotion_action(promotion_id: UUID, action: Literal["activate", "pause", "resume", "finish", "cancel"], body: PromoActionIn,
                     user: CurrentUser = Depends(SUPER)):
    src, dst, event = PROMO_MOVES[action]
    if action in ("cancel", "pause") and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    with unit_of_work("app", user.id, user.ctx, reason=body.reason) as conn:
        p = row(conn, """SELECT id, status::text AS status, price_amount, type::text AS type, creative_public_id, ends_at
                           FROM app.promotions WHERE id = :p FOR UPDATE""", {"p": promotion_id})
        if not p:
            raise err(404, "NO_ENCONTRADA", "Promoción inexistente.")
        if p["status"] not in src:
            raise err(409, "TRANSICION_NO_PERMITIDA", f"No se puede {action} una promoción en estado {p['status']}.")
        if dst == "active":
            if p["ends_at"] <= scalar(conn, "SELECT now()"):
                raise err(409, "PROMOCION_VENCIDA", "La fecha de fin ya pasó.")
            if p["price_amount"] > 0 and not scalar(conn, "SELECT 1 FROM app.payments WHERE promotion_id = :p AND status = 'approved'", {"p": promotion_id}):
                raise err(409, "PAGO_PENDIENTE", "Una promoción paga se activa recién con el pago aprobado. Las cortesías tienen precio 0.")
            if p["type"] == "banner_campaign" and not p["creative_public_id"]:
                raise err(409, "FALTA_CREATIVIDAD", "El banner necesita su imagen antes de activarse.")
        conn.execute(text(f"""UPDATE app.promotions SET status = CAST(:d AS app.promotion_status), status_reason = :r
                              {", approved_by = :u, approved_at = coalesce(approved_at, now())" if dst == "active" else ""} WHERE id = :p"""),
                     {"d": dst, "r": body.reason, "u": user.id, "p": promotion_id})
        conn.execute(text("""INSERT INTO app.promotion_events (promotion_id, event, from_status, to_status, actor_user_id, actor_type, reason)
                             VALUES (:p, CAST(:e AS app.promotion_event_type), CAST(:f AS app.promotion_status), CAST(:t AS app.promotion_status), :u, 'staff', :r)"""),
                     {"p": promotion_id, "e": event, "f": p["status"], "t": dst, "u": user.id, "r": body.reason})
        return row(conn, PROMO_SQL + " WHERE pr.id = :p", {"p": promotion_id})


# --------------------------------------------------------------------------- Home administrable
HOME_TARGETS = Literal["listado", "publicar", "planes", "registro"]


class HomeBlockIn(StrictModel):
    kind: Literal["hero", "announcement", "cta"]
    title: Annotated[str, StringConstraints(min_length=3, max_length=90)]
    body: Annotated[str, StringConstraints(max_length=280)] | None = None
    image_public_id: Annotated[str, StringConstraints(max_length=300)] | None = None
    cta_label: Annotated[str, StringConstraints(min_length=2, max_length=30)] | None = None
    cta_target: Annotated[str, StringConstraints(max_length=300)] | None = None
    sort_order: Annotated[int, Field(ge=0, le=100)] = 0
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: Literal["draft", "active", "archived"] = "draft"

    @field_validator("title", "body", "cta_label")
    @classmethod
    def _c(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def _shape(self):
        if (self.cta_label is None) != (self.cta_target is None):
            raise ValueError("El botón necesita texto y destino")
        if self.cta_target and not (self.cta_target in ("listado", "publicar", "planes", "registro") or self.cta_target.startswith("https://")):
            raise ValueError("Destino del botón: listado, publicar, planes, registro o un enlace https")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("La fecha de fin tiene que ser posterior a la de inicio")
        return self


HB_COLS = """id, kind::text AS kind, status::text AS status, title, body, image_public_id, cta_label, cta_target, sort_order,
             starts_at, ends_at, created_at, updated_at"""


@router.get("/home-blocks")
def home_blocks(user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, f"SELECT {HB_COLS} FROM app.home_blocks WHERE status <> 'archived' ORDER BY kind, sort_order, created_at")}


@router.post("/home-blocks", status_code=201)
def create_home_block(body: HomeBlockIn, user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx, reason="Contenido de la Home") as conn:
        bid = scalar(conn, """INSERT INTO app.home_blocks (kind, status, title, body, image_public_id, cta_label, cta_target, sort_order, starts_at, ends_at, created_by)
                              VALUES (CAST(:kind AS app.home_block_kind), CAST(:status AS app.home_block_status), :title, :body, :image_public_id,
                                      :cta_label, :cta_target, :sort_order, :starts_at, :ends_at, :u) RETURNING id""", {**body.model_dump(), "u": user.id})
        return row(conn, f"SELECT {HB_COLS} FROM app.home_blocks WHERE id = :b", {"b": bid})


@router.put("/home-blocks/{block_id}")
def update_home_block(block_id: UUID, body: HomeBlockIn, user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx, reason="Contenido de la Home") as conn:
        res = conn.execute(text("""UPDATE app.home_blocks SET kind = CAST(:kind AS app.home_block_kind), status = CAST(:status AS app.home_block_status),
                                      title = :title, body = :body, image_public_id = :image_public_id, cta_label = :cta_label, cta_target = :cta_target,
                                      sort_order = :sort_order, starts_at = :starts_at, ends_at = :ends_at, updated_by = :u WHERE id = :b"""),
                           {**body.model_dump(), "u": user.id, "b": block_id})
        if not res.rowcount:
            raise err(404, "NO_ENCONTRADO", "Bloque inexistente.")
        return row(conn, f"SELECT {HB_COLS} FROM app.home_blocks WHERE id = :b", {"b": block_id})


# --------------------------------------------------------------------------- verificaciones (operación)
@router.get("/verifications/{verification_id}")
def verification_detail(verification_id: UUID, user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        v = row(conn, """SELECT v.id, v.status::text AS status, v.checklist, v.evidence_notes, v.decision_reason, v.created_at, v.review_started_at,
                                v.decided_at, v.expires_at, p.name AS product, p.code AS product_code, p.checklist_template, p.public_disclaimer,
                                v.subject_agency_id AS agency_id, a.trade_name, a.legal_name, a.cuit, a.website_url, a.phone_e164, a.email::text AS agency_email,
                                g.name AS locality, app.agency_verification_state(a.id) AS agency_state,
                                rq.display_name AS requested_by_name, rv.display_name AS reviewer_name, asg.display_name AS assigned_to_name
                           FROM app.verifications v JOIN app.verification_products p ON p.id = v.product_id
                           LEFT JOIN app.agencies a ON a.id = v.subject_agency_id LEFT JOIN app.geo_areas g ON g.id = a.geo_area_id
                           LEFT JOIN app.user_profiles rq ON rq.user_id = v.requested_by LEFT JOIN app.user_profiles rv ON rv.user_id = v.reviewer_id
                           LEFT JOIN app.user_profiles asg ON asg.user_id = v.assigned_to
                          WHERE v.id = :v""", {"v": verification_id})
        if not v:
            raise err(404, "NO_ENCONTRADA", "Verificación inexistente.")
        # Checklist: plantilla del producto + lo marcado en esta solicitud
        done = {i.get("key"): i for i in (v["checklist"] or []) if isinstance(i, dict)}
        v["items"] = [{"key": t["key"], "label": t["label"], "done": bool(done.get(t["key"], {}).get("done")),
                       "note": done.get(t["key"], {}).get("note")} for t in (v["checklist_template"] or [])]
        v["history"] = rows(conn, """SELECT occurred_at AS at, action, actor_role, reason FROM app.audit_logs
                                      WHERE entity_type = 'verifications' AND entity_id = :v ORDER BY id DESC LIMIT 30""", {"v": verification_id}) \
            if user.has_role("superadmin") else []
        return v


class ChecklistItem(StrictModel):
    key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{2,40}$")]
    done: bool
    note: Annotated[str, StringConstraints(max_length=300)] | None = None


class VerificationPatch(StrictModel):
    checklist: list[ChecklistItem] | None = None
    evidence_notes: Annotated[str, StringConstraints(max_length=4000)] | None = None
    assign_to_me: bool = False
    start_review: bool = False


@router.patch("/verifications/{verification_id}")
def verification_patch(verification_id: UUID, body: VerificationPatch, user: CurrentUser = Depends(MOD)):
    import json
    with unit_of_work("app", user.id, user.ctx, reason="Revisión de verificación") as conn:
        v = row(conn, "SELECT status::text AS status, requested_by, subject_agency_id FROM app.verifications WHERE id = :v FOR UPDATE", {"v": verification_id})
        if not v:
            raise err(404, "NO_ENCONTRADA", "Verificación inexistente.")
        if v["status"] not in ("pending", "review"):
            raise err(409, "VERIFICACION_CERRADA", "La verificación ya tiene una decisión.")
        sets, p = [], {"v": verification_id}
        if body.checklist is not None:
            sets.append("checklist = CAST(:cl AS jsonb)")
            p["cl"] = json.dumps([{"key": i.key, "done": i.done, "note": clean_text(i.note) if i.note else None, "by": str(user.id)} for i in body.checklist])
        if body.evidence_notes is not None:
            sets.append("evidence_notes = :ev")
            p["ev"] = clean_text(body.evidence_notes) or None
        if body.assign_to_me:
            sets.append("assigned_to = :u")
            p["u"] = user.id
        if body.start_review and v["status"] == "pending":
            sets.append("status = 'review'")
        if sets:
            conn.execute(text(f"UPDATE app.verifications SET {', '.join(sets)} WHERE id = :v"), p)
    return verification_detail(verification_id, user)
