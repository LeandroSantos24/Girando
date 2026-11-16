"""/api/me — Mi Girando: perfil, publicaciones, fotos, venta, favoritos, estadísticas, notificaciones, agencias."""
from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import EmailStr, StringConstraints, field_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, current_user
from app.core import ratelimit
from app.core.db import row, rows, scalar, set_reason, unit_of_work
from app.core.errors import err
from app.integrations import NotConfigured
from app.schemas.common import PhoneE164, StrictModel, clean_text
from app.schemas.listings import (
    CloudinaryConfirmIn,
    ContactPatch,
    ImagePatch,
    ListingCreate,
    ListingPatch,
    ReorderIn,
    SaleIn,
    TransitionIn,
)
from app.services import listing_service
from app.services.account_service import me_summary, plan_usage
from app.services.analytics import track
from app.services.media import MAX_BYTES, CloudinaryImageStorage, get_storage

router = APIRouter(prefix="/api/me", tags=["mi girando"])

URL = Annotated[str, StringConstraints(max_length=200)]


class ProfilePatch(StrictModel):
    display_name: Annotated[str, StringConstraints(min_length=2, max_length=60)] | None = None
    bio: Annotated[str, StringConstraints(max_length=500)] | None = None
    geo_area_id: UUID | None = None
    first_name: Annotated[str, StringConstraints(max_length=80)] | None = None
    last_name: Annotated[str, StringConstraints(max_length=80)] | None = None
    contact_phone_e164: PhoneE164 | None = None
    contact_whatsapp_e164: PhoneE164 | None = None
    contact_email: EmailStr | None = None
    instagram_url: URL | None = None
    tiktok_url: URL | None = None
    facebook_url: URL | None = None
    x_url: URL | None = None
    youtube_url: URL | None = None
    website_url: URL | None = None
    is_public: bool | None = None
    show_phone_default: bool | None = None

    @field_validator("display_name", "bio", "first_name", "last_name")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)


PROFILE_COLS = ("display_name", "bio", "geo_area_id", "contact_phone_e164", "contact_whatsapp_e164", "contact_email", "instagram_url",
                "tiktok_url", "facebook_url", "x_url", "youtube_url", "website_url", "is_public", "show_phone_default")


@router.get("/profile")
def get_profile(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return me_summary(conn, user.id)


@router.patch("/profile")
def patch_profile(body: ProfilePatch, user: CurrentUser = Depends(current_user)):
    data = body.model_dump(exclude_unset=True)
    with unit_of_work("app", user.id, user.ctx) as conn:
        p = {k: data[k] for k in PROFILE_COLS if k in data}
        if p:
            conn.execute(text(f"UPDATE app.user_profiles SET {', '.join(f'{k} = :{k}' for k in p)} WHERE user_id = :u"), {**p, "u": user.id})
        pd = {k: data[k] for k in ("first_name", "last_name") if k in data}
        if pd:
            conn.execute(text(f"UPDATE app.user_personal_data SET {', '.join(f'{k} = :{k}' for k in pd)} WHERE user_id = :u"), {**pd, "u": user.id})
        return me_summary(conn, user.id)


@router.get("/plan")
def my_plan(agency_id: UUID | None = None, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if agency_id and not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
            raise err(403, "NO_AUTORIZADO", "No sos miembro de esa agencia.")
        return plan_usage(conn, user.id, agency_id)


# --------------------------------------------------------------------------- publicaciones
@router.get("/listings")
def my_listings(group: Literal["activas", "finalizadas", "todas"] = "todas", agency_id: UUID | None = None,
                user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": listing_service.list_mine(conn, user.id, group, agency_id),
                "usage": plan_usage(conn, user.id, agency_id)}


@router.post("/listings", status_code=201)
def create_listing(body: ListingCreate, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        lid = listing_service.create(conn, user.id, body.model_dump(exclude_unset=True))
        out = listing_service.get_private(conn, lid)
    track("listing_created", user.ctx, user.id, listing_id=lid)
    return out


@router.get("/listings/{listing_id}")
def get_listing(listing_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return listing_service.get_private(conn, listing_id)


@router.patch("/listings/{listing_id}")
def patch_listing(listing_id: UUID, body: ListingPatch, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        listing_service.update(conn, listing_id, body.model_dump(exclude_unset=True))
        return listing_service.get_private(conn, listing_id)


@router.post("/listings/{listing_id}/transition")
def transition(listing_id: UUID, body: TransitionIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        listing_service.transition(conn, listing_id, body.to)
        return listing_service.get_private(conn, listing_id)


@router.post("/listings/{listing_id}/renew")
def renew(listing_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        listing_service.renew(conn, listing_id)
        return listing_service.get_private(conn, listing_id)


@router.patch("/listings/{listing_id}/contact")
def patch_contact(listing_id: UUID, body: ContactPatch, user: CurrentUser = Depends(current_user)):
    data = body.model_dump(exclude_unset=True)
    with unit_of_work("app", user.id, user.ctx) as conn:
        if "show_email" in data:
            data["email"] = user.email if data["show_email"] else None
        if data:
            res = conn.execute(text(f"UPDATE app.listing_contacts SET {', '.join(f'{k} = :{k}' for k in data)} WHERE listing_id = :l"),
                               {**data, "l": listing_id})
            if res.rowcount == 0:
                raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        return listing_service.get_private(conn, listing_id)


@router.post("/listings/{listing_id}/sale", status_code=201)
def sale(listing_id: UUID, body: SaleIn, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        sale_id = listing_service.register_sale(conn, listing_id, body.model_dump())
        s = row(conn, """SELECT s.id, s.public_code, s.sold_on, s.final_price, s.currency::text AS currency, s.channel::text AS channel,
                                s.attributed_to_girando, (s.sold_on - l.first_published_at::date) AS days_to_sell,
                                (SELECT min(purge_after) FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'purge_scheduled') AS photos_purge_after
                           FROM app.sales s JOIN app.listings l ON l.id = s.listing_id WHERE s.id = :s""", {"s": sale_id})
    track("listing_sold", user.ctx, user.id, listing_id=listing_id)
    return s


# --------------------------------------------------------------------------- fotos
@router.post("/listings/{listing_id}/images", status_code=201)
async def upload_image(listing_id: UUID, file: UploadFile = File(...),
                       kind: Literal["front", "rear", "left", "right", "interior", "additional"] = Form("additional"),
                       user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.IMAGE_UPLOAD_USER, str(user.id))
    data = await file.read(MAX_BYTES + 1)
    try:
        storage = get_storage()
    except NotConfigured as e:
        raise err(503, "ALMACENAMIENTO_NO_CONFIGURADO", str(e)) from None
    if isinstance(storage, CloudinaryImageStorage):
        raise err(400, "USAR_SUBIDA_DIRECTA", "Con Cloudinary la subida es directa: pedí /images/upload-signature.")
    with unit_of_work("app", user.id, user.ctx) as conn:
        st = scalar(conn, "SELECT status::text FROM app.listings WHERE id = :l", {"l": listing_id})
        if st is None:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        if st in ("sold", "deleted", "pending"):
            raise err(409, "CAMPO_NO_EDITABLE", "No se pueden cambiar las fotos en este estado.")
        count = scalar(conn, "SELECT count(*) FROM app.listing_images WHERE listing_id = :l AND status = 'active'", {"l": listing_id})
        if count >= 6:
            raise err(409, "MAXIMO_FOTOS")
    stored = storage.save(listing_id, data)
    try:
        with unit_of_work("app", user.id, user.ctx) as conn:
            pos = scalar(conn, """SELECT min(p) FROM generate_series(1, 6) p WHERE p NOT IN
                                  (SELECT position FROM app.listing_images WHERE listing_id = :l AND status = 'active')""", {"l": listing_id})
            img_id = scalar(conn, """INSERT INTO app.listing_images (listing_id, storage_provider, public_id, secure_url, etag, format, kind, position,
                                        width, height, bytes, uploaded_by)
                                     VALUES (:l, CAST(:prov AS app.image_storage_provider), :pid, :url, :etag, :fmt, CAST(:kind AS app.image_kind), :pos,
                                        :w, :h, :b, :u) RETURNING id""",
                             {"l": listing_id, "prov": stored.provider, "pid": stored.public_id, "url": stored.secure_url, "etag": stored.etag,
                              "fmt": stored.format, "kind": kind, "pos": pos, "w": stored.width, "h": stored.height, "b": stored.bytes, "u": user.id})
            return {**listing_service.get_private(conn, listing_id), "image_id": img_id}
    except Exception:
        storage.delete(stored.public_id)
        raise


@router.post("/listings/{listing_id}/images/upload-signature")
def upload_signature(listing_id: UUID, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.IMAGE_UPLOAD_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.can_manage_listing_id(:l)", {"l": listing_id}):
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
    try:
        return CloudinaryImageStorage().upload_signature(listing_id)
    except NotConfigured as e:
        raise err(503, "CLOUDINARY_NO_CONFIGURADO", str(e)) from None


@router.post("/listings/{listing_id}/images/confirm", status_code=201)
def confirm_cloudinary(listing_id: UUID, body: CloudinaryConfirmIn, user: CurrentUser = Depends(current_user)):
    try:
        storage = CloudinaryImageStorage()
    except NotConfigured as e:
        raise err(503, "CLOUDINARY_NO_CONFIGURADO", str(e)) from None
    stored = storage.confirm(listing_id, body.public_id, body.version, body.signature)
    with unit_of_work("app", user.id, user.ctx) as conn:
        pos = scalar(conn, """SELECT min(p) FROM generate_series(1, 6) p WHERE p NOT IN
                              (SELECT position FROM app.listing_images WHERE listing_id = :l AND status = 'active')""", {"l": listing_id})
        conn.execute(text("""INSERT INTO app.listing_images (listing_id, storage_provider, public_id, provider_version, provider_asset_id, secure_url,
                                etag, format, kind, position, width, height, bytes, uploaded_by)
                             VALUES (:l, 'cloudinary', :pid, :ver, :aid, :url, :etag, :fmt, CAST(:kind AS app.image_kind), :pos, :w, :h, :b, :u)"""),
                     {"l": listing_id, "pid": stored.public_id, "ver": stored.provider_version, "aid": stored.provider_asset_id,
                      "url": stored.secure_url, "etag": stored.etag, "fmt": stored.format, "kind": body.kind, "pos": pos,
                      "w": stored.width, "h": stored.height, "b": stored.bytes, "u": user.id})
        return listing_service.get_private(conn, listing_id)


@router.patch("/listings/{listing_id}/images/{image_id}")
def patch_image(listing_id: UUID, image_id: UUID, body: ImagePatch, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if body.is_cover:
            conn.execute(text("UPDATE app.listing_images SET is_cover = false WHERE listing_id = :l AND status = 'active' AND id <> :i"),
                         {"l": listing_id, "i": image_id})
            conn.execute(text("UPDATE app.listing_images SET is_cover = true WHERE listing_id = :l AND id = :i AND status = 'active'"),
                         {"l": listing_id, "i": image_id})
        if body.kind:
            conn.execute(text("UPDATE app.listing_images SET kind = CAST(:k AS app.image_kind) WHERE listing_id = :l AND id = :i"),
                         {"k": body.kind, "l": listing_id, "i": image_id})
        return listing_service.get_private(conn, listing_id)


@router.post("/listings/{listing_id}/images/reorder")
def reorder_images(listing_id: UUID, body: ReorderIn, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        active = {r["id"] for r in rows(conn, "SELECT id FROM app.listing_images WHERE listing_id = :l AND status = 'active'", {"l": listing_id})}
        if set(body.image_ids) != active:
            raise err(422, "ORDEN_INVALIDO", "Enviá todas las fotos activas, cada una una vez.")
        for pos, iid in enumerate(body.image_ids, start=1):  # restricción diferida: se valida al commit
            conn.execute(text("UPDATE app.listing_images SET position = :p WHERE id = :i AND listing_id = :l"), {"p": pos, "i": iid, "l": listing_id})
        return listing_service.get_private(conn, listing_id)


@router.delete("/listings/{listing_id}/images/{image_id}")
def delete_image(listing_id: UUID, image_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        was_cover = scalar(conn, "SELECT is_cover FROM app.listing_images WHERE id = :i AND listing_id = :l AND status = 'active'",
                           {"i": image_id, "l": listing_id})
        if was_cover is None:
            raise err(404, "NO_ENCONTRADA", "La foto no existe.")
        # 'deleted' → el job de retención la borra del almacenamiento real
        conn.execute(text("UPDATE app.listing_images SET status = 'deleted', is_cover = false WHERE id = :i"), {"i": image_id})
        if was_cover:
            conn.execute(text("""UPDATE app.listing_images SET is_cover = true WHERE id = (SELECT id FROM app.listing_images
                                 WHERE listing_id = :l AND status = 'active' ORDER BY position LIMIT 1)"""), {"l": listing_id})
        return listing_service.get_private(conn, listing_id)


# --------------------------------------------------------------------------- ventas y estadísticas
@router.get("/sales")
def my_sales(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return listing_service.sales_summary(conn, user.id)


@router.get("/stats")
def my_stats(days: Literal[7, 30, 90] = 30, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        per = rows(conn, """SELECT l.id, l.public_code, l.title, l.status::text AS status,
                                   coalesce(sum(s.views), 0) AS views, coalesce(sum(s.contacts + s.contact_reveals), 0) AS contacts,
                                   coalesce(sum(s.shares), 0) AS shares, app.listing_favorites_count(l.id) AS favorites
                              FROM app.listings l LEFT JOIN app.listing_stats_daily s ON s.listing_id = l.id AND s.day > current_date - :d
                             WHERE l.owner_user_id = :u AND l.status NOT IN ('draft','deleted')
                             GROUP BY l.id ORDER BY l.updated_at DESC""", {"u": user.id, "d": days})
        totals = {k: sum(int(p[k] or 0) for p in per) for k in ("views", "contacts", "shares", "favorites")}
        return {"days": days, "totals": totals, "listings": per, "has_data": any(totals.values()),
                "note": "Las métricas se calculan a partir de eventos reales; se actualizan cada pocos minutos."}


# --------------------------------------------------------------------------- favoritos
@router.get("/favorites")
def favorites(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT f.listing_id, f.created_at AS saved_at, (pl.id IS NOT NULL) AS available,
                                              pl.public_code, pl.title, pl.brand, pl.model, pl.version, pl.year, pl.km, pl.price_amount,
                                              pl.currency, pl.locality, pl.province, pl.cover_url,
                                              f.price_at_save, f.currency_at_save::text AS currency_at_save,
                                              (pl.id IS NOT NULL AND f.price_at_save IS NOT NULL AND pl.currency::text = f.currency_at_save::text
                                               AND pl.price_amount < f.price_at_save) AS price_dropped,
                                              CASE WHEN pl.id IS NOT NULL AND pl.currency::text = f.currency_at_save::text AND pl.price_amount < f.price_at_save
                                                   THEN f.price_at_save - pl.price_amount END AS price_drop_amount
                                         FROM app.favorites f LEFT JOIN api_public.listings pl ON pl.id = f.listing_id
                                        WHERE f.user_id = :u ORDER BY f.created_at DESC""", {"u": user.id})}


@router.put("/favorites/{listing_id}", status_code=201)
def add_favorite(listing_id: UUID, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.FAVORITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        res = conn.execute(text("INSERT INTO app.favorites (user_id, listing_id) VALUES (:u, :l) ON CONFLICT DO NOTHING"), {"u": user.id, "l": listing_id})
    if res.rowcount:
        track("listing_favorite", user.ctx, user.id, listing_id=listing_id)
    return {"ok": True}


@router.delete("/favorites/{listing_id}")
def remove_favorite(listing_id: UUID, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.FAVORITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        res = conn.execute(text("DELETE FROM app.favorites WHERE user_id = :u AND listing_id = :l"), {"u": user.id, "l": listing_id})
    if res.rowcount:
        track("listing_unfavorite", user.ctx, user.id, listing_id=listing_id)
    return {"ok": True}


# --------------------------------------------------------------------------- notificaciones
@router.get("/notifications")
def notifications(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, """SELECT id, type_code, category::text AS category, title, body, entity_type, entity_id, action_path,
                                              read_at, created_at FROM app.notifications WHERE user_id = :u ORDER BY created_at DESC LIMIT 100""",
                              {"u": user.id})}


@router.post("/notifications/read-all")
def read_all(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        conn.execute(text("UPDATE app.notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL"), {"u": user.id})
    return {"ok": True}


@router.post("/notifications/{notification_id}/read")
def read_one(notification_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        conn.execute(text("UPDATE app.notifications SET read_at = coalesce(read_at, now()) WHERE id = :n AND user_id = :u"),
                     {"n": notification_id, "u": user.id})
    return {"ok": True}


# --------------------------------------------------------------------------- agencias
class AgencyIn(StrictModel):
    legal_name: Annotated[str, StringConstraints(min_length=2, max_length=150)]
    trade_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    cuit: Annotated[str, StringConstraints(pattern=r"^\d{2}-?\d{8}-?\d$")]
    tax_condition: Literal["responsable_inscripto", "monotributo", "exento"] | None = None
    # Rubro de la cuenta comercial. "Concesionaria oficial" lo asigna solo el staff. No se cambia después.
    kind: Literal["agency", "parts_store", "service_provider", "company"] = "agency"
    geo_area_id: UUID
    phone_e164: PhoneE164 | None = None
    whatsapp_e164: PhoneE164 | None = None
    email: EmailStr | None = None
    website_url: Annotated[str, StringConstraints(max_length=200, pattern=r"^https://\S+$")] | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @field_validator("legal_name", "trade_name", "description")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)


def _slugify(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:50] or "agencia"


@router.post("/agencies", status_code=201)
def create_agency(body: AgencyIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    d = body.model_dump()
    d["cuit"] = re.sub(r"\D", "", d["cuit"])
    with unit_of_work("app", user.id, user.ctx) as conn:
        base = _slugify(d["trade_name"])
        slug = base
        for i in range(2, 50):
            if not scalar(conn, "SELECT app.agency_slug_taken(:s)", {"s": slug}):
                break
            slug = f"{base}-{i}"
        aid = scalar(conn, """INSERT INTO app.agencies (slug, legal_name, trade_name, cuit, tax_condition, geo_area_id, phone_e164, whatsapp_e164,
                                 email, website_url, description, created_by, kind)
                              VALUES (:slug, :legal_name, :trade_name, :cuit, CAST(:tax_condition AS app.tax_condition), :geo_area_id, :phone_e164,
                                 :whatsapp_e164, :email, :website_url, :description, :u, CAST(:kind AS app.agency_kind)) RETURNING id""", {**d, "slug": slug, "u": user.id})
        return row(conn, "SELECT id, slug, trade_name, status::text AS status, kind::text AS kind FROM app.agencies WHERE id = :a", {"a": aid})


@router.get("/agencies")
def my_agencies(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        items = rows(conn, """SELECT a.id, a.slug, a.trade_name, a.legal_name, a.cuit, a.status::text AS status, a.status_reason,
                                     a.kind::text AS kind, m.role::text AS member_role,
                                     (SELECT v.status::text FROM app.verifications v WHERE v.subject_agency_id = a.id ORDER BY v.created_at DESC LIMIT 1) AS verification_status
                                FROM app.agency_members m JOIN app.agencies a ON a.id = m.agency_id
                               WHERE m.user_id = :u AND m.status = 'active' ORDER BY a.trade_name""", {"u": user.id})
        for a in items:
            a["usage"] = plan_usage(conn, user.id, a["id"])
            a["verification_state"] = scalar(conn, "SELECT app.agency_verification_state(:a)", {"a": a["id"]})
            # Inventario = todo lo que la agencia tiene cargado y no vendió ni borró; publicadas = lo que cuenta para el plan
            a["inventory_total"] = scalar(conn, "SELECT count(*) FROM app.listings WHERE agency_id = :a AND status NOT IN ('sold','deleted')", {"a": a["id"]})
        return {"items": items}


@router.post("/agencies/{agency_id}/verification", status_code=201)
def request_agency_verification(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        set_reason(conn, "Solicitud de verificación de cuenta comercial")
        if not scalar(conn, "SELECT app.app_is_agency_member(:a, 'owner', 'admin')", {"a": agency_id}):
            raise err(403, "NO_AUTORIZADO", "Solo el titular o un administrador de la agencia puede pedir la verificación.")
        # Casas de repuestos: verificación presencial con su propio checklist (y la base exige el pago aprobado antes)
        kind = scalar(conn, "SELECT kind::text FROM app.agencies WHERE id = :a", {"a": agency_id})
        prod = scalar(conn, "SELECT id FROM app.verification_products WHERE code = :c AND status = 'active'",
                      {"c": "parts_store" if kind == "parts_store" else "agency"})
        if not prod:
            raise err(503, "VERIFICACION_NO_DISPONIBLE", "La verificación todavía no está habilitada.")
        if scalar(conn, "SELECT 1 FROM app.verifications WHERE subject_agency_id = :a AND status IN ('pending','review')", {"a": agency_id}):
            raise err(409, "SOLICITUD_EXISTENTE", "Ya hay una solicitud de verificación en curso.")
        vid = scalar(conn, """INSERT INTO app.verifications (product_id, subject_agency_id, requested_by, checklist)
                              SELECT :p, :a, :u, checklist_template FROM app.verification_products WHERE id = :p RETURNING id""",
                     {"p": prod, "a": agency_id, "u": user.id})
        return {"id": vid, "status": "pending"}


# --------------------------------------------------------------------------- perfil e inventario de la agencia
Url = Annotated[str, StringConstraints(max_length=200, pattern=r"^https://\S+$")]


class AgencyPatch(StrictModel):
    trade_name: Annotated[str, StringConstraints(min_length=2, max_length=80)] | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    phone_e164: PhoneE164 | None = None
    whatsapp_e164: PhoneE164 | None = None
    email: EmailStr | None = None
    website_url: Url | None = None
    store_url: Url | None = None
    instagram_url: Annotated[str, StringConstraints(max_length=200, pattern=r"^https://(www\.)?instagram\.com/\S+$")] | None = None
    facebook_url: Annotated[str, StringConstraints(max_length=200, pattern=r"^https://(www\.|m\.)?facebook\.com/\S+$")] | None = None
    tiktok_url: Annotated[str, StringConstraints(max_length=200, pattern=r"^https://(www\.)?tiktok\.com/@\S+$")] | None = None
    youtube_url: Annotated[str, StringConstraints(max_length=200, pattern=r"^https://(www\.)?youtube\.com/\S+$")] | None = None
    geo_area_id: UUID | None = None

    @field_validator("trade_name", "description")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)


AGENCY_COLS = """a.id, a.slug, a.trade_name, a.legal_name, a.cuit, a.status::text AS status, a.description, a.phone_e164, a.whatsapp_e164,
                 a.email::text AS email, a.website_url, a.store_url, a.instagram_url, a.facebook_url, a.tiktok_url, a.youtube_url,
                 a.geo_area_id, g.name AS locality, app.agency_verification_state(a.id) AS verification_state"""


def _agency_admin(conn, agency_id: UUID) -> None:
    if not scalar(conn, "SELECT app.app_is_agency_member(:a, 'owner', 'admin')", {"a": agency_id}):
        raise err(403, "NO_AUTORIZADO", "Solo el titular o un administrador de la agencia puede cambiar estos datos.")


@router.get("/agencies/{agency_id}")
def my_agency(agency_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
            raise err(404, "NO_ENCONTRADA", "La agencia no existe o no sos miembro.")
        a = row(conn, f"SELECT {AGENCY_COLS} FROM app.agencies a JOIN app.geo_areas g ON g.id = a.geo_area_id WHERE a.id = :a", {"a": agency_id})
        a["usage"] = plan_usage(conn, user.id, agency_id)
        a["inventory"] = {r["status"]: r["n"] for r in rows(conn, """SELECT status::text AS status, count(*) AS n FROM app.listings
                                                                    WHERE agency_id = :a AND status NOT IN ('deleted') GROUP BY 1""", {"a": agency_id})}
        return a


@router.patch("/agencies/{agency_id}")
def patch_agency(agency_id: UUID, body: AgencyPatch, user: CurrentUser = Depends(current_user)):
    data = body.model_dump(exclude_unset=True)
    for k in list(data):
        if data[k] == "":
            data[k] = None
    with unit_of_work("app", user.id, user.ctx, reason="Edición del perfil de la agencia") as conn:
        _agency_admin(conn, agency_id)
        if data:
            conn.execute(text(f"UPDATE app.agencies SET {', '.join(f'{k} = :{k}' for k in data)} WHERE id = :id"), {**data, "id": agency_id})
    return my_agency(agency_id, user)


@router.get("/agencies/{agency_id}/stats")
def agency_stats(agency_id: UUID, days: Literal[7, 30, 90] = 30, user: CurrentUser = Depends(current_user)):
    """Métricas reales de la agencia: por publicación (vistas, contactos, favoritos) y clics a canales externos."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
            raise err(404, "NO_ENCONTRADA", "La agencia no existe o no sos miembro.")
        per = rows(conn, """SELECT l.id, l.public_code, l.title, l.status::text AS status,
                                   coalesce(sum(s.views), 0) AS views, coalesce(sum(s.contacts + s.contact_reveals), 0) AS contacts,
                                   coalesce(sum(s.shares), 0) AS shares, app.listing_favorites_count(l.id) AS favorites
                              FROM app.listings l LEFT JOIN app.listing_stats_daily s ON s.listing_id = l.id AND s.day > current_date - :d
                             WHERE l.agency_id = :a AND l.status NOT IN ('draft','deleted')
                             GROUP BY l.id ORDER BY l.updated_at DESC""", {"a": agency_id, "d": days})
    with unit_of_work("worker", None, user.ctx) as w:   # analytics_events solo lo lee staff/worker: acá se filtra por la agencia
        clicks = {r["channel"]: r["n"] for r in rows(w, """SELECT properties->>'channel' AS channel, count(*) AS n FROM app.analytics_events
                                                          WHERE agency_id = :a AND event_name = 'external_click' AND occurred_at > now() - make_interval(days => :d)
                                                          GROUP BY 1""", {"a": agency_id, "d": days})}
        profile_views = scalar(w, """SELECT count(*) FROM app.analytics_events WHERE agency_id = :a AND event_name = 'agency_view'
                                      AND occurred_at > now() - make_interval(days => :d)""", {"a": agency_id, "d": days})
    totals = {k: sum(int(p[k] or 0) for p in per) for k in ("views", "contacts", "shares", "favorites")}
    totals["profile_views"] = profile_views
    totals["external_clicks"] = sum(clicks.values())
    return {"days": days, "totals": totals, "external_clicks": clicks, "listings": per, "has_data": any(totals.values()),
            "note": "Eventos reales; los totales por publicación se agregan cada pocos minutos. Sin datos suficientes no se estima nada."}
