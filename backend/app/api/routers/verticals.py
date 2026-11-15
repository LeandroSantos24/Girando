"""Fase 4 · Verticales: Taxis y permisos, Servicios, Repuestos y Empleos.

Una sola API para las cuatro secciones (`posts` + detalle tipado por vertical). Cada sección
tiene sus propios filtros, que salen SIEMPRE de datos estructurados.
La base hace cumplir: quién puede publicar en cada rubro, el cupo gratis compartido del
particular, el candado de repuestos (pago + verificación) y la máquina de estados.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import Field, StringConstraints, field_validator, model_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, current_user, optional_user, request_ctx, require_roles
from app.core import ratelimit
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.core.middleware import client_ip
from app.integrations import NotConfigured
from app.schemas.common import StrictModel, clean_text
from app.services.analytics import track
from app.services.media import MAX_BYTES, CloudinaryImageStorage, get_storage

router = APIRouter(prefix="/api", tags=["verticales · fase 4"])
MOD = require_roles("moderator", "admin")

Vertical = Literal["taxi", "service", "part", "job"]
Fuel = Literal["gasoline", "diesel", "cng", "gasoline_cng", "hybrid", "plugin_hybrid", "electric", "other"]
VehicleType = Literal["car", "light_truck", "van", "truck", "motorcycle", "atv", "other"]
ServiceCategory = Literal["tow", "auto_paperwork", "insurance_broker", "freight", "cargo_transport", "passenger_transport", "mechanic",
                          "tire_shop", "auto_electrician", "body_paint", "car_wash", "cng", "vtv_rto", "other"]
PartCategory = Literal["engine", "transmission", "brakes", "suspension", "electrical", "body", "interior", "tires_wheels", "lubricants",
                       "cooling", "exhaust", "lighting", "accessories", "other"]
JobRole = Literal["driver", "mechanic", "salesperson", "administrative", "dispatcher", "logistics", "body_painter", "auto_electrician",
                  "tire_fitter", "car_washer", "other"]
LicenseClass = Literal["A", "A1", "A2", "A3", "B", "B1", "B2", "C", "C1", "C2", "C3", "D", "D1", "D2", "D3", "D4", "E", "E1", "E2", "F", "G", "G1", "G2", "G3"]
Money = Annotated[Decimal, Field(gt=0, lt=Decimal("100000000000"), max_digits=14, decimal_places=2)]


# --------------------------------------------------------------------------- DTOs
class TaxiDetail(StrictModel):
    offer_kind: Literal["taxi_with_permit", "permit_only", "vehicle_only"]
    service_type: Literal["taxi", "remis"] = "taxi"
    permit_number: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9 ./-]{1,20}$")] | None = None
    permit_holder_declared: Annotated[str, StringConstraints(max_length=120)] | None = None
    version_id: UUID | None = None
    vehicle_year: Annotated[int, Field(ge=1980, le=2100)] | None = None
    fuel: Fuel | None = None
    has_cng: bool = False
    has_meter: bool = False
    has_gps: bool = False
    equipment: Annotated[list[Annotated[str, StringConstraints(min_length=2, max_length=40)]], Field(max_length=15)] = []
    permit_price: Money | None = None
    vehicle_price: Money | None = None
    includes_driver_work: bool = False

    @model_validator(mode="after")
    def _shape(self):
        if self.offer_kind == "permit_only" and (self.version_id or self.vehicle_year or self.vehicle_price):
            raise ValueError("Un permiso sin vehículo no lleva datos ni precio de vehículo")
        if self.offer_kind == "vehicle_only" and (self.permit_number or self.permit_price or self.permit_holder_declared):
            raise ValueError("Un vehículo apto taxi no lleva número ni precio de permiso")
        if self.offer_kind != "vehicle_only" and not self.permit_number:
            raise ValueError("Indicá el número de permiso declarado")
        if self.offer_kind != "permit_only" and not (self.version_id and self.vehicle_year):
            raise ValueError("Elegí el vehículo del catálogo y su año")
        return self


class ServiceDetail(StrictModel):
    category: ServiceCategory
    coverage_note: Annotated[str, StringConstraints(max_length=300)] | None = None
    open_24h: bool = False
    at_home: bool = False
    vehicle_types: Annotated[list[VehicleType], Field(max_length=7)] = []
    license_number: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9 ./-]{1,30}$")] | None = None

    @model_validator(mode="after")
    def _license(self):
        if self.category == "insurance_broker" and not self.license_number:
            raise ValueError("Un productor asesor de seguros tiene que informar su matrícula de la SSN")
        return self


class PartDetail(StrictModel):
    category: PartCategory
    condition: Literal["new", "used"] = "new"
    brand_id: UUID | None = None
    model_id: UUID | None = None
    year_from: Annotated[int, Field(ge=1950, le=2100)] | None = None
    year_to: Annotated[int, Field(ge=1950, le=2100)] | None = None
    part_number: Annotated[str, StringConstraints(max_length=60)] | None = None
    part_brand: Annotated[str, StringConstraints(max_length=60)] | None = None
    in_stock: bool = True

    @model_validator(mode="after")
    def _shape(self):
        if self.model_id and not self.brand_id:
            raise ValueError("Elegí la marca del vehículo")
        if self.year_from and self.year_to and self.year_to < self.year_from:
            raise ValueError("El rango de años es inválido")
        return self


class JobDetail(StrictModel):
    role: JobRole
    role_detail: Annotated[str, StringConstraints(max_length=80)] | None = None
    license_required: bool = False
    license_classes: Annotated[list[LicenseClass], Field(max_length=8)] = []
    workday: Literal["full_time", "part_time", "shifts", "per_trip"] = "full_time"
    modality: Literal["onsite", "on_route", "hybrid", "remote"] = "onsite"
    salary_min: Money | None = None
    salary_max: Money | None = None
    vacancies: Annotated[int, Field(ge=1, le=500)] = 1

    @model_validator(mode="after")
    def _shape(self):
        if self.license_classes and not self.license_required:
            raise ValueError("Marcá que el puesto requiere licencia")
        if self.salary_min and self.salary_max and self.salary_max < self.salary_min:
            raise ValueError("El rango salarial es inválido")
        return self


DETAIL_MODELS = {"taxi": TaxiDetail, "service": ServiceDetail, "part": PartDetail, "job": JobDetail}
DETAIL_TABLES = {"taxi": "taxi_posts", "service": "service_posts", "part": "part_posts", "job": "job_posts"}
DETAIL_CASTS = {
    "taxi": {"offer_kind": "app.taxi_offer_kind", "service_type": "app.taxi_service_type", "fuel": "app.fuel_type", "equipment": "text[]"},
    "service": {"category": "app.service_category", "vehicle_types": "app.vehicle_type[]"},
    "part": {"category": "app.part_category", "condition": "app.vehicle_condition"},
    "job": {"role": "app.job_role", "workday": "app.job_workday", "modality": "app.job_modality", "license_classes": "text[]"},
}


class PostFields(StrictModel):
    geo_area_id: UUID | None = None
    title: Annotated[str, StringConstraints(max_length=90)] | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    price_amount: Money | None = None
    currency: Literal["ARS", "USD"] | None = None
    details: dict | None = None

    @field_validator("title", "description")
    @classmethod
    def _c(cls, v):
        return clean_text(v)


class PostCreate(PostFields):
    vertical: Vertical
    agency_id: UUID | None = None


class TransitionIn(StrictModel):
    to: Literal["pending", "draft", "paused", "sold", "deleted"]


def _parse_details(vertical: str, raw: dict | None):
    if raw is None:
        return None
    try:
        return DETAIL_MODELS[vertical].model_validate(raw).model_dump()
    except ValueError as e:
        msg = e.errors()[0]["msg"].removeprefix("Value error, ") if hasattr(e, "errors") else str(e)
        raise err(422, "DATO_INVALIDO", msg) from None


def _save_details(conn, vertical: str, post_id, d: dict) -> None:
    casts = DETAIL_CASTS[vertical]
    cols = list(d)
    vals = ", ".join(f"CAST(:{k} AS {casts[k]})" if k in casts else f":{k}" for k in cols)
    sets = ", ".join(f"{k} = EXCLUDED.{k}" for k in cols)
    conn.execute(text(f"""INSERT INTO app.{DETAIL_TABLES[vertical]} (post_id, {", ".join(cols)}) VALUES (:post_id, {vals})
                          ON CONFLICT (post_id) DO UPDATE SET {sets}"""), {**d, "post_id": post_id})


PRIVATE_SQL = """SELECT p.id, p.public_code, p.vertical::text AS vertical, p.agency_id, a.trade_name AS agency_name, p.geo_area_id, g.name AS locality,
       p.title, p.description, p.price_amount, p.currency::text AS currency, p.status::text AS status, p.status_reason, p.submitted_at,
       p.published_at, p.expires_at, p.created_at, p.updated_at,
       coalesce(to_jsonb(t) - 'post_id', to_jsonb(s) - 'post_id', to_jsonb(r) - 'post_id', to_jsonb(j) - 'post_id') AS details,
       (SELECT jsonb_agg(jsonb_build_object('id', i.id, 'url', i.secure_url, 'position', i.position, 'is_cover', i.is_cover) ORDER BY i.position)
          FROM app.post_images i WHERE i.post_id = p.id AND i.status = 'active') AS images
  FROM app.posts p
  LEFT JOIN app.agencies a ON a.id = p.agency_id LEFT JOIN app.geo_areas g ON g.id = p.geo_area_id
  LEFT JOIN app.taxi_posts t ON t.post_id = p.id LEFT JOIN app.service_posts s ON s.post_id = p.id
  LEFT JOIN app.part_posts r ON r.post_id = p.id LEFT JOIN app.job_posts j ON j.post_id = p.id"""
EDITABLE = ("draft", "requires_changes", "rejected", "paused", "expired")


def _private(conn, post_id) -> dict:
    d = row(conn, PRIVATE_SQL + " WHERE p.id = :p", {"p": post_id})
    if not d:
        raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
    d["images"] = d["images"] or []
    return d


# --------------------------------------------------------------------------- mis publicaciones
@router.get("/me/posts")
def my_posts(vertical: Vertical | None = None, agency_id: UUID | None = None, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, PRIVATE_SQL + """ WHERE p.status <> 'deleted' AND app.can_manage_listing(p.owner_user_id, p.agency_id)
                                                        AND (CAST(:v AS text) IS NULL OR p.vertical::text = :v)
                                                        AND (CAST(:a AS uuid) IS NULL OR p.agency_id = :a)
                                                      ORDER BY p.updated_at DESC LIMIT 200""", {"v": vertical, "a": agency_id})}


@router.post("/me/posts", status_code=201)
def create_post(body: PostCreate, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_CREATE_USER, str(user.id))
    details = _parse_details(body.vertical, body.details)
    with unit_of_work("app", user.id, user.ctx, reason="Alta de publicación") as conn:
        pid = scalar(conn, """INSERT INTO app.posts (vertical, owner_user_id, agency_id, created_by, geo_area_id, title, description, price_amount, currency)
                              VALUES (CAST(:v AS app.post_vertical), :u, :a, :u, :g, coalesce(:t, ''), :d, :p, CAST(coalesce(:c, 'ARS') AS app.currency_code))
                              RETURNING id""", {"v": body.vertical, "u": user.id, "a": body.agency_id, "g": body.geo_area_id, "t": body.title,
                                                "d": body.description, "p": body.price_amount, "c": body.currency})
        if details is not None:
            _save_details(conn, body.vertical, pid, details)
        return _private(conn, pid)


@router.get("/me/posts/{post_id}")
def my_post(post_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return _private(conn, post_id)


@router.patch("/me/posts/{post_id}")
def update_post(post_id: UUID, body: PostFields, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    d = body.model_dump(exclude_unset=True)
    with unit_of_work("app", user.id, user.ctx, reason="Edición de publicación") as conn:
        cur = row(conn, "SELECT status::text AS status, vertical::text AS vertical FROM app.posts WHERE id = :p AND app.can_manage_post_id(id)", {"p": post_id})
        if not cur:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        if cur["status"] == "published":
            if set(d) - {"price_amount"}:       # publicada: solo el precio (lo demás pasaría sin moderación)
                raise err(409, "CAMPO_NO_EDITABLE", "Con la publicación activa solo podés cambiar el precio. Pausala para editar el resto.")
        elif cur["status"] not in EDITABLE:
            raise err(409, "CAMPO_NO_EDITABLE", "La publicación no se puede editar en este estado.")
        details = _parse_details(cur["vertical"], d.pop("details", None))
        if d:
            casts = {"currency": "app.currency_code"}
            sets = ", ".join("title = coalesce(:title, '')" if k == "title" else (f"{k} = CAST(:{k} AS {casts[k]})" if k in casts else f"{k} = :{k}") for k in d)
            conn.execute(text(f"UPDATE app.posts SET {sets} WHERE id = :id"), {**d, "id": post_id})
        if details is not None:
            _save_details(conn, cur["vertical"], post_id, details)
        return _private(conn, post_id)


@router.post("/me/posts/{post_id}/transition")
def transition_post(post_id: UUID, body: TransitionIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.LISTING_WRITE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx, reason=f"Publicación → {body.to}") as conn:
        if not scalar(conn, "SELECT app.can_manage_post_id(:p)", {"p": post_id}):
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        conn.execute(text("UPDATE app.posts SET status = CAST(:s AS app.listing_status) WHERE id = :p"), {"s": body.to, "p": post_id})
        return _private(conn, post_id)


@router.post("/me/posts/{post_id}/images", status_code=201)
async def upload_post_image(post_id: UUID, file: UploadFile = File(...), user: CurrentUser = Depends(current_user)):
    """Hasta 4 fotos por publicación. Mismo validador de imágenes que los vehículos. No acepta documentos."""
    ratelimit.hit(ratelimit.IMAGE_UPLOAD_USER, str(user.id))
    data = await file.read(MAX_BYTES + 1)
    try:
        storage = get_storage()
    except NotConfigured as e:
        raise err(503, "ALMACENAMIENTO_NO_CONFIGURADO", str(e)) from None
    if isinstance(storage, CloudinaryImageStorage):
        raise err(501, "PENDIENTE_CLOUDINARY", "La subida directa a Cloudinary para estas secciones se habilita junto con las credenciales.")
    with unit_of_work("app", user.id, user.ctx) as conn:
        st = scalar(conn, "SELECT status::text FROM app.posts WHERE id = :p AND app.can_manage_post_id(id)", {"p": post_id})
        if st is None:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        if st not in EDITABLE:
            raise err(409, "CAMPO_NO_EDITABLE", "No se pueden cambiar las fotos en este estado.")
        if scalar(conn, "SELECT count(*) FROM app.post_images WHERE post_id = :p AND status = 'active'", {"p": post_id}) >= 4:
            raise err(409, "MAXIMO_FOTOS", "Máximo 4 fotos por publicación.")
    stored = storage.save(post_id, data)
    try:
        with unit_of_work("app", user.id, user.ctx) as conn:
            pos = scalar(conn, """SELECT min(n) FROM generate_series(0, 3) n WHERE n NOT IN
                                  (SELECT position FROM app.post_images WHERE post_id = :p AND status = 'active')""", {"p": post_id})
            conn.execute(text("""INSERT INTO app.post_images (post_id, public_id, secure_url, storage_provider, position, is_cover, width, height, bytes, uploaded_by)
                                 VALUES (:p, :pid, :url, CAST(:prov AS app.image_storage_provider), :pos,
                                         NOT EXISTS (SELECT 1 FROM app.post_images WHERE post_id = :p AND status = 'active' AND is_cover),
                                         :w, :h, :b, :u)"""),
                         {"p": post_id, "pid": stored.public_id, "url": stored.secure_url, "prov": stored.provider, "pos": pos,
                          "w": stored.width, "h": stored.height, "b": stored.bytes, "u": user.id})
            return _private(conn, post_id)
    except Exception:
        storage.delete(stored.public_id)
        raise


@router.delete("/me/posts/{post_id}/images/{image_id}")
def delete_post_image(post_id: UUID, image_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT app.can_manage_post_id(:p)", {"p": post_id}):
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
        conn.execute(text("UPDATE app.post_images SET status = 'deleted', is_cover = false WHERE id = :i AND post_id = :p"), {"i": image_id, "p": post_id})
        conn.execute(text("""UPDATE app.post_images SET is_cover = true WHERE id = (SELECT id FROM app.post_images
                              WHERE post_id = :p AND status = 'active' ORDER BY position LIMIT 1)
                              AND NOT EXISTS (SELECT 1 FROM app.post_images WHERE post_id = :p AND status = 'active' AND is_cover)"""), {"p": post_id})
        return _private(conn, post_id)


# --------------------------------------------------------------------------- búsqueda pública por vertical
PUBLIC_COMMON = """id, public_code, vertical::text AS vertical, title, price_amount, currency::text AS currency, published_at, geo_area_id, locality, province,
    seller_type, agency_id, agency_name, agency_slug, agency_verified, cover_url"""
PUBLIC_BY_VERTICAL = {
    "taxi": """taxi_offer_kind::text AS offer_kind, taxi_service_type::text AS service_type, permit_number, permit_price, vehicle_price, vehicle_brand,
               vehicle_model, vehicle_version, vehicle_year, taxi_fuel::text AS fuel, has_cng, has_meter, has_gps, equipment, includes_driver_work, permit_verified""",
    "service": """service_category::text AS category, coverage_note, open_24h, at_home, vehicle_types::text[] AS vehicle_types, license_number, license_verified""",
    "part": """part_category::text AS category, part_condition::text AS condition, part_brand_id AS brand_id, part_vehicle_brand AS vehicle_brand,
               part_model_id AS model_id, part_vehicle_model AS vehicle_model, part_year_from AS year_from, part_year_to AS year_to, part_number, part_brand, in_stock""",
    "job": """job_role::text AS role, role_detail, license_required, license_classes, workday::text AS workday, modality::text AS modality,
              salary_min, salary_max, vacancies""",
}
SORTS = {"recientes": "published_at DESC, id", "precio_asc": "price_amount ASC NULLS LAST, id", "precio_desc": "price_amount DESC NULLS LAST, id",
         "anio_desc": "vehicle_year DESC NULLS LAST, id"}


def _post_filters(
    vertical: Vertical,
    q: Annotated[str | None, Query(max_length=100)] = None,
    geo_area_id: UUID | None = None,
    price_min: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    price_max: Annotated[Decimal | None, Query(ge=0, le=10**11)] = None,
    verified: bool = False,
    agency_id: UUID | None = None,
    # taxis
    service_type: Annotated[list[Literal["taxi", "remis"]] | None, Query()] = None,
    offer_kind: Annotated[list[Literal["taxi_with_permit", "permit_only", "vehicle_only"]] | None, Query()] = None,
    year_min: Annotated[int | None, Query(ge=1950, le=2100)] = None,
    year_max: Annotated[int | None, Query(ge=1950, le=2100)] = None,
    fuel: Annotated[list[Fuel] | None, Query()] = None,
    has_cng: bool = False,
    # servicios
    category: Annotated[list[str] | None, Query(max_length=14)] = None,
    open_24h: bool = False,
    at_home: bool = False,
    vehicle_type: Annotated[list[VehicleType] | None, Query()] = None,
    # repuestos
    brand_id: UUID | None = None,
    model_id: UUID | None = None,
    condition: Annotated[list[Literal["new", "used"]] | None, Query()] = None,
    # empleos
    role: Annotated[list[JobRole] | None, Query()] = None,
    license_required: bool | None = None,
    license_class: Annotated[list[LicenseClass] | None, Query()] = None,
    workday: Annotated[list[Literal["full_time", "part_time", "shifts", "per_trip"]] | None, Query()] = None,
    modality: Annotated[list[Literal["onsite", "on_route", "hybrid", "remote"]] | None, Query()] = None,
) -> dict:
    return {k: v for k, v in locals().items()}


def _where(f: dict, skip: str | None = None) -> tuple[str, dict]:
    v = f["vertical"]
    c, p = ["vertical::text = :vertical"], {"vertical": v}

    def add(key: str, cond: str, **params):
        if key != skip:
            c.append(cond)
            p.update(params)

    def anyof(key: str, col: str):
        if f.get(key):
            add(key, f"{col}::text = ANY(CAST(:{key} AS text[]))", **{key: list(f[key])})

    if f.get("q"):
        add("q", "search_vector @@ plainto_tsquery('spanish', app.f_unaccent(:q))", q=f["q"])
    if f.get("geo_area_id"):
        add("geo_area_id", """geo_area_id IN (WITH RECURSIVE t AS (SELECT id FROM app.geo_areas WHERE id = CAST(:geo AS uuid)
               UNION ALL SELECT g.id FROM app.geo_areas g JOIN t ON g.parent_id = t.id) SELECT id FROM t)""", geo=str(f["geo_area_id"]))
    if f.get("price_min") is not None:
        add("price", "price_amount >= :price_min", price_min=f["price_min"])
    if f.get("price_max") is not None:
        add("price", "price_amount <= :price_max", price_max=f["price_max"])
    if f.get("agency_id"):
        add("agency_id", "agency_id = CAST(:agency AS uuid)", agency=str(f["agency_id"]))
    if v == "taxi":
        anyof("service_type", "taxi_service_type")
        anyof("offer_kind", "taxi_offer_kind")
        anyof("fuel", "taxi_fuel")
        if f.get("year_min") is not None:
            add("year", "vehicle_year >= :year_min", year_min=f["year_min"])
        if f.get("year_max") is not None:
            add("year", "vehicle_year <= :year_max", year_max=f["year_max"])
        if f.get("has_cng"):
            add("has_cng", "has_cng")
        if f.get("verified"):
            add("verified", "permit_verified")       # sello real del equipo de Girando
    elif v == "service":
        anyof("category", "service_category")
        if f.get("open_24h"):
            add("open_24h", "open_24h")
        if f.get("at_home"):
            add("at_home", "at_home")
        if f.get("vehicle_type"):
            add("vehicle_type", "vehicle_types::text[] && CAST(:vehicle_type AS text[])", vehicle_type=list(f["vehicle_type"]))
        if f.get("verified"):
            add("verified", "(agency_verified OR license_verified)")
    elif v == "part":
        anyof("category", "part_category")
        anyof("condition", "part_condition")
        if f.get("brand_id"):      # un repuesto sin marca cargada es universal: aparece para cualquier vehículo
            add("brand_id", "(part_brand_id = CAST(:brand AS uuid) OR part_brand_id IS NULL)", brand=str(f["brand_id"]))
        if f.get("model_id"):
            add("model_id", "(part_model_id = CAST(:model AS uuid) OR part_model_id IS NULL)", model=str(f["model_id"]))
    else:
        anyof("role", "job_role")
        anyof("workday", "workday")
        anyof("modality", "modality")
        if f.get("license_required") is not None:
            add("license_required", "license_required = :lic_req", lic_req=f["license_required"])
        if f.get("license_class"):
            add("license_class", "license_classes && CAST(:lic AS text[])", lic=list(f["license_class"]))
    return " AND ".join(c), p


@router.get("/posts")
def search_posts(request: Request, f: dict = Depends(_post_filters), page: Annotated[int, Query(ge=1, le=500)] = 1,
                 page_size: Annotated[int, Query(ge=1, le=48)] = 24, sort: Literal["recientes", "precio_asc", "precio_desc", "anio_desc"] = "recientes"):
    ratelimit.hit(ratelimit.SEARCH_IP, client_ip(request))
    where, p = _where(f)
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        total = scalar(conn, f"SELECT count(*) FROM api_public.posts WHERE {where}", p)
        items = rows(conn, f"""SELECT {PUBLIC_COMMON}, {PUBLIC_BY_VERTICAL[f["vertical"]]} FROM api_public.posts WHERE {where}
                               ORDER BY {SORTS[sort]} LIMIT :lim OFFSET :off""", {**p, "lim": page_size, "off": (page - 1) * page_size})
        notice = scalar(conn, "SELECT value #>> '{}' FROM api_public.settings WHERE key = 'taxi.legal_notice'") if f["vertical"] == "taxi" else None
    return {"items": items, "total": total, "page": page, "page_size": page_size, "legal_notice": notice}


FACETS = {  # vertical → (clave del filtro, columna)
    "taxi": (("service_type", "taxi_service_type"), ("offer_kind", "taxi_offer_kind"), ("fuel", "taxi_fuel")),
    "service": (("category", "service_category"),),
    "part": (("category", "part_category"), ("condition", "part_condition")),
    "job": (("role", "job_role"), ("workday", "workday"), ("modality", "modality")),
}


@router.get("/posts/facets")
def post_facets(request: Request, f: dict = Depends(_post_filters)):
    """Contadores reales por opción (cada uno calculado sin su propio filtro, para poder cambiar de opción)."""
    ratelimit.hit(ratelimit.SEARCH_IP, client_ip(request))
    out: dict = {}
    with unit_of_work("anon", None, request_ctx(request)) as conn:
        for key, col in FACETS[f["vertical"]]:
            where, p = _where(f, skip=key)
            out[key] = rows(conn, f"""SELECT {col}::text AS value, count(*) AS count FROM api_public.posts
                                      WHERE {where} AND {col} IS NOT NULL GROUP BY 1 ORDER BY count DESC, 1""", p)
        where, p = _where(f, skip="geo_area_id")
        out["zone"] = rows(conn, f"""SELECT geo_area_id::text AS value, locality AS label, count(*) AS count FROM api_public.posts
                                     WHERE {where} GROUP BY 1, 2 ORDER BY count DESC, 2 LIMIT 40""", p)
        where, p = _where(f)
        out["total"] = scalar(conn, f"SELECT count(*) FROM api_public.posts WHERE {where}", p)
    return out


@router.get("/posts/{code}")
def post_detail(code: str, request: Request, user: CurrentUser | None = Depends(optional_user)):
    ctx = request_ctx(request)
    with unit_of_work("anon", None, ctx) as conn:
        base = row(conn, "SELECT id, vertical::text AS vertical FROM api_public.posts WHERE public_code = :c OR id::text = :c", {"c": code[:64]})
        if not base:
            raise err(404, "NO_ENCONTRADA", "La publicación no existe o ya no está disponible.")
        d = row(conn, f"""SELECT {PUBLIC_COMMON}, description, images, seller_display_name, {PUBLIC_BY_VERTICAL[base["vertical"]]}
                           FROM api_public.posts WHERE id = :i""", {"i": base["id"]})
        d["images"] = d["images"] or []
        d["agency"] = row(conn, """SELECT id, slug, trade_name, kind::text AS kind, is_verified, member_since, locality, street, street_number, business_hours
                                     FROM api_public.agencies WHERE id = :a""", {"a": d["agency_id"]}) if d["agency_id"] else None
        if base["vertical"] == "taxi":
            d["legal_notice"] = scalar(conn, "SELECT value #>> '{}' FROM api_public.settings WHERE key = 'taxi.legal_notice'")
            d["vehicle_age_note"] = scalar(conn, "SELECT value #>> '{}' FROM api_public.settings WHERE key = 'taxi.vehicle_age_note'")
    d["is_mine"] = False
    if user:
        with unit_of_work("app", user.id, ctx) as conn:
            d["is_mine"] = bool(scalar(conn, "SELECT app.can_manage_post_id(:p)", {"p": d["id"]}))
    track("post_view", ctx, None, agency_id=d["agency_id"], properties={"vertical": base["vertical"], "post": str(d["id"])})
    return d


# --------------------------------------------------------------------------- moderación
@router.get("/admin/posts")
def admin_posts(status: Literal["pending", "published", "paused", "requires_changes", "rejected", "expired", "sold", "draft"] = "pending",
                vertical: Vertical | None = None, user: CurrentUser = Depends(MOD)):
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"items": rows(conn, PRIVATE_SQL + """ WHERE p.status::text = :s AND (CAST(:v AS text) IS NULL OR p.vertical::text = :v)
                                                      ORDER BY coalesce(p.submitted_at, p.created_at) LIMIT 200""", {"s": status, "v": vertical}),
                "counts": rows(conn, "SELECT vertical::text AS vertical, count(*) AS pending FROM app.posts WHERE status = 'pending' GROUP BY 1")}


class ModIn(StrictModel):
    reason: Annotated[str, StringConstraints(min_length=3, max_length=500)] | None = None


POST_ACTIONS = {"approve": "published", "request_changes": "requires_changes", "reject": "rejected", "pause": "paused",
                "reactivate": "published", "delete": "deleted"}


@router.post("/admin/posts/{post_id}/{action}")
def moderate_post(post_id: UUID, action: Literal["approve", "request_changes", "reject", "pause", "reactivate", "delete"], body: ModIn,
                  user: CurrentUser = Depends(MOD)):
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    if action in ("request_changes", "reject", "pause", "delete") and not body.reason:
        raise err(422, "MOTIVO_OBLIGATORIO")
    reason = clean_text(body.reason)
    with unit_of_work("app", user.id, user.ctx, reason=reason or f"Moderación: {action}") as conn:
        if not scalar(conn, "SELECT 1 FROM app.posts WHERE id = :p", {"p": post_id}):
            raise err(404, "NO_ENCONTRADA", "Publicación inexistente.")
        conn.execute(text("UPDATE app.posts SET status = CAST(:s AS app.listing_status), status_reason = coalesce(:r, status_reason) WHERE id = :p"),
                     {"s": POST_ACTIONS[action], "r": reason, "p": post_id})
        return _private(conn, post_id)


class SealIn(StrictModel):
    verified: bool
    note: Annotated[str, StringConstraints(min_length=5, max_length=500)]


@router.post("/admin/posts/{post_id}/seal")
def seal_post(post_id: UUID, body: SealIn, user: CurrentUser = Depends(MOD)):
    """Sello "permiso verificado" (taxis) o "matrícula verificada" (servicios). Solo tras una comprobación real: la nota es obligatoria y queda en auditoría."""
    with unit_of_work("app", user.id, user.ctx, reason=f"Sello de verificación: {clean_text(body.note)}") as conn:
        v = scalar(conn, "SELECT vertical::text FROM app.posts WHERE id = :p", {"p": post_id})
        if v == "taxi":
            n = conn.execute(text("""UPDATE app.taxi_posts SET permit_verified_at = CASE WHEN :ok THEN now() END
                                      WHERE post_id = :p AND permit_number IS NOT NULL"""), {"ok": body.verified, "p": post_id}).rowcount
        elif v == "service":
            n = conn.execute(text("""UPDATE app.service_posts SET license_verified_at = CASE WHEN :ok THEN now() END
                                      WHERE post_id = :p AND license_number IS NOT NULL"""), {"ok": body.verified, "p": post_id}).rowcount
        else:
            raise err(422, "SIN_SELLO", "Esta sección no tiene sello por publicación (repuestos usa la verificación del comercio).")
        if not n:
            raise err(409, "SIN_DATO_DECLARADO", "La publicación no declara número de permiso o matrícula para verificar.")
        return _private(conn, post_id)
