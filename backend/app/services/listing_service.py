"""Publicaciones del usuario: crear/editar borrador, transiciones, fotos, contacto, venta.

El backend decide qué campos se pueden editar en cada estado. Las transiciones, el
límite del plan, las 6 fotos y la venta los garantiza además la base (triggers).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.db import row, rows, scalar
from app.core.errors import err

VEHICLE_FIELDS = ("version_id", "engine_id", "year", "color", "color_family", "fuel_override")
CATALOG_FIELDS = ("version_id", "engine_id", "year")
LISTING_FIELDS = ("km", "price_amount", "currency", "condition", "geo_area_id", "title", "description",
                  "is_financeable", "accepts_trade_in", "video_url")
CATALOG_EDITABLE = {"draft", "requires_changes", "rejected"}
CONTENT_EDITABLE = {"draft", "requires_changes", "rejected", "paused", "published", "expired"}

PRIVATE_LISTING_SQL = """
SELECT l.id, l.public_code, l.status::text AS status, l.status_reason, l.title, l.description, l.price_amount, l.currency::text AS currency,
       l.condition::text AS condition, l.km, l.geo_area_id, g.name AS locality, gp.name AS province, l.is_financeable, l.accepts_trade_in,
       l.video_url, l.agency_id, a.trade_name AS agency_name, l.created_at, l.updated_at, l.submitted_at, l.first_published_at, l.published_at,
       l.expires_at, l.paused_at, l.sold_at, l.renewal_count, l.vehicle_id,
       v.version_id, v.engine_id, v.year, v.color, v.color_family, v.fuel_override::text AS fuel_override,
       cv.brand_id, cv.brand, cv.model_id, cv.model, cv.generation_id, cv.generation, cv.version, cv.vehicle_type::text AS vehicle_type,
       cv.body_type::text AS body_type, cv.transmission::text AS transmission, cv.traction::text AS traction, cv.doors,
       e.name AS engine, coalesce(v.fuel_override, e.fuel)::text AS fuel,
       (SELECT secure_url FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active' AND i.is_cover) AS cover_url,
       (SELECT count(*) FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'active') AS photo_count,
       (SELECT s.id FROM app.sales s WHERE s.listing_id = l.id AND s.status = 'reported') AS sale_id,
       (SELECT min(purge_after) FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'purge_scheduled') AS photos_purge_after,
       EXISTS (SELECT 1 FROM app.listing_images i WHERE i.listing_id = l.id AND i.status = 'purged') AS photos_purged
  FROM app.listings l
  JOIN app.vehicles v ON v.id = l.vehicle_id
  LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id
  LEFT JOIN app.vehicle_engines e ON e.id = v.engine_id
  LEFT JOIN app.geo_areas g ON g.id = l.geo_area_id
  LEFT JOIN app.geo_areas gd ON gd.id = g.parent_id
  LEFT JOIN app.geo_areas gp ON gp.id = CASE WHEN g.level = 'department' THEN g.parent_id WHEN g.level = 'locality' THEN gd.parent_id END
  LEFT JOIN app.agencies a ON a.id = l.agency_id
"""


def _default_engine(conn: Connection, version_id) -> UUID | None:
    engines = rows(conn, """SELECT engine_id, is_default FROM app.vehicle_version_engines
                            WHERE version_id = :v AND status = 'active' ORDER BY is_default DESC""", {"v": version_id})
    if len(engines) == 1 or (engines and engines[0]["is_default"]):
        return engines[0]["engine_id"]
    return None


def get_private(conn: Connection, listing_id) -> dict:
    d = row(conn, PRIVATE_LISTING_SQL + " WHERE l.id = :id", {"id": listing_id})
    if not d:
        raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
    d["images"] = rows(conn, """SELECT id, secure_url AS url, storage_provider::text AS provider, kind::text AS kind, position, is_cover,
                                       width, height, bytes, format FROM app.listing_images
                                 WHERE listing_id = :id AND status = 'active' ORDER BY position""", {"id": listing_id})
    d["contact"] = row(conn, """SELECT phone_e164, show_phone, whatsapp_e164, show_whatsapp, email::text AS email, show_email
                                 FROM app.listing_contacts WHERE listing_id = :id""", {"id": listing_id})
    d["history"] = rows(conn, """SELECT from_status::text AS from_status, to_status::text AS to_status, reason, actor_type::text AS actor_type, created_at
                                  FROM app.listing_status_history WHERE listing_id = :id ORDER BY created_at""", {"id": listing_id})
    d["favorites"] = scalar(conn, "SELECT app.listing_favorites_count(:id)", {"id": listing_id})
    return d


def list_mine(conn: Connection, user_id, group: str, agency_id=None) -> list[dict]:
    groups = {"activas": ("draft", "pending", "published", "paused", "requires_changes"),
              "finalizadas": ("sold", "expired", "rejected", "deleted"),
              "todas": ("draft", "pending", "published", "paused", "requires_changes", "sold", "expired", "rejected")}
    sts = list(groups.get(group, groups["todas"]))
    where = "l.agency_id = :a" if agency_id else "l.owner_user_id = :u AND l.agency_id IS NULL"
    items = rows(conn, PRIVATE_LISTING_SQL + f" WHERE {where} AND l.status::text = ANY(:s) ORDER BY l.updated_at DESC",
                 {"u": user_id, "a": agency_id, "s": sts})
    ids = [i["id"] for i in items]
    stats = {r["listing_id"]: r for r in rows(conn, """SELECT listing_id, sum(views) AS views, sum(contacts) AS contacts, sum(favorites) - sum(unfavorites) AS favs
                                                        FROM app.listing_stats_daily WHERE listing_id = ANY(:ids) GROUP BY listing_id""", {"ids": ids})} if ids else {}
    for i in items:
        st = stats.get(i["id"])
        i["stats"] = {"views": int(st["views"]) if st else 0, "contacts": int(st["contacts"]) if st else 0,
                      "favorites": scalar(conn, "SELECT app.listing_favorites_count(:id)", {"id": i["id"]})}
    return items


def create(conn: Connection, user_id, data: dict) -> UUID:
    agency_id = data.get("agency_id")
    if agency_id and not scalar(conn, "SELECT app.app_is_agency_member(:a)", {"a": agency_id}):
        raise err(403, "NO_AUTORIZADO", "No sos miembro de esa agencia.")
    if data.get("version_id") and not data.get("engine_id"):
        data["engine_id"] = _default_engine(conn, data["version_id"])
    vid = scalar(conn, """INSERT INTO app.vehicles (owner_user_id, agency_id, version_id, engine_id, year, color, color_family, fuel_override)
                          VALUES (:u, :a, :ver, :eng, :y, :c, :cf, CAST(:f AS app.fuel_type)) RETURNING id""",
                 {"u": user_id, "a": agency_id, "ver": data.get("version_id"), "eng": data.get("engine_id"), "y": data.get("year"),
                  "c": data.get("color"), "cf": data.get("color_family"), "f": data.get("fuel_override")})
    lid = scalar(conn, """INSERT INTO app.listings (owner_user_id, agency_id, created_by, vehicle_id, geo_area_id, title, description,
                              price_amount, currency, condition, km, is_financeable, accepts_trade_in, video_url)
                          VALUES (:u, :a, :u, :v, :g, coalesce(:t, ''), :d, :p, CAST(coalesce(:cur, 'ARS') AS app.currency_code),
                              CAST(coalesce(:cond, 'used') AS app.vehicle_condition), :km, coalesce(:fin, false), coalesce(:ti, false), :vid)
                          RETURNING id""",
                 {"u": user_id, "a": agency_id, "v": vid, "g": data.get("geo_area_id"), "t": data.get("title"), "d": data.get("description"),
                  "p": data.get("price_amount"), "cur": data.get("currency"), "cond": data.get("condition"), "km": data.get("km"),
                  "fin": data.get("is_financeable"), "ti": data.get("accepts_trade_in"), "vid": data.get("video_url")})
    # Contacto por defecto: el del perfil (oculto salvo que el usuario haya elegido mostrarlo)
    prof = row(conn, "SELECT contact_phone_e164, contact_whatsapp_e164, show_phone_default FROM app.user_profiles WHERE user_id = :u", {"u": user_id})
    if prof and not agency_id:
        conn.execute(text("""UPDATE app.listing_contacts SET phone_e164 = CAST(:p AS text), whatsapp_e164 = CAST(:w AS text),
                                show_phone = (CAST(:show AS boolean) AND CAST(:p AS text) IS NOT NULL),
                                show_whatsapp = (CAST(:show AS boolean) AND CAST(:w AS text) IS NOT NULL) WHERE listing_id = :l"""),
                     {"p": prof["contact_phone_e164"], "w": prof["contact_whatsapp_e164"], "show": prof["show_phone_default"], "l": lid})
    return lid


def update(conn: Connection, listing_id, data: dict) -> None:
    cur = row(conn, "SELECT l.status::text AS status, l.vehicle_id FROM app.listings l WHERE l.id = :id FOR UPDATE", {"id": listing_id})
    if not cur:
        raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")
    st = cur["status"]
    changed_catalog = [k for k in CATALOG_FIELDS if k in data]
    if changed_catalog and st not in CATALOG_EDITABLE:
        raise err(409, "CAMPO_NO_EDITABLE", "Marca, modelo, versión y año solo se editan en borrador o al corregir una publicación.")
    if st not in CONTENT_EDITABLE:
        raise err(409, "CAMPO_NO_EDITABLE", "La publicación no se puede editar en este estado." if st != "pending"
                  else "Está en revisión. Si necesitás cambiar algo, retirala a borrador.")
    if "version_id" in data and data.get("version_id") and "engine_id" not in data:
        data["engine_id"] = _default_engine(conn, data["version_id"])
    if "version_id" in data and not data.get("version_id"):
        data["engine_id"] = None
    vset = {k: data[k] for k in VEHICLE_FIELDS if k in data}
    if vset:
        cols = ", ".join(f"{k} = CAST(:{k} AS app.fuel_type)" if k == "fuel_override" else f"{k} = :{k}" for k in vset)
        conn.execute(text(f"UPDATE app.vehicles SET {cols} WHERE id = :vid"), {**vset, "vid": cur["vehicle_id"]})
    lset = {k: data[k] for k in LISTING_FIELDS if k in data}
    if lset:
        casts = {"currency": "app.currency_code", "condition": "app.vehicle_condition"}
        parts = []
        for k in lset:
            if k == "title":
                parts.append("title = coalesce(:title, '')")
            elif k in casts:
                parts.append(f"{k} = CAST(:{k} AS {casts[k]})")
            else:
                parts.append(f"{k} = :{k}")
        conn.execute(text(f"UPDATE app.listings SET {', '.join(parts)} WHERE id = :lid"), {**lset, "lid": listing_id})


def transition(conn: Connection, listing_id, to: str) -> None:
    res = conn.execute(text("UPDATE app.listings SET status = CAST(:to AS app.listing_status) WHERE id = :id"), {"to": to, "id": listing_id})
    if res.rowcount == 0:
        raise err(404, "NO_ENCONTRADA", "La publicación no existe o no tenés acceso.")


def renew(conn: Connection, listing_id) -> None:
    res = conn.execute(text("UPDATE app.listings SET expires_at = now() WHERE id = :id AND status = 'published'"), {"id": listing_id})
    if res.rowcount == 0:
        raise err(409, "RENOVACION_NO_DISPONIBLE", "Solo se renuevan publicaciones activas.")


def register_sale(conn: Connection, listing_id, s: dict) -> UUID:
    return scalar(conn, """SELECT app.register_sale(:l, :d, :p, CAST(:c AS app.currency_code), CAST(:ch AS app.sale_channel),
                              :fin, CAST(:ft AS app.financing_type), :fa, CAST(:inst AS smallint), :plate, :notes, NULL)""",
                  {"l": listing_id, "d": s["sold_on"], "p": s["final_price"], "c": s["currency"], "ch": s["channel"], "fin": s["is_financed"],
                   "ft": s.get("financing_type"), "fa": s.get("financed_amount"), "inst": s.get("installments"),
                   "plate": s.get("plate"), "notes": s.get("notes")})


def sales_summary(conn: Connection, user_id) -> dict:
    """Estadísticas propias con la regla n >= stats.min_sample_size (3). Sin datos → se informa, no se inventa."""
    n_min = scalar(conn, "SELECT app.setting_int('stats.min_sample_size', 3)")
    base = """FROM app.sales s JOIN app.listings l ON l.id = s.listing_id JOIN app.vehicles v ON v.id = s.vehicle_id
              LEFT JOIN app.v_catalog_versions cv ON cv.version_id = v.version_id WHERE s.status = 'reported'"""
    items = rows(conn, f"""SELECT s.id, s.public_code, s.sold_on, s.final_price, s.currency::text AS currency, s.is_financed,
                                  s.financing_type::text AS financing_type, s.installments, s.channel::text AS channel, s.attributed_to_girando,
                                  cv.brand, cv.model, cv.version, v.year, l.km, l.price_amount AS listed_price, l.public_code AS listing_code,
                                  (s.sold_on - l.first_published_at::date) AS days_to_sell
                             {base} ORDER BY s.sold_on DESC""")
    n = len(items)
    ars = [i for i in items if i["currency"] == "ARS"]
    summary = {"count": n, "attributed": sum(1 for i in items if i["attributed_to_girando"]), "min_sample": n_min,
               "sample_sufficient": n >= n_min, "avg_price_ars": None, "avg_days_to_sell": None, "total_ars": None}
    if len(ars) >= n_min:
        summary["avg_price_ars"] = round(sum(i["final_price"] for i in ars) / len(ars))
        summary["total_ars"] = sum(i["final_price"] for i in ars)
    days = [i["days_to_sell"] for i in items if i["days_to_sell"] is not None]
    if len(days) >= n_min:
        summary["avg_days_to_sell"] = round(sum(days) / len(days))
    by_model: dict[str, list] = {}
    for i in items:
        by_model.setdefault(f"{i['brand']} {i['model']}", []).append(i)
    summary["by_model"] = [{"name": k, "count": len(v), "sample_sufficient": len(v) >= n_min,
                            "avg_price_ars": round(sum(x["final_price"] for x in v if x["currency"] == "ARS") / max(1, len([x for x in v if x["currency"] == "ARS"])))
                            if len([x for x in v if x["currency"] == "ARS"]) >= n_min else None} for k, v in by_model.items()]
    return {"summary": summary, "items": items}
