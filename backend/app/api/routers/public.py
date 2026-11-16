"""Endpoints públicos (sin sesión): catálogo, ubicaciones, búsqueda, detalle, agencias, perfiles, planes.

Todo sale de vistas api_public.* con rol girando_anon: es imposible devolver una
columna privada desde acá porque ese rol no tiene permiso sobre las tablas.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import StringConstraints, field_validator

from app.api.deps import CurrentUser, current_user, optional_user, request_ctx
from app.core import ratelimit
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.core.middleware import client_ip
from app.schemas.common import StrictModel, clean_text
from app.schemas.listings import ColorFamily
from app.services import search_service
from app.services.analytics import track

router = APIRouter(prefix="/api", tags=["público"])

VehicleType = Literal["car", "light_truck", "van", "truck", "motorcycle", "atv", "other"]
# Carrocerías (etiquetas en el frontend): Hatchback, Sedán, SUV, Crossover, Pick-Up, Rural (wagon), Coupé, Cabriolet (convertible),
# Roadster, Monovolumen (mpv), Minivan, Furgón (panel_van), Van, Light Truck, Off-Road. 'chassis' quedó migrado a light_truck.
BodyType = Literal["hatchback", "sedan", "suv", "crossover", "pickup", "wagon", "coupe", "convertible", "roadster", "mpv", "minivan",
                   "panel_van", "van", "light_truck", "off_road", "motorcycle", "other"]


@router.get("/catalog/brands")
def brands(request: Request, vehicle_type: VehicleType | None = None):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT DISTINCT brand_id AS id, brand AS name FROM api_public.catalog_versions
                                         WHERE CAST(:vt AS text) IS NULL OR vehicle_type::text = :vt ORDER BY name""", {"vt": vehicle_type})}


@router.get("/catalog/brands/{brand_id}/models")
def models(brand_id: UUID, request: Request, vehicle_type: VehicleType | None = None):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT DISTINCT model_id AS id, model AS name, vehicle_type::text AS vehicle_type
                                         FROM api_public.catalog_versions WHERE brand_id = :b
                                          AND (CAST(:vt AS text) IS NULL OR vehicle_type::text = :vt) ORDER BY name""",
                                     {"b": brand_id, "vt": vehicle_type})}


@router.get("/catalog/models/{model_id}/generations")
def generations(model_id: UUID, request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT DISTINCT generation_id AS id, generation AS name,
                                              min(year_from) OVER (PARTITION BY generation_id) AS year_from,
                                              max(coalesce(year_to, 2100)) OVER (PARTITION BY generation_id) AS year_to_raw
                                         FROM api_public.catalog_versions WHERE model_id = :m ORDER BY name""", {"m": model_id})}


@router.get("/catalog/generations/{generation_id}/versions")
def versions(generation_id: UUID, request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT version_id AS id, version AS name, body_type::text AS body_type, doors, seats,
                                              transmission::text AS transmission, gears, traction::text AS traction,
                                              year_from, year_to, engines
                                         FROM api_public.catalog_versions WHERE generation_id = :g ORDER BY version""", {"g": generation_id})}


GEO_PATH = """SELECT g.id, g.name, g.level::text AS level, g.parent_id,
       CASE g.level::text WHEN 'locality' THEN d.name WHEN 'department' THEN NULL END AS department,
       CASE g.level::text WHEN 'locality' THEN pr.name WHEN 'department' THEN d.name END AS province,
       CASE g.level::text WHEN 'locality' THEN d.id END AS department_id,
       CASE g.level::text WHEN 'locality' THEN pr.id WHEN 'department' THEN d.id END AS province_id
  FROM api_public.geo_areas g
  LEFT JOIN api_public.geo_areas d ON d.id = g.parent_id
  LEFT JOIN api_public.geo_areas pr ON pr.id = d.parent_id"""


@router.get("/geo")
def geo(request: Request, parent_id: UUID | None = None, level: Literal["province", "department", "locality"] | None = None,
        q: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
        limit: Annotated[int | None, Query(ge=1, le=500)] = None, offset: Annotated[int, Query(ge=0, le=20000)] = 0):
    """Ubicaciones de todo el país (Georef). Siempre paginado: nunca devuelve las 4.028 localidades de una vez.

    · `parent_id`: hijos de una provincia o departamento (hasta 500 por página).
    · `level` sin `parent_id`: provincias completas; departamentos y localidades de a 50 como máximo.
    · `q`: búsqueda por nombre sin tildes ni mayúsculas (primero los que empiezan con el texto), con provincia y departamento
      de cada resultado para desambiguar ("San Martín" existe en varias provincias)."""
    lvl = level or (None if (parent_id or q) else "province")
    wide = bool(parent_id) or lvl == "province"
    cap = 500 if wide else 50
    lim = min(limit or (500 if wide else 20), cap)
    where, p = ["true"], {"lim": lim, "off": offset}
    if parent_id:
        where.append("g.parent_id = :parent")
        p["parent"] = parent_id
    if lvl:
        where.append("g.level::text = :lvl")
        p["lvl"] = lvl
    else:
        where.append("g.level::text IN ('province', 'department', 'locality')")
    order = "g.name, g.id"
    if q:
        p["q"] = search_service._norm(q).strip()
        where.append("lower(app.f_unaccent(g.name)) LIKE '%' || :q || '%'")
        order = "(lower(app.f_unaccent(g.name)) LIKE :q || '%') DESC, (g.level::text = 'province') DESC, (g.level::text = 'department') DESC, g.name, g.id"
    w = " AND ".join(where)
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        total = scalar(conn, f"SELECT count(*) FROM api_public.geo_areas g WHERE {w}", p)   # w: fragmentos constantes + parámetros ligados
        items = rows(conn, f"{GEO_PATH} WHERE {w} ORDER BY {order} LIMIT :lim OFFSET :off", p)
    return {"items": items, "total": total, "limit": lim, "offset": offset, "has_more": offset + len(items) < total}


@router.get("/geo/{area_id}")
def geo_one(area_id: UUID, request: Request):
    """Una ubicación con su provincia y departamento: sirve para reconstruir el selector desde una URL compartida."""
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        g = row(conn, f"{GEO_PATH} WHERE g.id = :i", {"i": area_id})
    if not g:
        raise err(404, "NO_ENCONTRADA", "Esa ubicación no existe.")
    return g


def _filters(
    q: Annotated[str | None, Query(max_length=100)] = None,
    brand_id: Annotated[list[UUID] | None, Query()] = None,
    model_id: Annotated[list[UUID] | None, Query()] = None,
    year_min: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    year_max: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    price_min: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    currency: Literal["ARS", "USD"] | None = None,
    km_min: Annotated[int | None, Query(ge=0, le=2_000_000)] = None,
    km_max: Annotated[int | None, Query(ge=0, le=2_000_000)] = None,
    vehicle_type: Annotated[list[VehicleType] | None, Query()] = None,
    fuel: Annotated[list[Literal["gasoline", "diesel", "cng", "gasoline_cng", "hybrid", "plugin_hybrid", "electric", "other"]] | None, Query()] = None,
    transmission: Annotated[list[Literal["manual", "automatic", "cvt", "automated_manual", "other"]] | None, Query()] = None,
    body_type: Annotated[list[BodyType] | None, Query()] = None,
    traction: Annotated[list[Literal["front", "rear", "4x2", "4x4", "awd"]] | None, Query()] = None,
    condition: Annotated[list[Literal["new", "used"]] | None, Query()] = None,
    seller_type: Annotated[list[Literal["particular", "agency", "official_dealer"]] | None, Query()] = None,
    verified: bool = False,
    financeable: bool = False,
    geo_area_id: UUID | None = None,
    agency_id: UUID | None = None,
    # ---- fase 4
    version_id: Annotated[list[UUID] | None, Query()] = None,
    color: Annotated[list[ColorFamily] | None, Query()] = None,
    doors: Annotated[list[Annotated[int, Query(ge=2, le=6)]] | None, Query()] = None,
    trade_in: bool = False,
    financing_entity_id: Annotated[list[UUID] | None, Query()] = None,
    down_payment_max: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    installment_max: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    radius_km: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> dict:
    return {k: v for k, v in locals().items()}


@router.get("/listings")
def search(request: Request, f: dict = Depends(_filters), page: Annotated[int, Query(ge=1, le=500)] = 1,
           page_size: Annotated[int, Query(ge=1, le=48)] = 24,
           sort: Literal["relevancia", "recientes", "precio_asc", "precio_desc", "km_asc", "km_desc", "anio_desc", "anio_asc"] = "relevancia"):
    ratelimit.hit(ratelimit.SEARCH_IP, client_ip(request))
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return search_service.search(conn, f, page, page_size, sort)


@router.get("/listings/facets")
def search_facets(request: Request, f: dict = Depends(_filters)):
    ratelimit.hit(ratelimit.SEARCH_IP, client_ip(request))
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return search_service.facets(conn, f)


@router.get("/listings/{code}")
def listing_detail(code: str, request: Request, user: CurrentUser | None = Depends(optional_user)):
    ctx = request_ctx(request)
    with unit_of_work("anon", None, ctx) as conn:
        d = row(conn, f"""SELECT {search_service.PUBLIC_COLS}, description, video_url, seats, gears, displacement_cc, power_hp,
                                 neighborhood, centroid_lat, centroid_lng, first_published_at, images, seller_display_name
                            FROM api_public.listings WHERE public_code = :c OR id::text = :c""", {"c": code[:64]})
        if not d:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o ya no está disponible.")
        d["images"] = d["images"] or []
        if d["agency_id"]:
            d["agency"] = row(conn, """SELECT id, slug, trade_name, kind::text AS kind, is_verified, member_since, locality, street, street_number,
                                              girando_rating, girando_review_count, google_rating, google_review_count, google_url, google_synced_at
                                         FROM api_public.agencies WHERE id = :a""", {"a": d["agency_id"]})
            d["seller_active_listings"] = scalar(conn, "SELECT count(*) FROM api_public.listings WHERE agency_id = :a", {"a": d["agency_id"]})
            d["seller"] = None
        else:
            d["agency"] = None
    if not d["agency_id"]:
        # Datos públicos del particular (solo si su perfil es público). El id del dueño se resuelve
        # con rol de sistema y NO se devuelve si el perfil no es público.
        with unit_of_work("worker", None, ctx) as wconn:
            owner_id = scalar(wconn, "SELECT owner_user_id FROM app.listings WHERE id = :id", {"id": d["id"]})
        with unit_of_work("anon", None, ctx) as conn:
            d["seller"] = row(conn, """SELECT user_id, display_name, identity_verified, member_since, locality, girando_rating, girando_review_count
                                         FROM api_public.user_profiles WHERE user_id = :u""", {"u": owner_id})
            d["seller_active_listings"] = None
    d["is_favorite"] = False
    if user:
        with unit_of_work("app", user.id, ctx) as conn:
            d["is_favorite"] = bool(scalar(conn, "SELECT 1 FROM app.favorites WHERE user_id = :u AND listing_id = :l", {"u": user.id, "l": d["id"]}))
            d["is_mine"] = bool(scalar(conn, "SELECT app.can_manage_listing_id(:l)", {"l": d["id"]}))
        from app.api.routers.marketplace import touch_viewed  # historial propio del usuario (no es analítica)
        touch_viewed(user, d["id"])
    d["whatsapp_url"] = f"/api/out/wa/{d['public_code']}"      # el número no viaja: lo resuelve el redirect
    track("listing_view", ctx, user.id if user else None, listing_id=d["id"], agency_id=d["agency_id"])
    return d


@router.get("/listings/{code}/market")
def listing_market(code: str, request: Request):
    """Precio vs mercado. Solo con muestra suficiente (market.min_sample_size); si no, `sufficient=false` y ningún número."""
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        lid = scalar(conn, "SELECT id FROM api_public.listings WHERE public_code = :c OR id::text = :c", {"c": code[:64]})
        if not lid:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o ya no está disponible.")
        m = row(conn, "SELECT * FROM app.market_price(:l)", {"l": lid}) or {"sample": 0, "sufficient": False}
    if not m.get("sufficient"):
        return {"sufficient": False, "sample": m.get("sample") or 0, "min_sample": m.get("min_sample"), "message": "Sin datos suficientes"}
    return {**m, "basis": "Publicaciones activas del mismo modelo y año ±1, en pesos (dólar BCRA)."}


@router.get("/listings/{code}/contact")
def listing_contact(code: str, request: Request, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.CONTACT_REVEAL_USER, str(user.id))
    with unit_of_work("anon", None, user.ctx) as conn:
        c = row(conn, """SELECT c.* FROM api_public.listing_contact c JOIN api_public.listings l ON l.id = c.listing_id
                          WHERE l.public_code = :c OR l.id::text = :c""", {"c": code[:64]})
    if not c:
        raise err(404, "NO_ENCONTRADA", "La publicación no está disponible.")
    track("listing_contact_reveal", user.ctx, user.id, listing_id=c["listing_id"])
    return c


@router.get("/agencies/{slug}")
def agency_public(slug: str, request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        a = row(conn, "SELECT * FROM api_public.agencies WHERE slug = :s", {"s": slug[:60]})
        if not a:
            raise err(404, "NO_ENCONTRADA", "La agencia no existe o no está disponible.")
        a["listings"] = rows(conn, f"SELECT {search_service.PUBLIC_COLS} FROM api_public.listings WHERE agency_id = :a ORDER BY published_at DESC LIMIT 48", {"a": a["id"]})
        a["reviews"] = rows(conn, "SELECT rating, comment, created_at, reviewer_display_name FROM api_public.reviews WHERE reviewed_agency_id = :a ORDER BY created_at DESC LIMIT 20", {"a": a["id"]})
    track("agency_view", request_ctx(request), agency_id=a["id"])
    return a


@router.get("/users/{user_id}/profile")
def user_public(user_id: UUID, request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        p = row(conn, "SELECT * FROM api_public.user_profiles WHERE user_id = :u", {"u": user_id})
        if not p:
            raise err(404, "NO_ENCONTRADO", "El perfil no es público.")
        p["reviews"] = rows(conn, "SELECT rating, comment, created_at, reviewer_display_name FROM api_public.reviews WHERE reviewed_user_id = :u ORDER BY created_at DESC LIMIT 20", {"u": user_id})
    return p


@router.get("/plans")
def plans(request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, "SELECT * FROM api_public.plans ORDER BY audience, sort_order, price_amount")}


@router.get("/settings")
def settings_public(request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {r["key"]: r["value"] for r in rows(conn, "SELECT key, value FROM api_public.settings")}


@router.get("/sponsored")
def sponsored(request: Request, placement: Literal["home_featured", "home_banner", "search_top", "search_brand_model", "agency_directory"] = "home_featured"):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        items = rows(conn, """SELECT s.promotion_id, s.type::text AS type, s.disclosure_label, s.advertiser_name, s.link_url,
                                      s.creative_public_id, l.public_code, l.title, l.price_amount, l.currency, l.year, l.km, l.brand, l.model, l.cover_url, l.locality
                                 FROM api_public.sponsored s LEFT JOIN api_public.listings l ON l.id = s.listing_id
                                WHERE s.placement::text = :p ORDER BY s.priority DESC LIMIT 12""", {"p": placement})
    return {"items": items}


@router.get("/report-reasons")
def report_reasons(request: Request, target: Literal["listing", "user", "agency", "message", "review", "post"] = "listing"):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"items": rows(conn, """SELECT id, code, label, requires_description FROM api_public.report_reasons
                                        WHERE CAST(:t AS app.report_target) = ANY(applies_to) ORDER BY sort_order""", {"t": target})}



class ReportIn(StrictModel):
    target: Literal["listing", "agency", "post"]
    code: Annotated[str, StringConstraints(min_length=3, max_length=64)]
    reason_id: UUID
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None

    @field_validator("description")
    @classmethod
    def _c(cls, v):
        return clean_text(v)


@router.post("/reports", status_code=201)
def create_report(body: ReportIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.REPORT_USER, str(user.id))
    with unit_of_work("anon", None, user.ctx) as conn:
        if body.target == "listing":
            tid = scalar(conn, "SELECT id FROM api_public.listings WHERE public_code = :c OR id::text = :c", {"c": body.code})
        elif body.target == "post":
            tid = scalar(conn, "SELECT id FROM api_public.posts WHERE public_code = :c", {"c": body.code})
        else:
            tid = scalar(conn, "SELECT id FROM api_public.agencies WHERE slug = :c", {"c": body.code})
    if not tid:
        raise err(404, "NO_ENCONTRADA", "No encontramos lo que querés reportar.")
    with unit_of_work("app", user.id, user.ctx) as conn:
        col = {"listing": "listing_id", "post": "post_id", "agency": "agency_id"}[body.target]   # lista blanca, nunca texto del usuario
        rid = scalar(conn, f"""INSERT INTO app.reports (reporter_user_id, target, {col}, reason_id, description)
                              VALUES (:u, CAST(:t AS app.report_target), :tid, :r, :d) RETURNING id""",
                     {"u": user.id, "t": body.target, "tid": tid, "r": body.reason_id, "d": body.description})
    return {"id": rid, "status": "pending"}


LEGAL = {"terminos": "terminos.html", "privacidad": "privacidad.html", "cookies": "cookies.html"}


@router.get("/legal/{doc}", include_in_schema=False)
def legal(doc: Literal["terminos", "privacidad", "cookies"]):
    from pathlib import Path

    from fastapi.responses import HTMLResponse
    html = (Path(__file__).resolve().parents[2] / "seeds" / "legal" / LEGAL[doc]).read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


# --------------------------------------------------------------------------- Home administrable (contenido propio de Girando)
@router.get("/home")
def home_content(request: Request):
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        return {"blocks": rows(conn, "SELECT id, kind::text AS kind, title, body, image_public_id, cta_label, cta_target FROM api_public.home_blocks ORDER BY kind, sort_order")}


# --------------------------------------------------------------------------- clics a canales externos de agencias
OUT_CHANNELS = Literal["website", "store", "instagram", "facebook", "tiktok", "youtube", "whatsapp"]
_CH_COL = {"website": "website_url", "store": "store_url", "instagram": "instagram_url", "facebook": "facebook_url",
           "tiktok": "tiktok_url", "youtube": "youtube_url", "whatsapp": "whatsapp_e164"}


@router.get("/out/agency/{slug}/{channel}", include_in_schema=True)
def outbound_agency(slug: Annotated[str, StringConstraints(max_length=60, pattern=r"^[a-z0-9-]+$")], channel: OUT_CHANNELS, request: Request,
                    listing: Annotated[str | None, Query(alias="l", max_length=12, pattern=r"^P-[A-Z0-9]{8}$")] = None):
    """Registra el clic (agencia, publicación si corresponde, canal, fecha) y redirige al destino guardado.
    Solo redirige a URLs cargadas por la agencia (no hay redirección abierta) y no guarda datos personales."""
    from fastapi.responses import RedirectResponse
    ratelimit.hit(ratelimit.OUTBOUND_IP, client_ip(request))
    ctx = request_ctx(request)
    with unit_of_work("anon", None, ctx) as conn:
        a = row(conn, f"SELECT id, {_CH_COL[channel]} AS target FROM api_public.agencies WHERE slug = :s", {"s": slug})
        if not a or not a["target"]:
            raise err(404, "NO_ENCONTRADO", "La agencia no tiene ese canal.")
        lid = scalar(conn, "SELECT id FROM api_public.listings WHERE public_code = :c AND agency_id = :a", {"c": listing, "a": a["id"]}) if listing else None
    target = a["target"]
    if channel == "whatsapp":
        target = "https://wa.me/" + "".join(ch for ch in target if ch.isdigit())
    if not target.startswith("https://"):
        raise err(404, "NO_ENCONTRADO", "Destino inválido.")
    # Sin user_id ni IP: solo el hecho del clic para las estadísticas de la agencia
    track("external_click", ctx.__class__(request_id=ctx.request_id), agency_id=a["id"], listing_id=lid, properties={"channel": channel})
    return RedirectResponse(target, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "origin"})


# --------------------------------------------------------------------------- WhatsApp: el contacto principal
_BOT_UA = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python-|httpx|go-http|java/|scrapy|headless|phantom|"
                     r"lighthouse|monitor|pingdom|uptime", re.I)
PublicCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]-[A-Z0-9]{8}$")]


def is_bot(user_agent: str | None) -> bool:
    return not user_agent or len(user_agent) < 20 or bool(_BOT_UA.search(user_agent))


@router.get("/out/wa/{code}", include_in_schema=True)
def outbound_whatsapp(code: PublicCode, request: Request):
    """Abre WhatsApp con el vendedor, sin iniciar sesión. El número no está en la página: se resuelve acá.

    · Mensaje precargado con el título y el código, para que quien vende sepa de dónde viene el contacto.
    · Límite por IP y filtro de bots (un bot no recibe el número ni cuenta como apertura).
    · Se registra SOLO el hecho de la apertura (publicación, fecha): ni usuario, ni IP, ni identificador de sesión."""
    from urllib.parse import quote

    from fastapi.responses import RedirectResponse
    ratelimit.hit(ratelimit.WHATSAPP_IP, client_ip(request))
    ctx = request_ctx(request)
    if is_bot(ctx.user_agent):
        raise err(403, "NO_DISPONIBLE", "Abrí WhatsApp desde la ficha de la publicación.")
    with unit_of_work("worker", None, ctx) as conn:
        t = row(conn, "SELECT * FROM app.whatsapp_target(:c)", {"c": code})
    if not t or not t["whatsapp"]:
        raise err(404, "NO_ENCONTRADA", "La publicación no está disponible o no tiene WhatsApp de contacto.")
    anon = ctx.__class__(request_id=ctx.request_id)        # sin IP ni user agent: nunca se guarda quién hizo clic
    if t["kind"] == "listing":
        track("listing_contact", anon, listing_id=t["entity_id"], agency_id=t["agency_id"], properties={"channel": "whatsapp"})
    else:
        track("post_contact", anon, agency_id=t["agency_id"], properties={"channel": "whatsapp", "vertical": t["vertical"], "post": str(t["entity_id"])})
    msg = f"Hola, vi tu {t['title'] or 'publicación'} en Girando ({t['public_code']})"
    url = "https://wa.me/" + "".join(ch for ch in t["whatsapp"] if ch.isdigit()) + "?text=" + quote(msg)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                                           "X-Robots-Tag": "noindex, nofollow"})
