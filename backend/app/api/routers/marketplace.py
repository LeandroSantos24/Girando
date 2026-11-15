"""Fase 4 · Marketplace: financiación por entidad, similares y recomendaciones explicables,
búsquedas guardadas, historial del usuario, consentimiento de cookies y eventos de publicidad.

Reglas:
  · Una oferta de financiación solo se ve si Moderación la aprobó y está vigente (api_public.*).
  · Si hay tasa, van TNA, TEA y CFT juntas (lo exige la base). Si no hay, no se inventa.
  · Las recomendaciones personalizadas usan actividad PROPIA de Girando y solo con consentimiento
    de analítica; sin consentimiento se recomienda por contexto. Siempre devuelven el motivo.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import Field, StringConstraints, field_validator, model_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, current_user, optional_user, request_ctx, require_roles
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.core.middleware import client_ip
from app.schemas.common import StrictModel, clean_text
from app.services import search_service

router = APIRouter(prefix="/api", tags=["marketplace · fase 4"])
ANON_COOKIE = "gr_aid"
MOD = require_roles("moderator", "admin")
ADMIN = require_roles("admin")

Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Money = Annotated[Decimal, Field(ge=0, lt=Decimal("100000000000"), max_digits=14, decimal_places=2)]
Rate = Annotated[Decimal, Field(ge=0, le=9999, max_digits=7, decimal_places=2)]
FinType = Literal["bank_loan", "pledge_loan", "dealer_financing", "savings_plan", "other"]

OFFER_COLS = """o.id, o.agency_id, o.entity_id, coalesce(e.name, a.trade_name) AS entity_name, o.type::text AS type, o.title, o.currency::text AS currency,
    o.min_down_payment_pct, o.min_down_payment_amount, o.max_financed_pct, o.max_financed_amount, o.terms_months, o.tna, o.tea, o.cft,
    o.rate_kind::text AS rate_kind, o.applies_to_condition::text AS applies_to_condition, o.max_vehicle_age_years, o.applies_to_all,
    o.valid_from, o.valid_until, o.conditions, o.source, o.source_url, o.status::text AS status, o.status_reason, o.reviewed_at, o.created_at"""
OFFER_FROM = "FROM app.financing_offers o LEFT JOIN app.financing_entities e ON e.id = o.entity_id LEFT JOIN app.agencies a ON a.id = o.agency_id"
PUBLIC_OFFER_COLS = """id, entity_id, entity_name, entity_kind::text AS entity_kind, logo_authorized, logo_public_id, type::text AS type, title,
    currency::text AS currency, min_down_payment_pct, min_down_payment_amount, max_financed_pct, max_financed_amount, terms_months,
    tna, tea, cft, rate_kind::text AS rate_kind, valid_until, conditions, source, source_url"""


# --------------------------------------------------------------------------- financiación: público
@router.get("/financing/entities")
def financing_entities(request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT id, slug, name, kind::text AS kind, website_url, logo_authorized, logo_public_id
                                        FROM api_public.financing_entities ORDER BY name""")}


def _listing(conn, code: str) -> dict:
    d = row(conn, "SELECT id, price_amount, currency::text AS currency FROM api_public.listings WHERE public_code = :c OR id::text = :c", {"c": code[:64]})
    if not d:
        raise err(404, "NO_ENCONTRADA", "La publicación no existe o ya no está disponible.")
    return d


@router.get("/listings/{code}/financing")
def listing_financing(code: str, request: Request):
    """Ofertas de financiación de una publicación con el "con cuánto lo retirás" ya calculado por la base."""
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        d = _listing(conn, code)
        offers = rows(conn, f"""SELECT {PUBLIC_OFFER_COLS}, down_payment, financed_amount, term_max, installment_min
                                 FROM api_public.listing_financing WHERE listing_id = :l ORDER BY cft NULLS LAST, valid_until""", {"l": d["id"]})
        return {"price_amount": d["price_amount"], "currency": d["currency"], "offers": offers,
                "disclaimer": scalar(conn, "SELECT value #>> '{}' FROM api_public.settings WHERE key = 'financing.disclaimer'")}


@router.get("/listings/{code}/financing/simulate")
def simulate_financing(code: str, request: Request, offer_id: UUID,
                       down_payment: Annotated[Decimal, Query(ge=0, le=10**11)], months: Annotated[int, Query(ge=1, le=120)]):
    """Calculadora ORIENTATIVA. Valida contra la oferta: anticipo mínimo, tope financiable y plazos ofrecidos."""
    ratelimit.hit(ratelimit.SEARCH_IP, client_ip(request))
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        d = _listing(conn, code)
        o = row(conn, f"""SELECT {PUBLIC_OFFER_COLS}, down_payment AS min_down, financed_amount AS max_financed
                           FROM api_public.listing_financing WHERE listing_id = :l AND id = :o""", {"l": d["id"], "o": offer_id})
        if not o:
            raise err(404, "OFERTA_NO_DISPONIBLE", "Esa oferta no está disponible para esta publicación.")
        if o["min_down"] is None:
            raise err(422, "MONEDA_DISTINTA", "La oferta está en otra moneda que la publicación: consultá a la entidad.")
        if months not in o["terms_months"]:
            raise err(422, "PLAZO_NO_OFRECIDO", f"Plazos disponibles: {', '.join(str(m) for m in sorted(o['terms_months']))} meses.")
        if down_payment < o["min_down"] or down_payment >= d["price_amount"]:
            raise err(422, "ANTICIPO_INVALIDO", f"El anticipo mínimo para esta oferta es {o['min_down']:.0f} {d['currency']}.")
        financed = d["price_amount"] - down_payment
        inst = scalar(conn, "SELECT app.financing_installment(:p, :t, :m)", {"p": financed, "t": o["tna"], "m": months})
        return {"orientative": True, "price_amount": d["price_amount"], "currency": d["currency"], "down_payment": down_payment,
                "financed_amount": financed, "months": months, "installment": inst,
                "tna": o["tna"], "tea": o["tea"], "cft": o["cft"], "rate_kind": o["rate_kind"], "entity_name": o["entity_name"],
                "valid_until": o["valid_until"], "source": o["source"],
                "note": None if inst is not None else "La oferta no informa tasa: no se puede estimar la cuota. Consultá a la entidad.",
                "disclaimer": scalar(conn, "SELECT value #>> '{}' FROM api_public.settings WHERE key = 'financing.disclaimer'")}


@router.get("/listings/{code}/price-history")
def price_history(code: str, request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        d = _listing(conn, code)
        return {"items": rows(conn, """SELECT old_amount, old_currency::text AS old_currency, new_amount, new_currency::text AS new_currency, created_at
                                        FROM api_public.listing_price_history WHERE listing_id = :l ORDER BY created_at""", {"l": d["id"]})}


# --------------------------------------------------------------------------- financiación: agencia
class OfferIn(StrictModel):
    entity_id: UUID | None = None
    type: FinType
    title: Annotated[str, StringConstraints(min_length=3, max_length=80)]
    currency: Literal["ARS", "USD"] = "ARS"
    min_down_payment_pct: Pct | None = None
    min_down_payment_amount: Money | None = None
    max_financed_pct: Pct | None = None
    max_financed_amount: Money | None = None
    terms_months: Annotated[list[Annotated[int, Field(ge=1, le=120)]], Field(min_length=1, max_length=12)]
    tna: Rate | None = None
    tea: Rate | None = None
    cft: Rate | None = None
    rate_kind: Literal["fixed", "variable", "mixed"] | None = None
    applies_to_condition: Literal["new", "used"] | None = None
    max_vehicle_age_years: Annotated[int, Field(ge=0, le=40)] | None = None
    applies_to_all: bool = False
    valid_from: date | None = None
    valid_until: date
    conditions: Annotated[str, StringConstraints(max_length=2000)] | None = None
    source: Annotated[str, StringConstraints(min_length=3, max_length=300)]
    source_url: Annotated[str, StringConstraints(max_length=300, pattern=r"^https://\S+$")] | None = None

    @field_validator("title", "conditions", "source")
    @classmethod
    def _c(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def _shape(self):
        rates = [self.tna, self.tea, self.cft]
        if any(r is not None for r in rates) and (any(r is None for r in rates) or self.rate_kind is None):
            raise ValueError("Si informás una tasa tenés que informar TNA, TEA y CFT, y si es fija o variable")
        if self.rate_kind is not None and self.tna is None:
            raise ValueError("Indicá las tasas o dejá vacío el tipo de tasa")
        if self.tna is not None and (self.tea < self.tna or self.cft < self.tna):
            raise ValueError("La TEA y el CFT no pueden ser menores que la TNA")
        if self.valid_until < (self.valid_from or date.today()):
            raise ValueError("La vigencia tiene que terminar después de empezar")
        if self.type != "dealer_financing" and self.entity_id is None:
            raise ValueError("Elegí la entidad que financia")
        return self


OFFER_FIELDS = ("entity_id", "type", "title", "currency", "min_down_payment_pct", "min_down_payment_amount", "max_financed_pct", "max_financed_amount",
                "terms_months", "tna", "tea", "cft", "rate_kind", "applies_to_condition", "max_vehicle_age_years", "applies_to_all",
                "valid_from", "valid_until", "conditions", "source", "source_url")
OFFER_CASTS = {"type": "app.financing_type", "currency": "app.currency_code", "rate_kind": "app.rate_kind",
               "applies_to_condition": "app.vehicle_condition", "terms_months": "smallint[]"}


def _offer_values(body: OfferIn) -> dict:
    d = body.model_dump()
    d["valid_from"] = d["valid_from"] or date.today()
    return d


def _insert_offer(conn, d: dict, agency_id: UUID | None, user_id) -> UUID:
    cols = ", ".join(OFFER_FIELDS)
    vals = ", ".join(f"CAST(:{k} AS {OFFER_CASTS[k]})" if k in OFFER_CASTS else f":{k}" for k in OFFER_FIELDS)
    return scalar(conn, f"INSERT INTO app.financing_offers (agency_id, created_by, {cols}) VALUES (:agency_id, :u, {vals}) RETURNING id",
                  {**d, "agency_id": agency_id, "u": user_id})


def _update_offer(conn, offer_id: UUID, d: dict) -> None:
    sets = ", ".join(f"{k} = CAST(:{k} AS {OFFER_CASTS[k]})" if k in OFFER_CASTS else f"{k} = :{k}" for k in OFFER_FIELDS)
    conn.execute(text(f"UPDATE app.financing_offers SET {sets} WHERE id = :id"), {**d, "id": offer_id})


@router.get("/me/agencies/{agency_id}/financing-offers")
def my_offers(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
            raise err(404, "NO_ENCONTRADA", "La agencia no existe o no sos miembro.")
        return {"items": rows(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.agency_id = :a ORDER BY o.created_at DESC", {"a": agency_id}),
                "girando_offers": rows(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.agency_id IS NULL AND o.status = 'approved' ORDER BY o.valid_until DESC")}


@router.post("/me/agencies/{agency_id}/financing-offers", status_code=201)
def create_offer(agency_id: UUID, body: OfferIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx, reason="Alta de oferta de financiación") as conn:
        if not scalar(conn, "SELECT app.app_is_agency_member(:a, 'owner', 'admin')", {"a": agency_id}):
            raise err(403, "NO_AUTORIZADO", "Solo el titular o un administrador de la agencia carga ofertas de financiación.")
        oid = _insert_offer(conn, _offer_values(body), agency_id, user.id)
        return row(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.id = :o", {"o": oid})


@router.patch("/me/financing-offers/{offer_id}")
def update_offer(offer_id: UUID, body: OfferIn, user: CurrentUser = Depends(current_user)):
    """Editar una oferta aprobada la devuelve a revisión (lo hace la base)."""
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx, reason="Edición de oferta de financiación") as conn:
        if not scalar(conn, "SELECT 1 FROM app.financing_offers WHERE id = :o AND agency_id IS NOT NULL", {"o": offer_id}):
            raise err(404, "NO_ENCONTRADA", "Oferta inexistente.")
        _update_offer(conn, offer_id, _offer_values(body))
        return row(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.id = :o", {"o": offer_id})


OFFER_MOVES = {"submit": "pending", "withdraw": "draft", "pause": "paused"}


@router.post("/me/financing-offers/{offer_id}/{action}")
def offer_action(offer_id: UUID, action: Literal["submit", "withdraw", "pause"], user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx, reason=f"Oferta de financiación: {action}") as conn:
        if not scalar(conn, "SELECT 1 FROM app.financing_offers WHERE id = :o", {"o": offer_id}):
            raise err(404, "NO_ENCONTRADA", "Oferta inexistente.")
        conn.execute(text("UPDATE app.financing_offers SET status = CAST(:s AS app.financing_offer_status) WHERE id = :o"),
                     {"s": OFFER_MOVES[action], "o": offer_id})
        return row(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.id = :o", {"o": offer_id})


class ListingOffersIn(StrictModel):
    offer_ids: Annotated[list[UUID], Field(max_length=10)]


@router.put("/me/listings/{listing_id}/financing-offers")
def set_listing_offers(listing_id: UUID, body: ListingOffersIn, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx, reason="Ofertas de financiación de la publicación") as conn:
        if not scalar(conn, "SELECT app.can_manage_listing_id(:l)", {"l": listing_id}):
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no es tuya.")
        conn.execute(text("DELETE FROM app.listing_financing_offers WHERE listing_id = :l AND NOT (offer_id = ANY(CAST(:ids AS uuid[])))"),
                     {"l": listing_id, "ids": [str(i) for i in body.offer_ids]})
        for oid in body.offer_ids:
            conn.execute(text("INSERT INTO app.listing_financing_offers (listing_id, offer_id) VALUES (:l, :o) ON CONFLICT DO NOTHING"),
                         {"l": listing_id, "o": oid})
        if body.offer_ids:
            conn.execute(text("UPDATE app.listings SET is_financeable = true WHERE id = :l AND NOT is_financeable"), {"l": listing_id})
        return {"offer_ids": [r["offer_id"] for r in rows(conn, "SELECT offer_id FROM app.listing_financing_offers WHERE listing_id = :l", {"l": listing_id})]}


# --------------------------------------------------------------------------- financiación: admin / moderación
class EntityIn(StrictModel):
    name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    slug: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,60}$")]
    kind: Literal["bank", "finance_company", "automaker", "savings_plan_admin", "other"] = "bank"
    website_url: Annotated[str, StringConstraints(max_length=300, pattern=r"^https://\S+$")] | None = None
    logo_authorized: bool = False
    logo_public_id: Annotated[str, StringConstraints(max_length=300)] | None = None
    logo_authorization_note: Annotated[str, StringConstraints(max_length=500)] | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _logo(self):
        if self.logo_public_id and not self.logo_authorized:
            raise ValueError("El logo solo se carga si la entidad autorizó el uso de su marca")
        if self.logo_authorized and not (self.logo_authorization_note or "").strip():
            raise ValueError("Anotá quién autorizó el uso del logo y cuándo")
        return self


ENTITY_COLS = "id, slug, name, kind::text AS kind, website_url, logo_authorized, logo_public_id, logo_authorization_note, is_active, created_at"


@router.get("/admin/financing-entities")
def admin_entities(user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, f"SELECT {ENTITY_COLS} FROM app.financing_entities ORDER BY name")}


@router.post("/admin/financing-entities", status_code=201)
def admin_create_entity(body: EntityIn, user: CurrentUser = Depends(ADMIN)):
    with unit_of_work("app", user.id, user.ctx, reason="Alta de entidad de financiación") as conn:
        eid = scalar(conn, """INSERT INTO app.financing_entities (slug, name, kind, website_url, logo_authorized, logo_public_id, logo_authorization_note, is_active, created_by)
                              VALUES (:slug, :name, CAST(:kind AS app.financing_entity_kind), :website_url, :logo_authorized, :logo_public_id,
                                      :logo_authorization_note, :is_active, :u) RETURNING id""", {**body.model_dump(), "u": user.id})
        return row(conn, f"SELECT {ENTITY_COLS} FROM app.financing_entities WHERE id = :e", {"e": eid})


@router.put("/admin/financing-entities/{entity_id}")
def admin_update_entity(entity_id: UUID, body: EntityIn, user: CurrentUser = Depends(ADMIN)):
    with unit_of_work("app", user.id, user.ctx, reason="Edición de entidad de financiación") as conn:
        n = conn.execute(text("""UPDATE app.financing_entities SET slug = :slug, name = :name, kind = CAST(:kind AS app.financing_entity_kind),
                                   website_url = :website_url, logo_authorized = :logo_authorized, logo_public_id = :logo_public_id,
                                   logo_authorization_note = :logo_authorization_note, is_active = :is_active WHERE id = :e"""),
                         {**body.model_dump(), "e": entity_id}).rowcount
        if not n:
            raise err(404, "NO_ENCONTRADA", "Entidad inexistente.")
        return row(conn, f"SELECT {ENTITY_COLS} FROM app.financing_entities WHERE id = :e", {"e": entity_id})


@router.get("/admin/financing-offers")
def admin_offers(status: Literal["draft", "pending", "approved", "rejected", "paused"] | None = "pending", user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, f"""SELECT {OFFER_COLS}, a.trade_name AS agency_name {OFFER_FROM}
                                        WHERE CAST(:s AS text) IS NULL OR o.status::text = :s ORDER BY o.created_at LIMIT 200""", {"s": status})}


@router.post("/admin/financing-offers", status_code=201)
def admin_create_offer(body: OfferIn, user: CurrentUser = Depends(ADMIN)):
    """Oferta cargada por Girando (convenio). Igual pasa por Moderación antes de mostrarse."""
    if body.applies_to_all:
        raise err(422, "DATO_INVALIDO", "Una oferta de Girando se asocia publicación por publicación.")
    with unit_of_work("app", user.id, user.ctx, reason="Oferta de financiación de Girando (convenio)") as conn:
        oid = _insert_offer(conn, _offer_values(body), None, user.id)
        conn.execute(text("UPDATE app.financing_offers SET status = 'pending' WHERE id = :o"), {"o": oid})
        return row(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.id = :o", {"o": oid})


class ReviewIn(StrictModel):
    reason: Annotated[str, StringConstraints(min_length=3, max_length=500)] | None = None


@router.post("/admin/financing-offers/{offer_id}/{action}")
def admin_review_offer(offer_id: UUID, action: Literal["approve", "reject"], body: ReviewIn, user: CurrentUser = Depends(MOD)):
    if action == "reject" and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    with unit_of_work("app", user.id, user.ctx, reason=body.reason or "Oferta de financiación aprobada") as conn:
        o = row(conn, "SELECT id, created_by, title FROM app.financing_offers WHERE id = :o", {"o": offer_id})
        if not o:
            raise err(404, "NO_ENCONTRADA", "Oferta inexistente.")
        conn.execute(text("UPDATE app.financing_offers SET status = CAST(:s AS app.financing_offer_status), status_reason = :r WHERE id = :o"),
                     {"s": "approved" if action == "approve" else "rejected", "r": clean_text(body.reason), "o": offer_id})
        conn.execute(text("SELECT app.enqueue_notification(:u, 'financing.reviewed', :t, :b, 'financing_offer', :o, '/mi-agencia')"),
                     {"u": o["created_by"], "o": offer_id, "b": o["title"],
                      "t": "Tu oferta de financiación fue aprobada" if action == "approve" else "Tu oferta de financiación fue rechazada"})
        return row(conn, f"SELECT {OFFER_COLS} {OFFER_FROM} WHERE o.id = :o", {"o": offer_id})


# --------------------------------------------------------------------------- consentimiento de cookies
class CookieConsentIn(StrictModel):
    analytics: bool


def _anon_id(request: Request) -> UUID | None:
    try:
        return UUID(request.cookies.get(ANON_COOKIE, ""))
    except ValueError:
        return None


def analytics_allowed(request: Request, user: CurrentUser | None) -> tuple[bool, UUID | None]:
    """¿Hay consentimiento de analítica vigente? Devuelve (permitido, id anónimo). Lo decide la base."""
    aid = _anon_id(request)
    if not user and not aid:
        return False, None
    with unit_of_work("worker", None, request_ctx(request)) as conn:
        ok = bool(scalar(conn, "SELECT app.has_analytics_consent(:u, :a)", {"u": user.id if user else None, "a": aid}))
    return ok, aid


@router.get("/consents/cookies")
def get_cookie_consent(request: Request, user: CurrentUser | None = Depends(optional_user)):
    aid = _anon_id(request)
    if not user and not aid:
        return {"decided": False, "analytics": False}
    with unit_of_work("worker", None, request_ctx(request)) as conn:
        c = row(conn, """SELECT state::text AS state, coalesce(analytics, false) AS analytics, created_at FROM app.consents
                          WHERE consent_type = 'cookies' AND superseded_at IS NULL
                            AND ((CAST(:u AS uuid) IS NOT NULL AND user_id = :u) OR (CAST(:u AS uuid) IS NULL AND anonymous_id = :a AND user_id IS NULL))
                          ORDER BY created_at DESC LIMIT 1""", {"u": user.id if user else None, "a": aid})
    return {"decided": bool(c), "analytics": bool(c and c["state"] == "granted" and c["analytics"]), "decided_at": c["created_at"] if c else None}


@router.post("/consents/cookies")
def set_cookie_consent(body: CookieConsentIn, request: Request, response: Response, user: CurrentUser | None = Depends(optional_user)):
    """Ley 25.326: la analítica propia es opcional y se puede retirar. Las cookies necesarias no requieren consentimiento."""
    ratelimit.hit(ratelimit.GLOBAL_IP, client_ip(request))
    aid = _anon_id(request) or uuid.uuid4()
    ctx = request_ctx(request)
    with unit_of_work("worker", None, ctx, reason="Consentimiento de cookies") as conn:
        pv = scalar(conn, "SELECT id FROM app.policy_versions WHERE doc_type = 'cookies_policy' ORDER BY published_at DESC NULLS LAST LIMIT 1")
        if not pv:
            raise err(503, "POLITICA_NO_PUBLICADA", "Todavía no hay una política de cookies publicada.")
        conn.execute(text("""INSERT INTO app.consents (user_id, anonymous_id, consent_type, policy_version_id, state, necessary, preferences, analytics, marketing, channel, user_agent)
                             VALUES (:u, :a, 'cookies', :pv, 'granted', true, false, :an, false, 'web', :ua)"""),
                     {"u": user.id if user else None, "a": aid, "pv": pv, "an": body.analytics, "ua": (ctx.user_agent or "")[:300]})
    s = get_settings()
    response.set_cookie(ANON_COOKIE, str(aid), max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax", secure=s.cookie_secure, path="/")
    return {"decided": True, "analytics": body.analytics}


# --------------------------------------------------------------------------- eventos de publicidad y recomendaciones
class EventIn(StrictModel):
    name: Literal["promotion_impression", "promotion_click", "reco_impression", "reco_click"]
    promotion_id: UUID | None = None
    listing_code: Annotated[str, StringConstraints(max_length=16)] | None = None
    placement: Annotated[str, StringConstraints(max_length=40, pattern=r"^[a-z_]+$")] | None = None
    vertical: Literal["vehicles", "taxis", "services", "parts", "jobs"] | None = None
    page: Literal["home", "search", "detail"] | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.name.startswith("promotion_") and not self.promotion_id:
            raise ValueError("Falta la promoción")
        return self


class EventsIn(StrictModel):
    events: Annotated[list[EventIn], Field(min_length=1, max_length=20)]


def record_events(request: Request, user: CurrentUser | None, events: list[EventIn]) -> int:
    allowed, aid = analytics_allowed(request, user)
    n = 0
    with unit_of_work("worker", None, request_ctx(request)) as conn:
        for e in events:
            lid = scalar(conn, "SELECT id FROM api_public.listings WHERE public_code = :c", {"c": e.listing_code}) if e.listing_code else None
            if e.promotion_id and not scalar(conn, "SELECT 1 FROM api_public.sponsored WHERE promotion_id = :p", {"p": e.promotion_id}):
                continue  # solo se miden promociones activas: nada de inflar campañas terminadas o inexistentes
            # Sin consentimiento el evento se cuenta (dato agregado para el anunciante) pero sin ningún identificador
            conn.execute(text("""INSERT INTO app.analytics_events (event_name, user_id, anonymous_id, platform, listing_id, promotion_id, properties, consent_analytics)
                                 VALUES (CAST(:e AS app.analytics_event_name), :u, :a, 'web', :l, :p, CAST(:props AS jsonb), :c)"""),
                         {"e": e.name, "u": user.id if (user and allowed) else None, "a": aid if allowed else None, "l": lid, "p": e.promotion_id,
                          "props": json.dumps({k: v for k, v in (("placement", e.placement), ("vertical", e.vertical), ("page", e.page)) if v}), "c": allowed})
            n += 1
    return n


@router.post("/events", status_code=202)
def ingest_events(body: EventsIn, request: Request, user: CurrentUser | None = Depends(optional_user)):
    """Impresiones y clics de espacios publicitarios y de recomendaciones, emitidos por la App."""
    ratelimit.hit(ratelimit.GLOBAL_IP, client_ip(request))
    return {"accepted": record_events(request, user, body.events)}


@router.get("/out/ad/{promotion_id}")
def ad_click(promotion_id: UUID, request: Request, user: CurrentUser | None = Depends(optional_user)):
    """Clic en un banner: registra el clic y redirige al enlace https del anunciante (definido por el Super Admin)."""
    ratelimit.hit(ratelimit.OUTBOUND_IP, client_ip(request))
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        url = scalar(conn, "SELECT link_url FROM api_public.sponsored WHERE promotion_id = :p AND link_url IS NOT NULL", {"p": promotion_id})
    if not url:
        raise err(404, "NO_ENCONTRADA", "El anuncio ya no está disponible.")
    record_events(request, user, [EventIn(name="promotion_click", promotion_id=promotion_id)])
    return RedirectResponse(url, status_code=302)


@router.get("/ads")
def ads(request: Request, vertical: Literal["vehicles", "taxis", "services", "parts", "jobs"] = "vehicles",
        page: Literal["home", "search", "detail"] = "home"):
    """Espacios publicitarios de una página. Siempre con su rótulo (Publicidad / Patrocinado)."""
    placements = {"home": ["home_banner", "home_featured", "vertical_top"], "search": ["search_top", "search_inline", "search_brand_model", "vertical_top"],
                  "detail": ["detail_sidebar"]}[page]
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        items = rows(conn, """SELECT s.promotion_id, s.type::text AS type, s.placement::text AS placement, s.disclosure_label, s.advertiser_name,
                                     s.creative_public_id, (s.link_url IS NOT NULL) AS has_link,
                                     l.public_code, l.title, l.price_amount, l.currency::text AS currency, l.year, l.km, l.brand, l.model, l.cover_url, l.locality
                                FROM api_public.sponsored s LEFT JOIN api_public.listings l ON l.id = s.listing_id
                               WHERE s.placement::text = ANY(CAST(:pl AS text[])) AND (s.target_vertical IS NULL OR s.target_vertical = :v)
                               ORDER BY s.priority DESC, s.ends_at LIMIT 12""", {"pl": placements, "v": vertical})
    for i in items:
        i["click_url"] = f"/api/out/ad/{i['promotion_id']}" if i.pop("has_link") else None
    return {"items": items}


# --------------------------------------------------------------------------- similares y recomendaciones (reglas explicables)
REASONS = (("same_model", "Mismo modelo"), ("same_body", "Misma carrocería"), ("near_price", "Precio parecido"),
           ("same_zone", "Misma zona"), ("same_brand", "Misma marca"))
SCORED = f"""SELECT {search_service.PUBLIC_COLS},
       (model_id = CAST(:model AS uuid)) AS same_model, (brand_id = CAST(:brand AS uuid)) AS same_brand,
       (body_type::text = :body) AS same_body, (province = :prov) AS same_zone,
       (CAST(:price AS numeric) IS NOT NULL AND coalesce(price_ars, CASE WHEN currency::text = :cur THEN price_amount END)
          BETWEEN CAST(:price AS numeric) * 0.75 AND CAST(:price AS numeric) * 1.25) AS near_price
  FROM api_public.listings"""


def _with_reasons(items: list[dict]) -> list[dict]:
    for i in items:
        i["reasons"] = [label for key, label in REASONS if i.pop(key, None)]
        i.pop("score", None)
    return items


def _ranked(conn, ref: dict, exclude: list, limit: int) -> list[dict]:
    """Puntaje transparente: modelo 4, carrocería 2, precio ±25 % 2, zona 1, marca 1."""
    p = {"model": ref.get("model_id"), "brand": ref.get("brand_id"), "body": ref.get("body_type"), "prov": ref.get("province"),
         "price": ref.get("price"), "cur": ref.get("currency") or "ARS", "ex": [str(x) for x in exclude], "lim": limit}
    return rows(conn, f"""SELECT * FROM (SELECT x.*, (coalesce(same_model, false)::int * 4 + coalesce(same_body, false)::int * 2 + coalesce(near_price, false)::int * 2
                                                     + coalesce(same_zone, false)::int + coalesce(same_brand, false)::int) AS score
                                          FROM ({SCORED} WHERE NOT (id = ANY(CAST(:ex AS uuid[])))) x) y
                          WHERE score > 0 ORDER BY score DESC, published_at DESC LIMIT :lim""", p)


@router.get("/listings/{code}/similar")
def similar(code: str, request: Request, limit: Annotated[int, Query(ge=1, le=12)] = 8):
    """"Similares": solo contexto de la publicación (no usa datos del visitante, no requiere consentimiento)."""
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        d = row(conn, """SELECT id, model_id, brand_id, body_type::text AS body_type, province, currency::text AS currency,
                                coalesce(price_ars, price_amount) AS price FROM api_public.listings WHERE public_code = :c OR id::text = :c""", {"c": code[:64]})
        if not d:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o ya no está disponible.")
        return {"basis": "contexto", "items": _with_reasons(_ranked(conn, d, [d["id"]], limit))}


@router.get("/recommendations")
def recommendations(request: Request, user: CurrentUser | None = Depends(optional_user), limit: Annotated[int, Query(ge=1, le=12)] = 8,
                    brand_id: UUID | None = None, model_id: UUID | None = None, body_type: Annotated[str | None, Query(max_length=20)] = None,
                    price: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None, geo_area_id: UUID | None = None):
    """"Te puede interesar". Con consentimiento de analítica y sesión: según lo que el usuario guardó y vio EN GIRANDO.
    Sin consentimiento: solo por el contexto que manda la página (filtros actuales). Si no hay nada, lo más reciente."""
    allowed, _ = analytics_allowed(request, user)
    ref, exclude, basis = None, [], "contexto"
    if user and allowed:
        with unit_of_work("app", user.id, user.ctx) as conn:
            seen = rows(conn, """SELECT l.id, l.model_id, l.brand_id, l.body_type::text AS body_type, l.province, coalesce(l.price_ars, l.price_amount) AS price, w
                                   FROM (SELECT listing_id, 2 AS w, created_at AS at FROM app.favorites WHERE user_id = :u
                                         UNION ALL SELECT listing_id, 1, viewed_at FROM app.recently_viewed WHERE user_id = :u) s
                                   JOIN api_public.listings l ON l.id = s.listing_id ORDER BY s.at DESC LIMIT 30""", {"u": user.id})
        if seen:
            def top(key):
                tally: dict = {}
                for s in seen:
                    if s[key] is not None:
                        tally[s[key]] = tally.get(s[key], 0) + s["w"]
                return max(tally, key=tally.get) if tally else None
            prices = sorted(s["price"] for s in seen if s["price"] is not None)
            ref = {"model_id": top("model_id"), "brand_id": top("brand_id"), "body_type": top("body_type"), "province": top("province"),
                   "price": prices[len(prices) // 2] if prices else None}
            exclude, basis = [s["id"] for s in seen], "actividad"
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        if ref is None and any(v is not None for v in (brand_id, model_id, body_type, price, geo_area_id)):
            prov = scalar(conn, """SELECT coalesce(p.name, g.name) FROM api_public.geo_areas g LEFT JOIN api_public.geo_areas p ON p.id = g.parent_id AND g.level::text <> 'province'
                                   WHERE g.id = :g""", {"g": geo_area_id}) if geo_area_id else None
            ref = {"model_id": model_id, "brand_id": brand_id, "body_type": body_type, "province": prov, "price": price}
        items = _with_reasons(_ranked(conn, ref, exclude, limit)) if ref else []
        if not items:
            basis = "recientes"
            items = rows(conn, f"SELECT {search_service.PUBLIC_COLS} FROM api_public.listings ORDER BY published_at DESC LIMIT :l", {"l": limit})
            for i in items:
                i["reasons"] = ["Publicado hace poco"]
    return {"basis": basis, "personalized": basis == "actividad", "items": items}


# --------------------------------------------------------------------------- búsquedas guardadas
FILTER_KEYS = {"q", "brand_id", "model_id", "version_id", "year_min", "year_max", "price_min", "price_max", "currency", "km_min", "km_max", "vehicle_type",
               "fuel", "transmission", "body_type", "traction", "condition", "seller_type", "verified", "financeable", "geo_area_id", "radius_km", "color",
               "doors", "trade_in", "financing_entity_id", "down_payment_max", "installment_max", "sort"}


class SavedSearchIn(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    filters: dict
    notification_enabled: bool = True
    notify_frequency: Literal["instant", "daily", "weekly"] = "daily"

    @field_validator("filters")
    @classmethod
    def _f(cls, v):
        if set(v) - FILTER_KEYS or len(json.dumps(v)) > 2000:
            raise ValueError("Filtros no reconocidos")
        return v


SS_COLS = "id, name, filters, notification_enabled, notify_frequency, last_notified_at, created_at"


@router.get("/me/saved-searches")
def saved_searches(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, f"SELECT {SS_COLS} FROM app.saved_searches WHERE user_id = :u ORDER BY created_at DESC", {"u": user.id})}


def _one(v):
    return (v[0] if v else None) if isinstance(v, list) else v


@router.post("/me/saved-searches", status_code=201)
def create_saved_search(body: SavedSearchIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.FAVORITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        if scalar(conn, "SELECT count(*) FROM app.saved_searches WHERE user_id = :u", {"u": user.id}) >= 20:
            raise err(409, "LIMITE_ALCANZADO", "Podés guardar hasta 20 búsquedas.")
        f = body.filters
        sid = scalar(conn, """INSERT INTO app.saved_searches (user_id, name, filters, brand_id, model_id, geo_area_id, notification_enabled, notify_frequency,
                                                             last_seen_listing_published_at)
                              VALUES (:u, :n, CAST(:f AS jsonb), :b, :m, :g, :e, :fr, now()) RETURNING id""",
                     {"u": user.id, "n": clean_text(body.name), "f": json.dumps(f), "b": _one(f.get("brand_id")), "m": _one(f.get("model_id")),
                      "g": f.get("geo_area_id"), "e": body.notification_enabled, "fr": body.notify_frequency})
        return row(conn, f"SELECT {SS_COLS} FROM app.saved_searches WHERE id = :s", {"s": sid})


class SavedSearchPatch(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)] | None = None
    notification_enabled: bool | None = None
    notify_frequency: Literal["instant", "daily", "weekly"] | None = None


@router.patch("/me/saved-searches/{search_id}")
def update_saved_search(search_id: UUID, body: SavedSearchPatch, user: CurrentUser = Depends(current_user)):
    d = body.model_dump(exclude_none=True)
    with unit_of_work("app", user.id, user.ctx) as conn:
        if d:
            sets = ", ".join(f"{k} = :{k}" for k in d)
            conn.execute(text(f"UPDATE app.saved_searches SET {sets} WHERE id = :s AND user_id = :u"), {**d, "s": search_id, "u": user.id})
        r = row(conn, f"SELECT {SS_COLS} FROM app.saved_searches WHERE id = :s AND user_id = :u", {"s": search_id, "u": user.id})
        if not r:
            raise err(404, "NO_ENCONTRADA", "Búsqueda inexistente.")
        return r


@router.delete("/me/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        conn.execute(text("DELETE FROM app.saved_searches WHERE id = :s AND user_id = :u"), {"s": search_id, "u": user.id})
    return Response(status_code=204)


# --------------------------------------------------------------------------- historial del usuario
@router.get("/me/history")
def history(user: CurrentUser = Depends(current_user)):
    """Vistos recientemente, pagos y cambios de plan del usuario y de sus cuentas comerciales."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        viewed = rows(conn, f"""SELECT {search_service.PUBLIC_COLS.replace("listings.id", "l.id")}, r.viewed_at
                                 FROM app.recently_viewed r JOIN api_public.listings l ON l.id = r.listing_id
                                WHERE r.user_id = :u ORDER BY r.viewed_at DESC LIMIT 50""", {"u": user.id})
        payments = rows(conn, """SELECT py.id, py.purpose::text AS purpose, py.status::text AS status, py.provider::text AS provider, py.amount,
                                        py.currency::text AS currency, py.paid_at, py.created_at, a.trade_name AS account,
                                        coalesce(np.name, p.name, pp.name, 'Promoción') AS concept, (py.plan_change_to IS NOT NULL) AS is_plan_change
                                   FROM app.payments py
                                   LEFT JOIN app.subscriptions s ON s.id = py.subscription_id LEFT JOIN app.plans p ON p.id = s.plan_id
                                   LEFT JOIN app.plans np ON np.id = py.plan_change_to
                                   LEFT JOIN app.promotions pr ON pr.id = py.promotion_id LEFT JOIN app.promotion_products pp ON pp.id = pr.product_id
                                   LEFT JOIN app.agencies a ON a.id = py.agency_id
                                  WHERE py.payer_user_id = :u OR (py.agency_id IS NOT NULL AND app.app_is_agency_member(py.agency_id, 'owner', 'admin'))
                                  ORDER BY py.created_at DESC LIMIT 100""", {"u": user.id})
        plans = rows(conn, """SELECT s.id, p.name AS plan, s.status::text AS status, s.provider::text AS provider, s.started_at, s.current_period_end,
                                     s.ended_at, s.created_at, a.trade_name AS account, pp.name AS pending_plan
                                FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.plans pp ON pp.id = s.pending_plan_id
                                LEFT JOIN app.agencies a ON a.id = s.agency_id
                               WHERE s.user_id = :u OR (s.agency_id IS NOT NULL AND app.app_is_agency_member(s.agency_id, 'owner', 'admin'))
                               ORDER BY s.created_at DESC LIMIT 50""", {"u": user.id})
        return {"recently_viewed": viewed, "payments": payments, "plan_changes": plans}


@router.delete("/me/history/viewed", status_code=204)
def clear_viewed(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        conn.execute(text("DELETE FROM app.recently_viewed WHERE user_id = :u"), {"u": user.id})
    return Response(status_code=204)


def touch_viewed(user: CurrentUser, listing_id) -> None:
    try:
        with unit_of_work("app", user.id, user.ctx) as conn:
            conn.execute(text("SELECT app.touch_recently_viewed(:l)"), {"l": listing_id})
    except Exception:  # noqa: BLE001 — el historial nunca rompe el detalle
        pass
