#!/usr/bin/env python3
"""Descarga provincias, departamentos y localidades de Argentina desde el dataset oficial Georef
(datos.gob.ar) y los deja versionados en backend/app/seeds/georef/.

    python3 scripts/georef_descargar.py            # o:  make georef

Fuente: API Georef, descarga de la base completa
  https://apis.datos.gob.ar/georef/api/v2.0/{provincias,departamentos,localidades}.json
  Documentación: https://www.argentina.gob.ar/georef/descarga-de-la-base-completa
  Licencia de los datos: Creative Commons Attribution 4.0 (Datos Argentina).

Salida (se versiona en Git; la carga `python -m app.cli seed-base`):
  provincias.csv      codigo,nombre,lat,lng
  departamentos.csv   codigo,provincia_codigo,nombre,lat,lng
  localidades.csv     codigo,departamento_codigo,nombre,lat,lng
  FUENTE.json         URLs, fecha de descarga, cantidad de filas y sha256 de cada archivo

Solo usa la biblioteca estándar. No inventa ni completa datos: si la respuesta no tiene la forma esperada
o las cantidades no son plausibles, corta con un error y no escribe nada.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE_URL = "https://apis.datos.gob.ar/georef/api/v2.0"
OUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "seeds" / "georef"
# Cantidades mínimas plausibles (Argentina tiene 24 jurisdicciones y más de 500 departamentos/partidos/comunas)
EXPECTED = {"provincias": (24, 24), "departamentos": (500, 600), "localidades": (3000, 20000)}


def fetch(base: str, entity: str) -> tuple[str, list[dict]]:
    url = f"{base}/{entity}.json"
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        sys.exit(f"URL no permitida: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "girando-georef/1.0", "Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - esquema validado arriba
        data = json.load(r)
    items = data.get(entity) if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        sys.exit(f"{url}: no vino la lista '{entity}'. ¿Cambió el formato de Georef?")
    return url, items


def _coord(item: dict, key: str):
    c = item.get("centroide") or {}
    v = c.get(key, item.get(f"centroide_{key}"))
    return "" if v in (None, "") else f"{float(v):.6f}"


def _ref(item: dict, name: str) -> str:
    """id de una entidad anidada ({'provincia': {'id': '50'}}) o aplanada ('provincia_id')."""
    nested = item.get(name)
    v = nested.get("id") if isinstance(nested, dict) else item.get(f"{name}_id")
    return "" if v is None else str(v).strip()


def _clean(name) -> str:
    return " ".join(str(name or "").split())


def normalize(provs: list[dict], deps: list[dict], locs: list[dict]) -> tuple[dict[str, list[list[str]]], dict]:
    p_rows = sorted([str(p["id"]).strip(), _clean(p["nombre"]), _coord(p, "lat"), _coord(p, "lon")] for p in provs)
    p_codes = {r[0] for r in p_rows}
    d_rows, d_skipped = [], 0
    for d in deps:
        code, prov = str(d["id"]).strip(), _ref(d, "provincia")
        if prov not in p_codes or not _clean(d.get("nombre")):
            d_skipped += 1
            continue
        d_rows.append([code, prov, _clean(d["nombre"]), _coord(d, "lat"), _coord(d, "lon")])
    d_rows.sort()
    d_codes = {r[0] for r in d_rows}
    l_rows, l_skipped = [], 0
    for loc in locs:
        code, dep = str(loc["id"]).strip(), _ref(loc, "departamento")
        if dep not in d_codes or not _clean(loc.get("nombre")):
            l_skipped += 1     # sin departamento conocido: no se puede ubicar en la jerarquía, se informa y se omite
            continue
        l_rows.append([code, dep, _clean(loc["nombre"]), _coord(loc, "lat"), _coord(loc, "lon")])
    l_rows.sort()
    for name, rows_ in (("provincias", p_rows), ("departamentos", d_rows), ("localidades", l_rows)):
        lo, hi = EXPECTED[name]
        if not lo <= len(rows_) <= hi:
            sys.exit(f"{name}: {len(rows_)} filas, fuera de lo esperado ({lo}–{hi}). No se escribió nada.")
        codes = [r[0] for r in rows_]
        if len(codes) != len(set(codes)):
            sys.exit(f"{name}: hay códigos repetidos. No se escribió nada.")
    return ({"provincias": p_rows, "departamentos": d_rows, "localidades": l_rows},
            {"departamentos_omitidos": d_skipped, "localidades_omitidas_sin_departamento": l_skipped})


HEADERS = {"provincias": ["codigo", "nombre", "lat", "lng"],
           "departamentos": ["codigo", "provincia_codigo", "nombre", "lat", "lng"],
           "localidades": ["codigo", "departamento_codigo", "nombre", "lat", "lng"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    urls, raw = {}, {}
    for entity in ("provincias", "departamentos", "localidades"):
        urls[entity], raw[entity] = fetch(args.base_url.rstrip("/"), entity)
        print(f"descargado {entity}: {len(raw[entity])}")
    tables, skipped = normalize(raw["provincias"], raw["departamentos"], raw["localidades"])
    out.mkdir(parents=True, exist_ok=True)
    meta = {"fuente": "API Georef — Datos Argentina (datos.gob.ar)", "licencia": "Creative Commons Attribution 4.0",
            "documentacion": "https://www.argentina.gob.ar/georef/descarga-de-la-base-completa",
            "descargado_el": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "archivos": {}, **skipped}
    for name, rows_ in tables.items():
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(HEADERS[name])
        w.writerows(rows_)
        content = buf.getvalue().encode("utf-8")
        (out / f"{name}.csv").write_bytes(content)
        meta["archivos"][f"{name}.csv"] = {"url": urls[name], "filas": len(rows_), "sha256": hashlib.sha256(content).hexdigest()}
        print(f"escrito {name}.csv: {len(rows_)} filas")
    (out / "FUENTE.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Listo en {out}. Revisá el diff, versioná los 4 archivos y corré: python -m app.cli seed-base")


if __name__ == "__main__":
    main()
