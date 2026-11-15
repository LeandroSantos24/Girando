"""Búsqueda pública sobre api_public.listings (solo datos públicos, solo publicaciones visibles).

- Filtros = facetas sobre datos estructurados del catálogo (nunca sobre texto libre).
- El texto se interpreta primero contra el catálogo ("corsa 2014" → modelo Corsa, año 2014);
  lo que no coincide se busca en título y descripción (full text en español, sin tildes).
- Los patrocinados NO se mezclan acá: van por /api/sponsored con su rótulo.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.db import rows, scalar

SORTS = {
    "relevancia": "published_at DESC, id",
    "recientes": "published_at DESC, id",
    # precio normalizado a pesos con la última cotización BCRA; sin cotización, lo que está en dólares va al final
    "precio_asc": "coalesce(price_ars, CASE WHEN currency = 'ARS' THEN price_amount END) ASC NULLS LAST, price_amount ASC, id",
    "precio_desc": "coalesce(price_ars, CASE WHEN currency = 'ARS' THEN price_amount END) DESC NULLS LAST, price_amount DESC, id",
    "km_asc": "km ASC, id",
    "km_desc": "km DESC, id",
    "anio_desc": "year DESC, id",
    "anio_asc": "year ASC, id",
}

PUBLIC_COLS = """id, public_code, title, price_amount, currency, condition::text AS condition, km, year, color,
    brand_id, brand, model_id, model, generation, version_id, version, vehicle_type::text AS vehicle_type,
    body_type::text AS body_type, fuel::text AS fuel, transmission::text AS transmission, traction::text AS traction,
    doors, engine, locality, province, geo_area_id, seller_type, agency_id, agency_name, agency_slug,
    coalesce(agency_verified, false) AS agency_verified, coalesce(seller_identity_verified, false) AS seller_identity_verified,
    is_financeable, accepts_trade_in, published_at, cover_url, color_family, price_ars,
    EXISTS (SELECT 1 FROM api_public.listing_financing lf WHERE lf.listing_id = listings.id) AS has_financing"""


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def interpret_query(conn: Connection, q: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"brand_id": None, "brand": None, "model_id": None, "model": None, "year": None, "rest": []}
    if not q:
        return out
    tokens = [t for t in re.split(r"\s+", _norm(q)) if t][:8]
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.fullmatch(r"(19|20)\d{2}", t):
            out["year"] = int(t)
            i += 1
            continue
        if not out["brand_id"]:
            b = conn.execute(text(
                "SELECT DISTINCT brand_id AS id, brand AS name FROM api_public.catalog_versions WHERE lower(app.f_unaccent(brand)) = :t LIMIT 1"), {"t": t}).first()
            if b:
                out["brand_id"], out["brand"] = b.id, b.name
                i += 1
                continue
        if not out["model_id"]:
            # Modelos de varias palabras ("gol trend"): primero la frase de 2 tokens, después 1 token exacto o como primera palabra
            two = " ".join(tokens[i:i + 2]) if i + 1 < len(tokens) else None
            m = conn.execute(text(
                """SELECT model_id AS id, model AS name, lower(app.f_unaccent(model)) = :two AS used_two FROM api_public.catalog_versions
                   WHERE (lower(app.f_unaccent(model)) IN (:t, coalesce(:two, '')) OR lower(app.f_unaccent(model)) LIKE :t || ' %')
                     AND (CAST(:b AS uuid) IS NULL OR brand_id = CAST(:b AS uuid))
                   ORDER BY (lower(app.f_unaccent(model)) = :two) DESC, (lower(app.f_unaccent(model)) = :t) DESC, model LIMIT 1"""),
                {"t": t, "two": two, "b": str(out["brand_id"]) if out["brand_id"] else None}).first()
            if m:
                out["model_id"], out["model"] = m.id, m.name
                i += 2 if m.used_two else 1
                continue
        out["rest"].append(t)
        i += 1
    return out


def build_where(conn: Connection, f: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    interp = interpret_query(conn, f.get("q"))
    clauses, p = ["true"], {}

    def add(cond: str, **params):
        clauses.append(cond)
        p.update(params)

    brand_ids = list(f.get("brand_id") or [])
    model_ids = list(f.get("model_id") or [])
    if interp["brand_id"]:
        brand_ids.append(interp["brand_id"])
    if interp["model_id"]:
        model_ids.append(interp["model_id"])
    if brand_ids:
        add("brand_id = ANY(CAST(:brand_ids AS uuid[]))", brand_ids=[str(x) for x in brand_ids])
    if model_ids:
        add("model_id = ANY(CAST(:model_ids AS uuid[]))", model_ids=[str(x) for x in model_ids])
    year = interp["year"]
    if year:
        add("year = :year_exact", year_exact=year)
    for key, col, op in (("year_min", "year", ">="), ("year_max", "year", "<="), ("km_min", "km", ">="), ("km_max", "km", "<=")):
        if f.get(key) is not None:
            add(f"{col} {op} :{key}", **{key: f[key]})
    if f.get("price_min") is not None or f.get("price_max") is not None:
        # El rango se expresa en la moneda elegida y se compara contra el precio NORMALIZADO con la última cotización
        # BCRA (Com. A 3500). Sin cotización cargada no se mezclan monedas: solo entra lo publicado en esa moneda.
        # El precio que se muestra es siempre el que cargó el vendedor.
        p["price_currency"] = f.get("currency") or "ARS"
        p["usd_rate"] = scalar(conn, "SELECT rate_to_ars FROM api_public.exchange_rate WHERE currency = 'USD'")
        norm = """(CASE WHEN currency::text = :price_currency THEN price_amount
                        WHEN :price_currency = 'ARS' THEN price_ars
                        WHEN CAST(:usd_rate AS numeric) IS NOT NULL THEN price_amount / CAST(:usd_rate AS numeric) END)"""
        if f.get("price_min") is not None:
            add(f"{norm} >= :price_min", price_min=f["price_min"])
        if f.get("price_max") is not None:
            add(f"{norm} <= :price_max", price_max=f["price_max"])
    elif f.get("currency"):
        add("currency = CAST(:currency AS app.currency_code)", currency=f["currency"])
    for key, col in (("vehicle_type", "vehicle_type"), ("fuel", "fuel"), ("transmission", "transmission"),
                     ("body_type", "body_type"), ("traction", "traction"), ("condition", "condition")):
        vals = f.get(key) or []
        if vals:
            add(f"{col}::text = ANY(CAST(:{key} AS text[]))", **{key: list(vals)})
    if f.get("seller_type"):
        add("seller_type = ANY(CAST(:seller_type AS text[]))", seller_type=list(f["seller_type"]))
    if f.get("verified"):
        # Verificado = agencia con status 'verified' o particular con identidad verificada. Nunca por defecto.
        add("(coalesce(agency_verified, false) OR coalesce(seller_identity_verified, false))")
    if f.get("version_id"):
        add("version_id = ANY(CAST(:version_ids AS uuid[]))", version_ids=[str(x) for x in f["version_id"]])
    if f.get("color"):
        add("color_family = ANY(CAST(:colors AS text[]))", colors=list(f["color"]))
    if f.get("doors"):
        add("doors = ANY(CAST(:doors AS int[]))", doors=[int(x) for x in f["doors"]])
    if f.get("trade_in"):
        add("accepts_trade_in")
    if f.get("financeable"):
        # "Apto crédito": lo declaró el vendedor o tiene una oferta de financiación aprobada y vigente
        add("(is_financeable OR EXISTS (SELECT 1 FROM api_public.listing_financing lf WHERE lf.listing_id = listings.id))")
    fin = []
    if f.get("financing_entity_id"):
        fin.append("lf.entity_id = ANY(CAST(:fin_entities AS uuid[]))")
        p["fin_entities"] = [str(x) for x in f["financing_entity_id"]]
    if f.get("down_payment_max") is not None:      # "tengo hasta X de anticipo": alcanza para el anticipo mínimo de la oferta
        fin.append("lf.down_payment <= :down_payment_max")
        p["down_payment_max"] = f["down_payment_max"]
    if f.get("installment_max") is not None:       # cuota orientativa al plazo más largo; sin tasa informada no hay cuota y no entra
        fin.append("lf.installment_min <= :installment_max")
        p["installment_max"] = f["installment_max"]
    if fin:   # todas las condiciones las cumple UNA misma oferta
        clauses.append(f"EXISTS (SELECT 1 FROM api_public.listing_financing lf WHERE lf.listing_id = listings.id AND {' AND '.join(fin)})")
    if f.get("geo_area_id"):
        subtree = """geo_area_id IN (WITH RECURSIVE t AS (SELECT id FROM app.geo_areas WHERE id = CAST(:geo AS uuid)
               UNION ALL SELECT g.id FROM app.geo_areas g JOIN t ON g.parent_id = t.id) SELECT id FROM t)"""
        if f.get("radius_km"):
            # Radio desde el centro de la zona elegida (si la zona tiene coordenadas); la zona misma siempre entra
            add(f"""({subtree} OR EXISTS (SELECT 1 FROM app.geo_areas c WHERE c.id = CAST(:geo AS uuid) AND c.centroid_lat IS NOT NULL
                       AND listings.centroid_lat IS NOT NULL
                       AND 6371 * 2 * asin(sqrt(power(sin(radians(listings.centroid_lat - c.centroid_lat) / 2), 2)
                           + cos(radians(c.centroid_lat)) * cos(radians(listings.centroid_lat))
                           * power(sin(radians(listings.centroid_lng - c.centroid_lng) / 2), 2))) <= :radius_km))""",
                geo=str(f["geo_area_id"]), radius_km=f["radius_km"])
        else:
            add(subtree, geo=str(f["geo_area_id"]))
    if f.get("agency_id"):
        add("agency_id = CAST(:agency AS uuid)", agency=str(f["agency_id"]))
    if interp["rest"]:
        # Texto libre: título/descripción (FTS) o versión del catálogo ("highline", "4x4", "gnc")
        for n, tok in enumerate(interp["rest"][:5]):
            add(f"""(search_vector @@ plainto_tsquery('spanish', app.f_unaccent(:fts{n}))
                    OR lower(app.f_unaccent(coalesce(version, '') || ' ' || coalesce(engine, ''))) LIKE '%' || :fts{n} || '%')""", **{f"fts{n}": tok})
    return " AND ".join(clauses), p, interp


def search(conn: Connection, f: dict[str, Any], page: int, page_size: int, sort: str) -> dict[str, Any]:
    where, p, interp = build_where(conn, f)
    order = SORTS.get(sort, SORTS["relevancia"])
    total = scalar(conn, f"SELECT count(*) FROM api_public.listings WHERE {where}", p)  # where: solo placeholders ligados
    items = rows(conn, f"SELECT {PUBLIC_COLS} FROM api_public.listings WHERE {where} ORDER BY {order} LIMIT :lim OFFSET :off",
                 {**p, "lim": page_size, "off": (page - 1) * page_size})
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "interpretation": {k: interp[k] for k in ("brand", "model", "year")} | {"text": " ".join(interp["rest"]) or None}}


def facets(conn: Connection, f: dict[str, Any]) -> dict[str, Any]:
    """Opciones disponibles con su cantidad REAL según la selección actual (cada faceta se calcula sin su
    propio filtro, para poder cambiar de opción). Nunca aparece una combinación imposible ni un número estimado."""
    out = {}
    # (clave de salida, columna, etiqueta, filtros propios que se quitan)
    specs = (("brand", "brand_id", "brand", ("brand_id", "model_id", "version_id")), ("model", "model_id", "model", ("model_id", "version_id")),
             ("fuel", "fuel", None, ("fuel",)), ("transmission", "transmission", None, ("transmission",)),
             ("body_type", "body_type", None, ("body_type",)), ("traction", "traction", None, ("traction",)),
             ("vehicle_type", "vehicle_type", None, ("vehicle_type",)), ("condition", "condition", None, ("condition",)),
             ("seller_type", "seller_type", None, ("seller_type",)), ("color", "color_family", None, ("color",)),
             ("doors", "doors", None, ("doors",)), ("location", "geo_area_id", "locality", ("geo_area_id", "radius_km")))
    for key, col, label, own in specs:
        sub = {k: v for k, v in f.items() if k not in own}
        where, p, _ = build_where(conn, sub)
        name = f"{label}" if label else f"{col}::text"
        out[key] = rows(conn, f"""SELECT {col}::text AS value, {name} AS label, count(*) AS count
                                 FROM api_public.listings WHERE {where} AND {col} IS NOT NULL
                                 GROUP BY 1, 2 ORDER BY count DESC, 2 LIMIT 50""", p)
    # Versiones: solo cuando hay un modelo elegido (si no, la lista no sirve para nada)
    out["version"] = []
    if f.get("model_id"):
        where, p, _ = build_where(conn, {k: v for k, v in f.items() if k != "version_id"})
        out["version"] = rows(conn, f"""SELECT version_id::text AS value, version AS label, count(*) AS count
                                        FROM api_public.listings WHERE {where} GROUP BY 1, 2 ORDER BY count DESC, 2 LIMIT 60""", p)
    # Entidades con ofertas aprobadas y vigentes en las publicaciones que quedan
    where, p, _ = build_where(conn, {k: v for k, v in f.items() if k != "financing_entity_id"})
    out["financing_entity"] = rows(conn, f"""SELECT lf.entity_id::text AS value, lf.entity_name AS label, count(DISTINCT listings.id) AS count
                                              FROM api_public.listings JOIN api_public.listing_financing lf ON lf.listing_id = listings.id
                                             WHERE {where} AND lf.entity_id IS NOT NULL GROUP BY 1, 2 ORDER BY count DESC, 2 LIMIT 30""", p)
    where, p, _ = build_where(conn, f)
    agg = rows(conn, f"""SELECT count(*) AS total, min(year) AS year_min, max(year) AS year_max, min(km) AS km_min, max(km) AS km_max,
                                min(price_ars) AS price_ars_min, max(price_ars) AS price_ars_max,
                                count(*) FILTER (WHERE accepts_trade_in) AS trade_in,
                                count(*) FILTER (WHERE coalesce(agency_verified, false) OR coalesce(seller_identity_verified, false)) AS verified,
                                count(*) FILTER (WHERE is_financeable OR EXISTS (SELECT 1 FROM api_public.listing_financing lf WHERE lf.listing_id = listings.id)) AS financeable
                           FROM api_public.listings WHERE {where}""", p)[0]
    out["ranges"] = {k: agg[k] for k in ("year_min", "year_max", "km_min", "km_max", "price_ars_min", "price_ars_max")}
    out["flags"] = {k: agg[k] for k in ("total", "trade_in", "verified", "financeable")}
    return out


LIST_FILTERS = ("brand_id", "model_id", "version_id", "vehicle_type", "fuel", "transmission", "body_type", "traction", "condition",
                "seller_type", "color", "doors", "financing_entity_id")


def normalize_filters(raw: dict[str, Any]) -> dict[str, Any]:
    """Filtros guardados (búsquedas guardadas) → el mismo diccionario que arma la API pública. Los filtros
    guardados ya pasaron por la lista blanca de claves; acá solo se uniforman listas y se descarta lo vacío."""
    out: dict[str, Any] = {}
    for k, v in (raw or {}).items():
        if v in (None, "", [], False):
            continue
        out[k] = (v if isinstance(v, list) else [v]) if k in LIST_FILTERS else v
    out.pop("sort", None)
    return out
