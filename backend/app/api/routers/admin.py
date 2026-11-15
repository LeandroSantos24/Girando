"""/api/admin — Panel de administración. Consume la MISMA base que la App.

Permisos por rol de staff (tabla staff_roles, no el JWT). Toda acción queda en
audit_logs (trigger) y, si es de moderación, en moderation_actions con motivo.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field, StringConstraints, field_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, require_roles, staff_user
from app.core import ratelimit
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.schemas.common import StrictModel, clean_text


def _rl(user: CurrentUser = Depends(staff_user)) -> CurrentUser:
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    return user


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(_rl)])

# Matriz de permisos (ver docs/06-roles-y-permisos.md). "superadmin" pasa todas las validaciones.
#   Operación (Admin): moderación, usuarios, agencias, verificaciones, reportes, catálogo, soporte.
#   Negocio (Super Admin): planes, suscripciones, pagos, promociones, Home, comunicaciones, estadísticas
#   globales, configuración comercial, auditoría, retención e integraciones.
MOD = require_roles("moderator", "admin")
CATALOG = require_roles("catalog_editor", "admin")
USERS = require_roles("admin", "support")
FINANCE = require_roles("finance")          # finance + superadmin: lectura de suscripciones, pagos y finanzas
SUPER = require_roles("superadmin")         # solo dueños de Girando

Reason = Annotated[str, StringConstraints(min_length=3, max_length=500)]


class ActionIn(StrictModel):
    reason: Reason | None = None

    @field_validator("reason")
    @classmethod
    def _c(cls, v):
        return clean_text(v)


def _actor_role(user: CurrentUser) -> str:
    for r in ("superadmin", "admin", "moderator", "catalog_editor", "support", "finance"):
        if r in user.staff_roles:
            return r
    return "admin"


def _page(page: int, size: int) -> dict:
    return {"lim": size, "off": (page - 1) * size}


# --------------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(user: CurrentUser = Depends(staff_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        def by_status(table: str, enum: str) -> dict:
            return {r["status"]: r["n"] for r in rows(conn, f"SELECT status::text AS status, count(*) AS n FROM app.{table} GROUP BY 1")}
        data = {
            "users": by_status("users", "user_status"),
            "agencies": by_status("agencies", "agency_status"),
            "listings": by_status("listings", "listing_status"),
            "sales_total": scalar(conn, "SELECT count(*) FROM app.sales WHERE status = 'reported'"),
            "sales_attributed": scalar(conn, "SELECT count(*) FROM app.sales WHERE status = 'reported' AND attributed_to_girando"),
            "reports_open": scalar(conn, "SELECT count(*) FROM app.reports WHERE status IN ('pending','reviewing')"),
            "verifications_open": scalar(conn, "SELECT count(*) FROM app.verifications WHERE status IN ('pending','review')"),
            "moderation_queue": rows(conn, """SELECT l.id, l.public_code, l.title, l.submitted_at, cv.brand, cv.model, v.year
                                                FROM app.listings l JOIN app.vehicles v ON v.id = l.vehicle_id
                                                LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
                                               WHERE l.status = 'pending' ORDER BY l.submitted_at LIMIT 10"""),
            "published_last_7d": scalar(conn, "SELECT count(*) FROM app.listing_status_history WHERE to_status = 'published' AND created_at > now() - interval '7 days'"),
            "signups_last_7d": scalar(conn, "SELECT count(*) FROM app.users WHERE created_at > now() - interval '7 days'"),
            # Publicaciones aprobadas por semana (últimas 8), desde el historial real de estados
            "weekly_published": rows(conn, """SELECT w::date AS week, (SELECT count(*) FROM app.listing_status_history h
                                                   WHERE h.to_status = 'published' AND h.from_status = 'pending'
                                                     AND h.created_at >= w AND h.created_at < w + interval '7 days') AS n
                                                FROM generate_series(date_trunc('week', now()) - interval '7 weeks', date_trunc('week', now()), interval '1 week') w
                                               ORDER BY w"""),
        }
        data["can_business"] = user.has_role("finance")
        if data["can_business"]:
            data["subscriptions_active"] = scalar(conn, "SELECT count(*) FROM app.subscriptions WHERE status IN ('active','payment_failed','grace_period')")
        return data


# --------------------------------------------------------------------------- usuarios
@router.get("/users")
def users(q: Annotated[str | None, Query(max_length=100)] = None, status: str | None = None, page: int = Query(1, ge=1),
          page_size: int = Query(25, ge=1, le=100), user: CurrentUser = Depends(USERS)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        where = "(CAST(:q AS text) IS NULL OR u.email::text ILIKE '%' || :q || '%' OR p.display_name ILIKE '%' || :q || '%') AND (CAST(:s AS text) IS NULL OR u.status::text = :s)"
        p = {"q": q, "s": status, **_page(page, page_size)}
        total = scalar(conn, f"SELECT count(*) FROM app.users u LEFT JOIN app.user_profiles p ON p.user_id = u.id WHERE {where}", p)
        items = rows(conn, f"""SELECT u.id, u.email::text AS email, p.display_name, u.status::text AS status, u.status_reason,
                                      u.email_verified_at IS NOT NULL AS email_verified, u.identity_verified_at IS NOT NULL AS identity_verified,
                                      u.created_at, u.last_login_at,
                                      (SELECT string_agg(role::text, ',') FROM app.staff_roles s WHERE s.user_id = u.id AND s.revoked_at IS NULL) AS staff_roles,
                                      (SELECT count(*) FROM app.agency_members m WHERE m.user_id = u.id AND m.status = 'active') AS agencies,
                                      (SELECT count(*) FROM app.listings l WHERE l.owner_user_id = u.id AND l.status IN ('pending','published')) AS active_listings
                                 FROM app.users u LEFT JOIN app.user_profiles p ON p.user_id = u.id
                                WHERE {where} ORDER BY u.created_at DESC LIMIT :lim OFFSET :off""", p)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


class RolesIn(StrictModel):
    role: Literal["admin", "moderator", "finance", "support", "catalog_editor"]
    grant: bool = True


@router.post("/users/{user_id}/roles")
def user_roles(user_id: UUID, body: RolesIn, user: CurrentUser = Depends(require_roles("superadmin"))):
    with unit_of_work("app", user.id, user.ctx, reason="Gestión de roles de staff") as conn:
        if body.grant:
            conn.execute(text("""INSERT INTO app.staff_roles (user_id, role, granted_by) SELECT :u, CAST(:r AS app.staff_role), :me
                                 WHERE NOT EXISTS (SELECT 1 FROM app.staff_roles WHERE user_id = :u AND role = CAST(:r AS app.staff_role) AND revoked_at IS NULL)"""),
                         {"u": user_id, "r": body.role, "me": user.id})
        else:
            conn.execute(text("""UPDATE app.staff_roles SET revoked_at = now(), revoked_by = :me
                                 WHERE user_id = :u AND role = CAST(:r AS app.staff_role) AND revoked_at IS NULL"""), {"u": user_id, "r": body.role, "me": user.id})
    return {"ok": True}


@router.post("/users/{user_id}/{action}")
def user_action(user_id: UUID, action: Literal["suspend", "block", "reactivate"], body: ActionIn, user: CurrentUser = Depends(USERS)):
    if user_id == user.id:
        raise err(422, "ACCION_SOBRE_UNO_MISMO", "No podés cambiar el estado de tu propia cuenta.")
    if action != "reactivate" and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    to = {"suspend": "suspended", "block": "blocked", "reactivate": "active"}[action]
    with unit_of_work("app", user.id, user.ctx, reason=body.reason) as conn:
        cur = scalar(conn, "SELECT status::text FROM app.users WHERE id = :u", {"u": user_id})
        if cur is None:
            raise err(404, "NO_ENCONTRADO", "Usuario inexistente.")
        if cur == "deleted":
            raise err(409, "TRANSICION_NO_PERMITIDA")
        if scalar(conn, "SELECT 1 FROM app.staff_roles WHERE user_id = :u AND role = 'superadmin' AND revoked_at IS NULL", {"u": user_id}) and "superadmin" not in user.staff_roles:
            raise err(403, "ROL_INSUFICIENTE", "Solo un superadmin puede cambiar el estado de otro superadmin.")
        conn.execute(text("UPDATE app.users SET status = CAST(:s AS app.user_status), status_reason = :r WHERE id = :u"),
                     {"s": to, "r": body.reason, "u": user_id})
        conn.execute(text("""INSERT INTO app.moderation_actions (actor_user_id, actor_role, action, target_user_id, previous_state, new_state, reason)
                             VALUES (:a, CAST(:role AS app.staff_role), CAST(:act AS app.moderation_action_type), :u, :prev, :new, :r)"""),
                     {"a": user.id, "role": _actor_role(user), "act": {"suspend": "user_suspend", "block": "user_block", "reactivate": "user_reactivate"}[action],
                      "u": user_id, "prev": cur, "new": to, "r": body.reason})
    if to in ("suspended", "blocked"):
        with unit_of_work("worker", None, user.ctx) as conn:
            conn.execute(text("UPDATE app.sessions SET ended_at = now(), end_reason = 'admin_revoked' WHERE user_id = :u AND ended_at IS NULL"), {"u": user_id})
    return {"ok": True, "status": to}


# --------------------------------------------------------------------------- agencias
@router.get("/agencies")
def agencies(status: str | None = None, q: Annotated[str | None, Query(max_length=100)] = None, page: int = Query(1, ge=1),
             page_size: int = Query(25, ge=1, le=100), user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        where = "(CAST(:s AS text) IS NULL OR a.status::text = :s) AND (CAST(:q AS text) IS NULL OR a.trade_name ILIKE '%' || :q || '%' OR a.cuit LIKE '%' || :q || '%')"
        p = {"s": status, "q": q, **_page(page, page_size)}
        items = rows(conn, f"""SELECT a.id, a.slug, a.trade_name, a.legal_name, a.cuit, a.kind::text AS kind, a.status::text AS status, a.status_reason,
                                      a.verified_at, a.created_at, g.name AS locality,
                                      (SELECT p.display_name FROM app.agency_members m JOIN app.user_profiles p ON p.user_id = m.user_id
                                        WHERE m.agency_id = a.id AND m.role = 'owner' AND m.status = 'active') AS owner_name,
                                      (SELECT count(*) FROM app.listings l WHERE l.agency_id = a.id AND l.status = 'published') AS published,
                                      (SELECT v.status::text FROM app.verifications v WHERE v.subject_agency_id = a.id ORDER BY v.created_at DESC LIMIT 1) AS verification_status,
                                      (SELECT v.created_at FROM app.verifications v WHERE v.subject_agency_id = a.id ORDER BY v.created_at DESC LIMIT 1) AS verification_requested_at,
                                      (SELECT v.id FROM app.verifications v WHERE v.subject_agency_id = a.id ORDER BY v.created_at DESC LIMIT 1) AS verification_id,
                                      app.agency_verification_state(a.id) AS verification_state,
                                      (SELECT (p).name FROM (SELECT app.effective_plan(NULL, a.id) AS p) x) AS plan_name,
                                      (SELECT s.provider::text FROM app.subscriptions s WHERE s.agency_id = a.id AND app.subscription_grants(s)
                                        ORDER BY s.created_at DESC LIMIT 1) AS plan_provider,
                                      (SELECT count(*) FROM app.listings l WHERE l.agency_id = a.id AND l.status NOT IN ('sold','deleted')) AS inventory
                                 FROM app.agencies a JOIN app.geo_areas g ON g.id = a.geo_area_id
                                WHERE {where} ORDER BY a.created_at DESC LIMIT :lim OFFSET :off""", p)
        total = scalar(conn, f"SELECT count(*) FROM app.agencies a WHERE {where}", p)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/agencies/{agency_id}/{action}")
def agency_action(agency_id: UUID, action: Literal["verify", "reject", "suspend", "reactivate", "revoke"], body: ActionIn,
                  user: CurrentUser = Depends(MOD)):
    # Verificar / rechazar una solicitud es revisión (moderación). Suspender, revocar y reactivar
    # cambian el estado comercial de la agencia: solo Admin (o Super Admin).
    if action in ("suspend", "revoke", "reactivate") and not user.has_role("admin"):
        raise err(403, "ROL_INSUFICIENTE", "Suspender, revocar o reactivar una agencia lo hace un administrador.")
    if action in ("reject", "suspend", "revoke") and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    with unit_of_work("app", user.id, user.ctx, reason=body.reason) as conn:
        a = row(conn, "SELECT status::text AS status, verified_at FROM app.agencies WHERE id = :a FOR UPDATE", {"a": agency_id})
        if not a:
            raise err(404, "NO_ENCONTRADA", "Agencia inexistente.")
        ver = row(conn, "SELECT id, status::text AS status FROM app.verifications WHERE subject_agency_id = :a ORDER BY created_at DESC LIMIT 1", {"a": agency_id})
        mod_action = {"verify": "agency_verify", "reject": "agency_reject", "suspend": "agency_suspend", "reactivate": "agency_reactivate", "revoke": "agency_revoke"}[action]
        if action in ("verify", "reject"):
            if not ver or ver["status"] not in ("pending", "review"):
                raise err(409, "SIN_SOLICITUD", "La agencia no tiene una solicitud de verificación abierta.")
            if ver["status"] == "pending" and action == "verify":
                conn.execute(text("UPDATE app.verifications SET status = 'review' WHERE id = :v"), {"v": ver["id"]})
            conn.execute(text("UPDATE app.verifications SET status = CAST(:s AS app.verification_status), decision_reason = :r WHERE id = :v"),
                         {"s": "approved" if action == "verify" else "rejected", "r": body.reason, "v": ver["id"]})
        elif action == "revoke":
            if not ver or ver["status"] != "approved":
                raise err(409, "TRANSICION_NO_PERMITIDA", "La agencia no tiene una verificación aprobada.")
            conn.execute(text("UPDATE app.verifications SET status = 'revoked', decision_reason = :r WHERE id = :v"), {"r": body.reason, "v": ver["id"]})
        elif action == "suspend":
            if a["status"] == "suspended":
                raise err(409, "TRANSICION_NO_PERMITIDA")
            conn.execute(text("UPDATE app.agencies SET status = 'suspended', status_reason = :r WHERE id = :a"), {"r": body.reason, "a": agency_id})
        elif action == "reactivate":
            if a["status"] != "suspended":
                raise err(409, "TRANSICION_NO_PERMITIDA")
            conn.execute(text("UPDATE app.agencies SET status = CAST(:s AS app.agency_status), status_reason = NULL WHERE id = :a"),
                         {"s": "verified" if a["verified_at"] else "pending", "a": agency_id})
        new = scalar(conn, "SELECT status::text FROM app.agencies WHERE id = :a", {"a": agency_id})
        conn.execute(text("""INSERT INTO app.moderation_actions (actor_user_id, actor_role, action, agency_id, previous_state, new_state, reason)
                             VALUES (:u, CAST(:role AS app.staff_role), CAST(:act AS app.moderation_action_type), :a, :prev, :new, :r)"""),
                     {"u": user.id, "role": _actor_role(user), "act": mod_action, "a": agency_id, "prev": a["status"], "new": new, "r": body.reason})
        owner = scalar(conn, "SELECT user_id FROM app.agency_members WHERE agency_id = :a AND role = 'owner' AND status = 'active'", {"a": agency_id})
        if owner:
            conn.execute(text("SELECT app.enqueue_notification(:u, 'verification.agency_status', :t, :b, 'agency', :a, '/verificacion')"),
                         {"u": owner, "t": f"Verificación de agencia: {_AGENCY_LABEL.get(new, new)}", "b": body.reason or "Revisá el estado en Mi Girando.", "a": agency_id})
        return {"ok": True, "status": new}


_AGENCY_LABEL = {"pending": "pendiente", "review": "en revisión", "verified": "verificada", "rejected": "rechazada", "suspended": "suspendida", "revoked": "revocada"}


# --------------------------------------------------------------------------- publicaciones / moderación
@router.get("/listings")
def listings(status: str | None = None, q: Annotated[str | None, Query(max_length=100)] = None, page: int = Query(1, ge=1),
             page_size: int = Query(25, ge=1, le=100), user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        where = """(CAST(:s AS text) IS NULL OR l.status::text = :s) AND (CAST(:q AS text) IS NULL OR l.title ILIKE '%' || :q || '%'
                   OR l.public_code ILIKE '%' || :q || '%' OR cv.brand ILIKE '%' || :q || '%' OR cv.model ILIKE '%' || :q || '%')"""
        base = """FROM app.listings l JOIN app.vehicles v ON v.id = l.vehicle_id LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
                  LEFT JOIN app.user_profiles p ON p.user_id = l.owner_user_id LEFT JOIN app.agencies a ON a.id = l.agency_id"""
        p = {"s": status, "q": q, **_page(page, page_size)}
        items = rows(conn, f"""SELECT l.id, l.public_code, l.title, l.status::text AS status, l.status_reason, l.price_amount, l.currency::text AS currency,
                                      l.km, v.year, cv.brand, cv.model, cv.version, coalesce(a.trade_name, p.display_name) AS seller,
                                      CASE WHEN l.agency_id IS NULL THEN 'particular' ELSE a.kind::text END AS seller_type,
                                      l.submitted_at, l.published_at, l.updated_at,
                                      (SELECT count(*) FROM app.reports r WHERE r.listing_id = l.id AND r.status IN ('pending','reviewing')) AS open_reports,
                                      (SELECT count(*) FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active') AS photos,
                                      (SELECT secure_url FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_url,
                                      (SELECT count(*) FROM app.listings d JOIN app.vehicles dv ON dv.id = d.vehicle_id
                                        WHERE d.id <> l.id AND d.owner_user_id = l.owner_user_id AND dv.version_id = v.version_id AND dv.year = v.year
                                          AND d.price_amount = l.price_amount AND d.status IN ('pending','published')) AS possible_duplicates
                                 {base} WHERE {where} ORDER BY coalesce(l.submitted_at, l.updated_at) DESC LIMIT :lim OFFSET :off""", p)
        total = scalar(conn, f"SELECT count(*) {base} WHERE {where}", p)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/listings/{listing_id}")
def listing_detail(listing_id: UUID, user: CurrentUser = Depends(MOD)):
    from app.services.listing_service import get_private
    with unit_of_work("app", user.id, user.ctx) as conn:
        d = get_private(conn, listing_id)
        d["owner"] = row(conn, """SELECT u.id, u.email::text AS email, p.display_name, u.status::text AS status FROM app.listings l
                                  JOIN app.users u ON u.id = l.owner_user_id LEFT JOIN app.user_profiles p ON p.user_id = u.id WHERE l.id = :l""", {"l": listing_id})
        d["moderation"] = rows(conn, """SELECT action::text AS action, reason, previous_state, new_state, created_at, actor_role::text AS actor_role
                                        FROM app.moderation_actions WHERE listing_id = :l ORDER BY created_at DESC""", {"l": listing_id})
        return d


MODERATION = {
    "approve": ("published", "listing_approve", "listing.approved", "Tu publicación fue aprobada"),
    "request_changes": ("requires_changes", "listing_request_changes", "listing.changes_requested", "Tu publicación necesita cambios"),
    "reject": ("rejected", "listing_reject", "listing.rejected", "Tu publicación fue rechazada"),
    "pause": ("paused", "listing_pause", "listing.paused", "Tu publicación fue pausada por moderación"),
    "reactivate": ("published", "listing_reactivate", "listing.approved", "Tu publicación volvió a estar visible"),
    "delete": ("deleted", "listing_delete", "listing.deleted", "Tu publicación fue eliminada por moderación"),
}


@router.post("/listings/{listing_id}/{action}")
def moderate(listing_id: UUID, action: Literal["approve", "request_changes", "reject", "pause", "reactivate", "delete"], body: ActionIn,
             user: CurrentUser = Depends(MOD)):
    to, mod_action, ntype, ntitle = MODERATION[action]
    if action not in ("approve", "reactivate") and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    with unit_of_work("app", user.id, user.ctx, reason=body.reason) as conn:
        cur = row(conn, "SELECT status::text AS status, owner_user_id, title FROM app.listings WHERE id = :l FOR UPDATE", {"l": listing_id})
        if not cur:
            raise err(404, "NO_ENCONTRADA", "Publicación inexistente.")
        conn.execute(text("UPDATE app.listings SET status = CAST(:s AS app.listing_status), status_reason = :r WHERE id = :l"),
                     {"s": to, "r": body.reason, "l": listing_id})
        conn.execute(text("""INSERT INTO app.moderation_actions (actor_user_id, actor_role, action, listing_id, previous_state, new_state, reason)
                             VALUES (:u, CAST(:role AS app.staff_role), CAST(:act AS app.moderation_action_type), :l, :prev, :new, :r)"""),
                     {"u": user.id, "role": _actor_role(user), "act": mod_action, "l": listing_id, "prev": cur["status"], "new": to, "r": body.reason})
        conn.execute(text("SELECT app.enqueue_notification(:u, :t, :title, :body, 'listing', :l, '/mis-publicaciones')"),
                     {"u": cur["owner_user_id"], "t": ntype, "title": ntitle, "body": (cur["title"] or "Tu publicación") + (f" · {body.reason}" if body.reason else ""), "l": listing_id})
        return {"ok": True, "status": to}


# --------------------------------------------------------------------------- catálogo
class BrandIn(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]


class ModelIn(StrictModel):
    brand_id: UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    vehicle_type: Literal["car", "light_truck", "van", "truck", "motorcycle", "atv", "other"]
    default_body_type: Literal["sedan", "hatchback", "suv", "pickup", "coupe", "convertible", "wagon", "van", "minivan", "chassis", "motorcycle", "other"] | None = None
    segment: Annotated[str, StringConstraints(max_length=30)] | None = None


class GenerationIn(StrictModel):
    model_id: UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    year_from: Annotated[int, Field(ge=1900, le=2100)]
    year_to: Annotated[int, Field(ge=1900, le=2100)] | None = None


class EngineIn(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    fuel: Literal["gasoline", "diesel", "cng", "gasoline_cng", "hybrid", "plugin_hybrid", "electric", "other"]
    displacement_cc: Annotated[int, Field(ge=49, le=20000)] | None = None
    power_hp: Annotated[int, Field(ge=1, le=2000)] | None = None
    torque_nm: Annotated[int, Field(ge=1, le=5000)] | None = None
    cylinders: Annotated[int, Field(ge=1, le=16)] | None = None
    aspiration: Literal["natural", "turbo", "supercharged", "electric"] | None = None


class VersionIn(StrictModel):
    generation_id: UUID
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    body_type: Literal["sedan", "hatchback", "suv", "pickup", "coupe", "convertible", "wagon", "van", "minivan", "chassis", "motorcycle", "other"] | None = None
    doors: Annotated[int, Field(ge=0, le=6)] | None = None
    seats: Annotated[int, Field(ge=1, le=60)] | None = None
    transmission: Literal["manual", "automatic", "cvt", "automated_manual", "other"] | None = None
    gears: Annotated[int, Field(ge=1, le=12)] | None = None
    traction: Literal["front", "rear", "4x2", "4x4", "awd"] | None = None
    origin_country: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] | None = None
    year_from: Annotated[int, Field(ge=1900, le=2100)] | None = None
    year_to: Annotated[int, Field(ge=1900, le=2100)] | None = None
    engine_ids: list[UUID] = []


CATALOG_TABLES = {"brands": "vehicle_brands", "models": "vehicle_models", "generations": "vehicle_generations",
                  "versions": "vehicle_versions", "engines": "vehicle_engines"}
PATCHABLE = {
    "brands": {"name"},
    "models": {"name", "vehicle_type", "default_body_type", "segment"},
    "generations": {"name", "year_from", "year_to"},
    "versions": {"name", "body_type", "doors", "seats", "transmission", "gears", "traction", "origin_country", "year_from", "year_to"},
    "engines": {"name", "fuel", "displacement_cc", "power_hp", "torque_nm", "cylinders", "aspiration"},
}
CASTS = {"vehicle_type": "app.vehicle_type", "default_body_type": "app.body_type", "body_type": "app.body_type",
         "transmission": "app.transmission_type", "traction": "app.traction_type", "fuel": "app.fuel_type", "aspiration": "app.engine_aspiration"}


def _slug(s: str) -> str:
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


def _usage_sql(level: str) -> str:
    col = {"brands": "cv.brand_id", "models": "cv.model_id", "generations": "cv.generation_id", "versions": "cv.version_id"}.get(level)
    if level == "engines":
        return "(SELECT count(*) FROM app.vehicles vv WHERE vv.engine_id = x.id)"
    return f"""(SELECT count(*) FROM app.vehicles vv JOIN app.v_catalog_versions cv ON cv.version_id = vv.version_id WHERE {col} = x.id)"""


@router.get("/catalog/{level}")
def catalog_list(level: Literal["brands", "models", "generations", "versions", "engines"], parent_id: UUID | None = None,
                 user: CurrentUser = Depends(CATALOG)):
    parent_col = {"models": "brand_id", "generations": "model_id", "versions": "generation_id"}.get(level)
    with unit_of_work("app", user.id, user.ctx) as conn:
        where = f"x.{parent_col} = :p" if parent_col and parent_id else "true"
        items = rows(conn, f"SELECT x.*, x.status::text AS status, {_usage_sql(level)} AS vehicles_count FROM app.{CATALOG_TABLES[level]} x WHERE {where} ORDER BY x.name",
                     {"p": parent_id})
        if level == "versions":
            for v in items:
                v["engines"] = rows(conn, """SELECT e.id, e.name, e.fuel::text AS fuel, ve.is_default, ve.status::text AS status
                                              FROM app.vehicle_version_engines ve JOIN app.vehicle_engines e ON e.id = ve.engine_id
                                             WHERE ve.version_id = :v ORDER BY e.name""", {"v": v["id"]})
        return {"items": items}


def _insert(conn, table: str, data: dict) -> UUID:
    cols = list(data)
    vals = ", ".join(f"CAST(:{c} AS {CASTS[c]})" if c in CASTS else f":{c}" for c in cols)
    return scalar(conn, f"INSERT INTO app.{table} ({', '.join(cols)}) VALUES ({vals}) RETURNING id", data)


@router.post("/catalog/brands", status_code=201)
def create_brand(body: BrandIn, user: CurrentUser = Depends(CATALOG)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"id": _insert(conn, "vehicle_brands", {"name": body.name, "slug": _slug(body.name)})}


@router.post("/catalog/models", status_code=201)
def create_model(body: ModelIn, user: CurrentUser = Depends(CATALOG)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"id": _insert(conn, "vehicle_models", {**body.model_dump(exclude_none=True), "slug": _slug(body.name)})}


@router.post("/catalog/generations", status_code=201)
def create_generation(body: GenerationIn, user: CurrentUser = Depends(CATALOG)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"id": _insert(conn, "vehicle_generations", body.model_dump(exclude_none=True))}


@router.post("/catalog/engines", status_code=201)
def create_engine(body: EngineIn, user: CurrentUser = Depends(CATALOG)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"id": _insert(conn, "vehicle_engines", body.model_dump(exclude_none=True))}


@router.post("/catalog/versions", status_code=201)
def create_version(body: VersionIn, user: CurrentUser = Depends(CATALOG)):
    data = body.model_dump(exclude_none=True)
    engines = data.pop("engine_ids", [])
    with unit_of_work("app", user.id, user.ctx) as conn:
        vid = _insert(conn, "vehicle_versions", data)
        for i, e in enumerate(engines):
            conn.execute(text("INSERT INTO app.vehicle_version_engines (version_id, engine_id, is_default) VALUES (:v, :e, :d)"),
                         {"v": vid, "e": e, "d": i == 0})
        return {"id": vid}


class CatalogPatch(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    status: Literal["active", "inactive"] | None = None
    vehicle_type: str | None = None
    default_body_type: str | None = None
    segment: str | None = None
    year_from: Annotated[int, Field(ge=1900, le=2100)] | None = None
    year_to: Annotated[int, Field(ge=1900, le=2100)] | None = None
    body_type: str | None = None
    doors: Annotated[int, Field(ge=0, le=6)] | None = None
    seats: Annotated[int, Field(ge=1, le=60)] | None = None
    transmission: str | None = None
    gears: Annotated[int, Field(ge=1, le=12)] | None = None
    traction: str | None = None
    origin_country: str | None = None
    fuel: str | None = None
    displacement_cc: Annotated[int, Field(ge=49, le=20000)] | None = None
    power_hp: Annotated[int, Field(ge=1, le=2000)] | None = None
    torque_nm: Annotated[int, Field(ge=1, le=5000)] | None = None
    cylinders: Annotated[int, Field(ge=1, le=16)] | None = None
    aspiration: str | None = None


@router.patch("/catalog/{level}/{item_id}")
def patch_catalog(level: Literal["brands", "models", "generations", "versions", "engines"], item_id: UUID, body: CatalogPatch,
                  user: CurrentUser = Depends(CATALOG)):
    data = body.model_dump(exclude_unset=True)
    bad = set(data) - PATCHABLE[level] - {"status"}
    if bad:
        raise err(422, "CAMPO_NO_EDITABLE", f"Campos no editables para {level}: {', '.join(sorted(bad))}")
    if not data:
        return {"ok": True}
    parts = []
    for k in data:
        cast = "app.catalog_status" if k == "status" else CASTS.get(k)
        parts.append(f"{k} = CAST(:{k} AS {cast})" if cast else f"{k} = :{k}")
    if "name" in data and level in ("brands", "models"):
        parts.append("slug = :slug")
        data["slug"] = _slug(data["name"])
    with unit_of_work("app", user.id, user.ctx, reason=f"Catálogo: edición de {level}") as conn:
        res = conn.execute(text(f"UPDATE app.{CATALOG_TABLES[level]} SET {', '.join(parts)} WHERE id = :id"), {**data, "id": item_id})
        if res.rowcount == 0:
            raise err(404, "NO_ENCONTRADO", "Elemento inexistente.")
    return {"ok": True}


class VersionEngineIn(StrictModel):
    engine_id: UUID
    status: Literal["active", "inactive"] = "active"
    is_default: bool = False


@router.put("/catalog/versions/{version_id}/engines")
def link_engine(version_id: UUID, body: VersionEngineIn, user: CurrentUser = Depends(CATALOG)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if body.is_default:
            conn.execute(text("UPDATE app.vehicle_version_engines SET is_default = false WHERE version_id = :v"), {"v": version_id})
        conn.execute(text("""INSERT INTO app.vehicle_version_engines (version_id, engine_id, is_default, status)
                             VALUES (:v, :e, :d, CAST(:s AS app.catalog_status))
                             ON CONFLICT (version_id, engine_id) DO UPDATE SET is_default = EXCLUDED.is_default, status = EXCLUDED.status"""),
                     {"v": version_id, "e": body.engine_id, "d": body.is_default, "s": body.status})
    return {"ok": True}


# --------------------------------------------------------------------------- auditoría, planes, retención, verificaciones, reportes
@router.get("/audit")
def audit(entity_type: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
          user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        p = {"t": entity_type, **_page(page, page_size)}
        items = rows(conn, """SELECT a.id, a.occurred_at, a.actor_type::text AS actor_type, a.actor_role, a.action, a.entity_type, a.entity_id,
                                     a.before_data, a.after_data, a.reason, host(a.ip) AS ip, pr.display_name AS actor_name
                                FROM app.audit_logs a LEFT JOIN app.user_profiles pr ON pr.user_id = a.actor_user_id
                               WHERE CAST(:t AS text) IS NULL OR a.entity_type = :t ORDER BY a.id DESC LIMIT :lim OFFSET :off""", p)
        total = scalar(conn, "SELECT count(*) FROM app.audit_logs WHERE CAST(:t AS text) IS NULL OR entity_type = :t", p)
        return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/plans")
def plans(user: CurrentUser = Depends(FINANCE)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, "SELECT *, audience::text AS audience, billing_period::text AS billing_period, currency::text AS currency FROM app.plans p ORDER BY p.audience, p.sort_order")}


class PlanPatch(StrictModel):
    name: Annotated[str, StringConstraints(min_length=2, max_length=60)] | None = None
    description: Annotated[str, StringConstraints(max_length=300)] | None = None
    price_amount: Annotated[float, Field(ge=0, le=100_000_000)] | None = None
    max_active_listings: Annotated[int, Field(ge=0, le=100000)] | None = None
    included_featured_listings: Annotated[int, Field(ge=0, le=1000)] | None = None
    max_members: Annotated[int, Field(ge=1, le=1000)] | None = None
    stats_level: Annotated[int, Field(ge=0, le=3)] | None = None
    is_public: bool | None = None
    is_active: bool | None = None
    features_display: list[Annotated[str, StringConstraints(max_length=80)]] | None = None


@router.patch("/plans/{plan_id}")
def patch_plan(plan_id: UUID, body: PlanPatch, user: CurrentUser = Depends(SUPER)):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return {"ok": True}
    with unit_of_work("app", user.id, user.ctx, reason="Edición de plan") as conn:
        res = conn.execute(text(f"UPDATE app.plans SET {', '.join(f'{k} = :{k}' for k in data)} WHERE id = :id"), {**data, "id": plan_id})
        if res.rowcount == 0:
            raise err(404, "NO_ENCONTRADO", "Plan inexistente.")
    return {"ok": True}


@router.get("/retention")
def retention(user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT code, label, category::text AS category, extract(epoch FROM duration)::bigint AS duration_seconds,
                                              duration::text AS duration, starts_from, action::text AS action, is_active, approved_for_production, updated_at
                                         FROM app.retention_policies ORDER BY category, code""")}


class RetentionPatch(StrictModel):
    value: Annotated[int, Field(ge=1, le=3650)]
    unit: Literal["days", "months", "years"]


@router.patch("/retention/{code}")
def patch_retention(code: str, body: RetentionPatch, user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx, reason="Cambio de política de retención") as conn:
        res = conn.execute(text("UPDATE app.retention_policies SET duration = CAST(:d AS interval), updated_by = :u WHERE code = :c"),
                           {"d": f"{body.value} {body.unit}", "u": user.id, "c": code[:60]})
        if res.rowcount == 0:
            raise err(404, "NO_ENCONTRADO", "Política inexistente.")
    return {"ok": True}


@router.get("/verifications")
def verifications(user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT v.id, v.status::text AS status, p.name AS product, v.created_at, v.decided_at, v.decision_reason,
                                              a.trade_name AS agency, v.subject_agency_id AS agency_id, up.display_name AS user_name
                                         FROM app.verifications v JOIN app.verification_products p ON p.id = v.product_id
                                         LEFT JOIN app.agencies a ON a.id = v.subject_agency_id
                                         LEFT JOIN app.user_profiles up ON up.user_id = v.subject_user_id
                                        ORDER BY v.created_at DESC LIMIT 200""")}


@router.get("/reports")
def reports(user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT r.id, r.target::text AS target, rr.label AS reason, r.description, r.status::text AS status, r.created_at,
                                              l.public_code, l.title AS listing_title, r.resolution_note
                                         FROM app.reports r JOIN app.report_reasons rr ON rr.id = r.reason_id
                                         LEFT JOIN app.listings l ON l.id = r.listing_id ORDER BY r.created_at DESC LIMIT 200""")}


class ResolveIn(StrictModel):
    resolution: Literal["resolved", "rejected"]
    note: Reason


@router.post("/reports/{report_id}/resolve")
def resolve_report(report_id: UUID, body: ResolveIn, user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx, reason=body.note) as conn:
        res = conn.execute(text("""UPDATE app.reports SET status = CAST(:s AS app.report_status), resolved_by = :u, resolved_at = now(), resolution_note = :n
                                   WHERE id = :id AND status IN ('pending','reviewing')"""),
                           {"s": body.resolution, "u": user.id, "n": body.note, "id": report_id})
        if res.rowcount == 0:
            raise err(409, "TRANSICION_NO_PERMITIDA")
        conn.execute(text("""INSERT INTO app.moderation_actions (actor_user_id, actor_role, action, report_id, reason)
                             VALUES (:u, CAST(:role AS app.staff_role), CAST(:a AS app.moderation_action_type), :r, :n)"""),
                     {"u": user.id, "role": _actor_role(user), "a": "report_resolve" if body.resolution == "resolved" else "report_dismiss", "r": report_id, "n": body.note})
    return {"ok": True}



# --------------------------------------------------------------------------- ventas (datos reales, regla n >= mínimo)
@router.get("/sales-stats")
def sales_stats(days: int = Query(30, ge=1, le=3650), user: CurrentUser = Depends(FINANCE)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        n_min = scalar(conn, "SELECT app.setting_int('stats.min_sample_size', 3)")
        p = {"d": days}
        k = row(conn, """SELECT (SELECT count(*) FROM app.listings WHERE created_at > now() - make_interval(days => :d)) AS created,
                                (SELECT count(*) FROM app.listings WHERE status = 'published') AS published,
                                count(*) AS sold, count(*) FILTER (WHERE s.attributed_to_girando) AS attributed,
                                sum(s.final_price) FILTER (WHERE s.currency = 'ARS') AS volume_ars,
                                count(*) FILTER (WHERE s.currency = 'ARS') AS n_ars, avg(s.final_price) FILTER (WHERE s.currency = 'ARS') AS avg_ars
                           FROM app.sales s WHERE s.status = 'reported' AND s.sold_on > current_date - :d""", p)
        models = rows(conn, """SELECT cv.brand || ' ' || cv.model AS name, count(*) AS sold,
                                      avg(l.price_amount) FILTER (WHERE s.currency = 'ARS' AND l.currency = 'ARS') AS avg_listed,
                                      avg(s.final_price) FILTER (WHERE s.currency = 'ARS') AS avg_sold,
                                      avg(s.sold_on - l.first_published_at::date) AS avg_days,
                                      (SELECT count(*) FROM app.listings l2 JOIN app.vehicles v2 ON v2.id = l2.vehicle_id JOIN app.v_catalog_versions c2 ON c2.version_id = v2.version_id
                                        WHERE c2.model_id = cv.model_id AND l2.status IN ('published','sold')) AS published
                                 FROM app.sales s JOIN app.listings l ON l.id = s.listing_id JOIN app.vehicles v ON v.id = s.vehicle_id
                                 JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
                                WHERE s.status = 'reported' AND s.sold_on > current_date - :d
                                GROUP BY cv.brand, cv.model, cv.model_id ORDER BY sold DESC LIMIT 20""", p)
        for m in models:
            if m["sold"] < n_min:
                m["avg_listed"] = m["avg_sold"] = m["avg_days"] = None
        brands = rows(conn, """SELECT cv.brand AS name, count(*) AS n FROM app.listings l JOIN app.vehicles v ON v.id = l.vehicle_id
                                JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id WHERE l.status = 'published'
                                GROUP BY cv.brand ORDER BY n DESC LIMIT 8""")
        if k["n_ars"] < n_min:
            k["avg_ars"] = None
        return {"days": days, "min_sample": n_min, "kpis": k, "models": models, "brands": brands}


@router.get("/media-queue")
def media_queue(user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT l.id, l.public_code, coalesce(cv.brand || ' ' || cv.model || ' ' || v.year, l.title) AS title, l.status::text AS reason,
                                              count(*) AS photos, min(i.purge_after) AS scheduled,
                                              CASE WHEN bool_and(i.status = 'purged') THEN 'purged' ELSE 'scheduled' END AS status
                                         FROM app.listing_images i JOIN app.listings l ON l.id = i.listing_id JOIN app.vehicles v ON v.id = l.vehicle_id
                                         LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
                                        WHERE i.status IN ('purge_scheduled','purged')
                                        GROUP BY l.id, cv.brand, cv.model, v.year ORDER BY min(i.purge_after) DESC LIMIT 200""")}


@router.get("/emails")
def emails(user: CurrentUser = Depends(SUPER)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT e.id, t.code AS template_code, t.subject AS template_name, e.event_code,
                                              regexp_replace(e.to_email::text, '^(.).*(@.*)$', '\\1***\\2') AS to_email_masked,
                                              e.status::text AS status, e.last_error, e.created_at, e.sent_at
                                         FROM app.email_events e JOIN app.email_templates t ON t.id = e.template_id ORDER BY e.created_at DESC LIMIT 200""")}
