#!/usr/bin/env python3
"""Genera docs/02-diccionario-de-datos.md leyendo el catálogo de PostgreSQL
(la base cargada con db/cargar_local.sh). El diccionario nunca se escribe a
mano: si cambia el SQL, se regenera y queda igual al esquema real."""
import json, re, subprocess, sys
from pathlib import Path

PSQL = ["psql", "-h", "/var/tmp/girando-pg", "-p", "5433", "-U", "postgres", "-d", "girando_v0", "-AtX", "-c"]
OUT = Path(__file__).resolve().parents[1] / "docs" / "02-diccionario-de-datos.md"

def q(sql):
    return json.loads(subprocess.check_output(PSQL + [f"SELECT coalesce(json_agg(x), '[]') FROM ({sql}) x"]).decode())

tables = q("""
  SELECT c.oid::int AS oid, c.relname AS name, obj_description(c.oid) AS comment,
         c.relkind = 'p' AS partitioned, c.relrowsecurity AS rls
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app' AND c.relkind IN ('r','p') AND NOT c.relispartition
  ORDER BY c.oid""")
cols = q("""
  SELECT a.attrelid::int AS oid, a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type,
         a.attnotnull AS notnull, pg_get_expr(d.adbin, d.adrelid) AS def, a.attgenerated <> '' AS generated,
         col_description(a.attrelid, a.attnum) AS comment
  FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attrelid IN (SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='app')
  ORDER BY a.attrelid, a.attnum""")
cons = q("""
  SELECT conrelid::int AS oid, conname AS name, contype AS type, pg_get_constraintdef(oid) AS def,
         (SELECT array_agg(attname) FROM pg_attribute WHERE attrelid = conrelid AND attnum = ANY(conkey)) AS cols
  FROM pg_constraint WHERE connamespace = 'app'::regnamespace AND conrelid <> 0 ORDER BY conrelid, contype, conname""")
idx = q("""
  SELECT i.indrelid::int AS oid, c.relname AS name, pg_get_indexdef(i.indexrelid) AS def, i.indisprimary AS pk
  FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_class t ON t.oid = i.indrelid
  WHERE t.relnamespace = 'app'::regnamespace AND NOT t.relispartition ORDER BY i.indrelid, c.relname""")
pols = q("""
  SELECT c.oid::int AS oid, p.polname AS name, p.polcmd AS cmd,
         (SELECT string_agg(rolname, ',') FROM pg_roles WHERE oid = ANY(p.polroles)) AS roles
  FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid WHERE c.relnamespace = 'app'::regnamespace ORDER BY c.oid, p.polname""")
enums = q("""
  SELECT t.typname AS name, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS vals
  FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid WHERE t.typnamespace = 'app'::regnamespace GROUP BY t.typname ORDER BY t.typname""")
views = q("""SELECT c.relname AS name, n.nspname AS schema, obj_description(c.oid) AS comment
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'v' AND n.nspname IN ('app','api_public') ORDER BY n.nspname, c.relname""")

def by(lst):
    d = {}
    for x in lst: d.setdefault(x["oid"], []).append(x)
    return d
C, K, I, P = by(cols), by(cons), by(idx), by(pols)
DEFAULT_VIS = {}
for vis, names in {
  "PÚBLICO": "vehicle_brands vehicle_models vehicle_generations vehicle_versions vehicle_engines vehicle_version_engines geo_areas policy_versions plans promotion_products verification_products report_reasons exchange_rates external_ratings user_profiles",
  "PROPIETARIO": "favorites saved_searches notification_preferences notifications sessions consents user_blocks listing_stats_daily listing_status_history catalog_requests conversations messages promotion_events",
  "SENSIBLE": "vehicle_identifiers documents user_personal_data",
  "SISTEMA": "auth_tokens",
  "ADMIN": "staff_roles login_attempts moderation_actions reports audit_logs analytics_events payment_events email_templates email_events notification_types app_settings retention_policies",
}.items():
    for n in names.split(): DEFAULT_VIS[n] = vis
TAG = re.compile(r"^\[([A-ZÁÉÍÓÚ ]+(?: [a-z][^\]]*)?)\]\s*")
CMD = {"r": "SELECT", "a": "INSERT", "w": "UPDATE", "d": "DELETE", "*": "ALL"}

def esc(s): return (s or "").replace("|", "\\|").replace("\n", " ")

lines = ["# Girando — Diccionario de datos v0 (generado)", "",
         "> Generado automáticamente desde el catálogo de PostgreSQL por `db/generar_diccionario.py`. **No editar a mano.**",
         "> Visibilidad en cursiva = heredada del default de la tabla (campos técnicos: id, fechas, FKs). Visibilidad: **PÚBLICO** · **PRIVADO** (titular + staff autorizado) · **PROPIETARIO** (solo el titular) · **ADMIN** (solo staff) · **SENSIBLE** (cifrado/restringido y auditado) · **SISTEMA** (secreto técnico, nunca sale del backend).", "",
         f"Tablas: **{len(tables)}** · Enums: **{len(enums)}** · Vistas: **{len(views)}**", "", "## Índice", ""]
for t in tables: lines.append(f"- [`{t['name']}`](#{t['name'].replace('_','_')})")
lines += ["", "---", ""]
for t in tables:
    lines += [f"## {t['name']}", "", esc(t["comment"]) or "_(sin comentario)_", ""]
    flags = ["RLS activo" if t["rls"] else "SIN RLS"] + (["particionada por mes"] if t["partitioned"] else [])
    lines += ["_" + " · ".join(flags) + "_", "",
              "| Campo | Tipo | Oblig. | Default | Visibilidad | Notas |", "|---|---|---|---|---|---|"]
    pk = next((k["cols"] for k in K.get(t["oid"], []) if k["type"] == "p"), []) or []
    fks = {k["cols"][0]: re.sub(r"^FOREIGN KEY \([^)]*\) ", "", k["def"]) for k in K.get(t["oid"], []) if k["type"] == "f" and len(k["cols"]) == 1}
    for c in C.get(t["oid"], []):
        com = c["comment"] or ""
        m = TAG.match(com); note = TAG.sub("", com)
        vis = m.group(1) if m else "_" + DEFAULT_VIS.get(t["name"], "PRIVADO") + "_"
        extra = []
        if c["name"] in pk: extra.append("**PK**")
        if c["name"] in fks: extra.append("FK → " + fks[c["name"]].replace("REFERENCES ", ""))
        if c["generated"]: extra.append("generada")
        dflt = "" if c["generated"] else (c["def"] or "")
        lines.append(f"| `{c['name']}` | {esc(c['type'])} | {'sí' if c['notnull'] else 'no'} | {esc(dflt)[:40]} | {esc(vis)} | {esc(' · '.join(extra + ([note] if note else [])))} |")
    checks = [k for k in K.get(t["oid"], []) if k["type"] in ("c", "u", "x") or (k["type"] == "f" and len(k["cols"]) > 1)]
    if checks:
        lines += ["", "<details><summary>Restricciones</summary>", ""]
        lines += [f"- `{k['name']}`: `{esc(k['def'])}`" for k in checks]
        lines += ["", "</details>"]
    ix = [i for i in I.get(t["oid"], []) if not i["pk"]]
    if ix:
        lines += ["", "<details><summary>Índices</summary>", ""]
        IDX = re.compile(r"^CREATE (UNIQUE )?INDEX \S+ ON app\.\S+ ")
        for i in ix:
            d = esc(IDX.sub(lambda m: "UNIQUE " if m.group(1) else "", i["def"]))
            lines.append(f"- `{d}` — {i['name']}")
        lines += ["", "</details>"]
    pl = P.get(t["oid"], [])
    if pl:
        lines += ["", "<details><summary>Políticas RLS</summary>", ""]
        lines += [f"- `{p['name']}` ({CMD.get(p['cmd'], p['cmd'])} → {p['roles']})" for p in pl]
        lines += ["", "</details>"]
    lines += ["", "---", ""]
lines += ["## Enums", "", "| Enum | Valores |", "|---|---|"]
lines += [f"| `{e['name']}` | {', '.join('`'+v+'`' for v in e['vals'])} |" for e in enums]
lines += ["", "## Vistas", "", "| Vista | Descripción |", "|---|---|"]
lines += [f"| `{v['schema']}.{v['name']}` | {esc(v['comment'])} |" for v in views]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{OUT} · {len(tables)} tablas · {sum(len(C.get(t['oid'],[])) for t in tables)} columnas · {len(enums)} enums · {len(views)} vistas")
