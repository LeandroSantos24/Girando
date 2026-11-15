"""CLI de operación: migraciones, bootstrap de roles, seeds y jobs.

  python -m app.cli migrate          # alembic upgrade head (rol dueño)
  python -m app.cli bootstrap-db     # crea/actualiza el rol de login de la API (NOINHERIT)
  python -m app.cli seed-base        # configuración y catálogos de referencia (idempotente, todos los entornos)
  python -m app.cli seed-dev [--reset-passwords]   # SOLO ENV=development: usuarios de prueba (@girando.test)
  python -m app.cli reset-dev-db --confirm girando  # SOLO local: borra y recrea la base de desarrollo
  python -m app.cli jobs [--loop N]  # vencimientos, purga de fotos/patentes, agregados, cotización
  python -m app.cli create-superadmin EMAIL   # contraseña por variable SUPERADMIN_PASSWORD
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.db import row, rows, scalar, unit_of_work
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.seeds import base_data as B

log = logging.getLogger("girando.cli")
LEGAL_DIR = Path(__file__).resolve().parent / "seeds" / "legal"


def owner_engine():
    return create_engine(get_settings().database_owner_url, future=True)


# --------------------------------------------------------------------------- migraciones / roles
def cmd_migrate(_):
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    command.upgrade(cfg, "head")
    log.info("migrations_applied")


def cmd_bootstrap_db(_):
    s = get_settings()
    with owner_engine().begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'girando_api'")).first()
        # Contraseña por parámetro: psycopg no permite bind en DDL, se escapa como literal SQL de forma segura.
        pw = conn.execute(text("SELECT quote_literal(:p)"), {"p": s.db_api_password}).scalar()
        if exists:
            conn.execute(text(f"ALTER ROLE girando_api WITH LOGIN NOINHERIT PASSWORD {pw}"))
        else:
            conn.execute(text(f"CREATE ROLE girando_api WITH LOGIN NOINHERIT PASSWORD {pw}"))
        conn.execute(text("GRANT girando_anon, girando_app, girando_worker TO girando_api"))
        dbname = conn.execute(text("SELECT current_database()")).scalar()
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{dbname}" TO girando_api'))
    log.info("db_role_ready", extra={"role": "girando_api", "inherit": False})


# --------------------------------------------------------------------------- seeds
def _q(conn, sql, **p):
    return conn.execute(text(sql), p)


def cmd_seed_base(_):
    with unit_of_work("worker") as conn:
        # Geo
        ar = scalar(conn, "SELECT id FROM app.geo_areas WHERE level = 'country' AND name = 'Argentina'")
        if not ar:
            ar = scalar(conn, "INSERT INTO app.geo_areas (level, name, country_code) VALUES ('country', 'Argentina', 'AR') RETURNING id")
        for prov in B.PROVINCES:
            pid = scalar(conn, "SELECT id FROM app.geo_areas WHERE parent_id = :p AND name = :n", {"p": ar, "n": prov})
            if not pid:
                pid = scalar(conn, "INSERT INTO app.geo_areas (parent_id, level, name) VALUES (:p, 'province', :n) RETURNING id", {"p": ar, "n": prov})
            for dep in B.DEPARTMENTS.get(prov, []):
                if not scalar(conn, "SELECT 1 FROM app.geo_areas WHERE parent_id = :p AND name = :n", {"p": pid, "n": dep}):
                    _q(conn, "INSERT INTO app.geo_areas (parent_id, level, name) VALUES (:p, 'department', :n)", p=pid, n=dep)
        # Catálogo
        engines = {}
        for brand, models in B.CATALOG:
            slug = brand.lower().replace(" ", "-")
            bid = scalar(conn, "SELECT id FROM app.vehicle_brands WHERE lower(name) = lower(:n)", {"n": brand}) or \
                scalar(conn, "INSERT INTO app.vehicle_brands (name, slug) VALUES (:n, :s) RETURNING id", {"n": brand, "s": slug})
            for mname, vtype, body, gens in models:
                mid = scalar(conn, "SELECT id FROM app.vehicle_models WHERE brand_id = :b AND lower(name) = lower(:n)", {"b": bid, "n": mname}) or \
                    scalar(conn, """INSERT INTO app.vehicle_models (brand_id, name, slug, vehicle_type, default_body_type)
                                    VALUES (:b, :n, :s, CAST(:t AS app.vehicle_type), CAST(:bd AS app.body_type)) RETURNING id""",
                           {"b": bid, "n": mname, "s": mname.lower().replace(" ", "-"), "t": vtype, "bd": body})
                for gname, yf, yt, versions in gens:
                    gid = scalar(conn, "SELECT id FROM app.vehicle_generations WHERE model_id = :m AND lower(name) = lower(:n)", {"m": mid, "n": gname}) or \
                        scalar(conn, "INSERT INTO app.vehicle_generations (model_id, name, year_from, year_to) VALUES (:m, :n, :f, :t) RETURNING id",
                               {"m": mid, "n": gname, "f": yf, "t": yt})
                    for vname, ename, fuel, trans, trac, doors in versions:
                        vid = scalar(conn, "SELECT id FROM app.vehicle_versions WHERE generation_id = :g AND lower(name) = lower(:n)", {"g": gid, "n": vname}) or \
                            scalar(conn, """INSERT INTO app.vehicle_versions (generation_id, name, body_type, doors, transmission, traction)
                                            VALUES (:g, :n, CAST(:b AS app.body_type), :d, CAST(:tr AS app.transmission_type), CAST(:tc AS app.traction_type)) RETURNING id""",
                                   {"g": gid, "n": vname, "b": body, "d": doors, "tr": trans, "tc": trac})
                        if ename not in engines:
                            engines[ename] = scalar(conn, "SELECT id FROM app.vehicle_engines WHERE lower(name) = lower(:n)", {"n": ename}) or \
                                scalar(conn, """INSERT INTO app.vehicle_engines (name, fuel, aspiration)
                                                VALUES (:n, CAST(:f AS app.fuel_type), CAST(:a AS app.engine_aspiration)) RETURNING id""",
                                       {"n": ename, "f": fuel, "a": "turbo" if "Turbo" in ename or "TD" in vname else None})
                        _q(conn, """INSERT INTO app.vehicle_version_engines (version_id, engine_id, is_default) VALUES (:v, :e, true)
                                   ON CONFLICT DO NOTHING""", v=vid, e=engines[ename])
        # Planes
        for code, name, aud, price, period, limit, feat, stats, members, default, order, features in B.PLANS:
            if not scalar(conn, "SELECT 1 FROM app.plans WHERE code = :c", {"c": code}):
                _q(conn, """INSERT INTO app.plans (code, name, audience, price_amount, billing_period, max_active_listings, included_featured_listings,
                               stats_level, max_members, is_default_for_audience, sort_order, features_display)
                           VALUES (:c, :n, CAST(:a AS app.plan_audience), :p, CAST(:per AS app.billing_period), :l, :f, :s, :m, :d, :o, :fd)""",
                   c=code, n=name, a=aud, p=price, per=period, l=limit, f=feat, s=stats, m=members, d=default, o=order, fd=features)
        for code, (jobs, needs_verif, pending) in B.PLAN_EXTRAS.items():   # solo la primera vez: después manda lo que edite el Super Admin
            _q(conn, """UPDATE app.plans SET max_active_jobs = :j, requires_verification = :v, pending_owner_confirmation = :p
                       WHERE code = :c AND created_at = updated_at""", c=code, j=jobs, v=needs_verif, p=pending)
        for slug, name, kind, web in B.FINANCING_ENTITIES:
            _q(conn, """INSERT INTO app.financing_entities (slug, name, kind, website_url) VALUES (:s, :n, CAST(:k AS app.financing_entity_kind), :w)
                       ON CONFLICT (slug) DO NOTHING""", s=slug, n=name, k=kind, w=web)
        for i, (code, label, applies) in enumerate(B.REPORT_REASONS):
            _q(conn, """INSERT INTO app.report_reasons (code, label, applies_to, sort_order, requires_description)
                       VALUES (:c, :l, CAST(:a AS app.report_target[]), :o, :rd)
                       ON CONFLICT (code) DO UPDATE SET applies_to = EXCLUDED.applies_to""",
               c=code, l=label, a=applies, o=i, rd=code == "otro")
        for code, subject, body, variables in B.EMAIL_TEMPLATES:
            if not scalar(conn, "SELECT 1 FROM app.email_templates WHERE code = :c", {"c": code}):
                _q(conn, """INSERT INTO app.email_templates (code, subject, body_html, body_text, variables, status)
                           VALUES (:c, :s, :b, :b, :v, 'active')""", c=code, s=subject, b=body, v=variables)
        for code, cat, desc, commercial, mandatory, email, tpl in B.NOTIFICATION_TYPES:
            _q(conn, """INSERT INTO app.notification_types (code, category, description, is_commercial, is_mandatory, email_enabled, email_template_code)
                       VALUES (:c, CAST(:cat AS app.notification_category), :d, :com, :man, :em, :t) ON CONFLICT (code) DO NOTHING""",
               c=code, cat=cat, d=desc, com=commercial, man=mandatory, em=email, t=tpl)
        for code, label, cat, dur, frm, action in B.RETENTION:
            _q(conn, """INSERT INTO app.retention_policies (code, label, category, duration, starts_from, action)
                       VALUES (:c, :l, CAST(:cat AS app.retention_category), CAST(:d AS interval), :f, CAST(:a AS app.retention_action))
                       ON CONFLICT (code) DO NOTHING""", c=code, l=label, cat=cat, d=dur, f=frm, a=action)
        for key, value, desc, public in B.SETTINGS:
            _q(conn, """INSERT INTO app.app_settings (key, value, description, is_public) VALUES (:k, CAST(:v AS jsonb), :d, :p)
                       ON CONFLICT (key) DO NOTHING""", k=key, v=json.dumps(value), d=desc, p=public)
        for code, name, desc, kind, subject, status, disclaimer in B.VERIFICATION_PRODUCTS:
            _q(conn, """INSERT INTO app.verification_products (code, name, description, kind, subject, status, public_disclaimer)
                       VALUES (:c, :n, :d, CAST(:k AS app.verification_kind), CAST(:s AS app.verification_subject), CAST(:st AS app.verification_product_status), :pd)
                       ON CONFLICT (code) DO NOTHING""", c=code, n=name, d=desc, k=kind, s=subject, st=status, pd=disclaimer)
        for code, items in B.VERIFICATION_CHECKLISTS.items():
            _q(conn, """UPDATE app.verification_products SET checklist_template = CAST(:c AS jsonb)
                       WHERE code = :code AND checklist_template = '[]'::jsonb""", c=json.dumps(items), code=code)
        for code, name, desc, ptype, placement, price, days in B.PROMOTION_PRODUCTS:
            _q(conn, """INSERT INTO app.promotion_products (code, name, description, type, placement, price_amount, duration_days, is_active)
                       VALUES (:c, :n, :d, CAST(:t AS app.promotion_type), CAST(:p AS app.promotion_placement), :pr, :days, false)
                       ON CONFLICT (code) DO NOTHING""", c=code, n=name, d=desc, t=ptype, p=placement, pr=price, days=days)
        for dtype, fname in B.POLICIES:
            content = (LEGAL_DIR / fname).read_bytes()
            _q(conn, """INSERT INTO app.policy_versions (doc_type, version, content_url, content_sha256, published_at)
                       VALUES (CAST(:t AS app.policy_doc_type), '2026-09-draft', :u, :h, now()) ON CONFLICT (doc_type, version) DO NOTHING""",
               t=dtype, u=f"/api/legal/{fname.removesuffix('.html')}", h=hashlib.sha256(content).digest())
    log.info("seed_base_done")


DEV_USERS = [
    # email, nombre visible, rol de staff. SOLO desarrollo local (ENV=development). Nunca en producción.
    ("superadmin@girando.test", "Super Admin (dev)", "superadmin"),
    ("admin@girando.test", "Admin operación (dev)", "admin"),
    ("moderador@girando.test", "Moderación (dev)", "moderator"),
    ("usuario@girando.test", "Usuario de prueba", None),
    ("agencia@girando.test", "Dueño de agencia (dev)", None),
]
DEV_AGENCY_PLAN = "agencia-30"


def _dev_guard() -> None:
    s = get_settings()
    if s.env != "development":
        sys.exit("Solo corre con ENV=development (base local de desarrollo).")


def cmd_seed_dev(args):
    """Usuarios y datos mínimos para probar Girando en local. Idempotente: no duplica cuentas.
    --reset-passwords vuelve a poner la contraseña de desarrollo en las cuentas @girando.test."""
    _dev_guard()
    password = os.environ.get("DEV_SEED_PASSWORD", "Girando-dev-2026")
    from app.core.security import validate_password_strength
    if problem := validate_password_strength(password):
        sys.exit(f"DEV_SEED_PASSWORD no es válida: {problem}")
    with unit_of_work("worker", reason="seed-dev") as conn:
        ids = {}
        for email, name, role in DEV_USERS:
            uid = scalar(conn, "SELECT id FROM app.users WHERE email = :e", {"e": email})
            if not uid:
                uid = scalar(conn, """INSERT INTO app.users (email, password_hash, status, email_verified_at) VALUES (:e, :h, 'active', now()) RETURNING id""",
                             {"e": email, "h": hash_password(password)})
                _q(conn, "INSERT INTO app.user_profiles (user_id, display_name) VALUES (:u, :n)", u=uid, n=name)
                _q(conn, "INSERT INTO app.user_personal_data (user_id) VALUES (:u)", u=uid)
            elif getattr(args, "reset_passwords", False):
                _q(conn, "UPDATE app.users SET password_hash = :h, status = 'active', failed_login_count = 0, locked_until = NULL WHERE id = :u",
                   h=hash_password(password), u=uid)
            # Cada cuenta de prueba tiene exactamente el rol que dice la tabla
            _q(conn, """UPDATE app.staff_roles SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL
                       AND (CAST(:r AS text) IS NULL OR role <> CAST(:r AS app.staff_role))""", u=uid, r=role)
            if role:
                _q(conn, """INSERT INTO app.staff_roles (user_id, role) SELECT :u, CAST(:r AS app.staff_role)
                           WHERE NOT EXISTS (SELECT 1 FROM app.staff_roles WHERE user_id = :u AND role = CAST(:r AS app.staff_role) AND revoked_at IS NULL)""",
                   u=uid, r=role)
            ids[email] = uid
        # Agencia de prueba: perfil completo, plan Agencia 30 asignado manualmente (sin Mercado Pago)
        # y una solicitud de verificación pendiente para probar el flujo del Admin.
        owner = ids["agencia@girando.test"]
        aid = scalar(conn, "SELECT id FROM app.agencies WHERE slug = 'agencia-de-prueba-dev'")
        if not aid:
            gc = scalar(conn, "SELECT id FROM app.geo_areas WHERE name = 'Godoy Cruz'")
            aid = scalar(conn, """INSERT INTO app.agencies (slug, legal_name, trade_name, cuit, geo_area_id, created_by, description, phone_e164, whatsapp_e164,
                                                         email, website_url)
                                  VALUES ('agencia-de-prueba-dev', 'Agencia de Prueba DEV SRL', 'Agencia de Prueba (dev)', '30500010912', :g, :u,
                                          'Agencia ficticia creada por seed-dev para probar en local. No existe.', '+542614000000', '+542614000000',
                                          'agencia@girando.test', 'https://example.com') RETURNING id""", {"g": gc, "u": owner})
            prod = scalar(conn, "SELECT id FROM app.verification_products WHERE code = 'agency'")
            _q(conn, """INSERT INTO app.verifications (product_id, subject_agency_id, requested_by, checklist)
                       SELECT :p, :a, :u, checklist_template FROM app.verification_products WHERE id = :p""", p=prod, a=aid, u=owner)
        if not scalar(conn, "SELECT 1 FROM app.subscriptions WHERE agency_id = :a AND status IN ('active','grace_period','payment_failed')", {"a": aid}):
            grant_manual_plan(conn, agency_id=aid, plan_code=DEV_AGENCY_PLAN, created_by=ids["superadmin@girando.test"],
                              notes="Plan de prueba asignado por seed-dev (local)")
    log.info("seed_dev_done", extra={"users": [u[0] for u in DEV_USERS]})
    print_dev_credentials(password)


def grant_manual_plan(conn, *, agency_id, plan_code=None, plan_id=None, created_by, notes):
    """Plan asignado a mano (cortesía/convenio), sin cobro: provider 'manual', precio 0, período por calendario.
    No pasa por Mercado Pago y no se renueva solo: al terminar el período, el job lo vence."""
    plan = row(conn, """SELECT id, billing_period::text AS billing_period FROM app.plans
                         WHERE (id = CAST(:pid AS uuid) OR code = :code) AND audience = 'agency' AND is_active""", {"pid": plan_id, "code": plan_code})
    if not plan:
        raise ValueError("plan de agencia inexistente o inactivo")
    period = plan["billing_period"] if plan["billing_period"] != "none" else "month"
    _q(conn, "UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE agency_id = :a AND status = 'pending'", a=agency_id)
    return scalar(conn, """INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, status, price_amount, currency, billing_period,
                                                        started_at, current_period_start, current_period_end, billing_anchor_day, notes)
                           SELECT :p, :a, :u, 'manual', 'active', 0, 'ARS', CAST(:per AS app.billing_period), now(), now(),
                                  app.next_period_end(now(), CAST(:per AS app.billing_period)),
                                  extract(day FROM now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::int, :n
                           RETURNING id""", {"p": plan["id"], "a": agency_id, "u": created_by, "per": period, "n": notes})


def print_dev_credentials(password: str) -> None:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:3100").rstrip("/")
    print("\nUsuarios de desarrollo (solo local, nunca en producción):")
    print(f"  contraseña de todas: {password}  (variable DEV_SEED_PASSWORD del .env)")
    for email, _name, role in DEV_USERS:
        url = f"{base}/admin/" if role else f"{base}/"
        print(f"  {email:<26} {role or ('agencia (Agencia 30)' if email.startswith('agencia') else 'particular'):<22} {url}")


def cmd_reset_dev_db(args):
    """Borra y recrea la base LOCAL de desarrollo: esquemas app/api_public y alembic_version,
    migraciones desde cero, rol de la API, datos base y seed de desarrollo. No toca código ni migraciones.
    Exige ENV=development, un host local y confirmar el nombre de la base."""
    _dev_guard()
    from sqlalchemy.engine import make_url
    url = make_url(get_settings().database_owner_url)
    host, dbname = (url.host or "localhost"), url.database
    if host not in ("localhost", "127.0.0.1", "::1", "db", "postgres"):
        sys.exit(f"Host '{host}' no parece local. reset-dev-db solo se usa contra la base de desarrollo.")
    if any(w in (dbname or "").lower() for w in ("prod", "production", "live")):
        sys.exit(f"La base '{dbname}' parece de producción. Abortado.")
    if args.confirm != dbname:
        sys.exit(f"Para confirmar, repetí el nombre de la base: --confirm {dbname}")
    print(f"Recreando la base local '{dbname}' en {host}…")
    with owner_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS api_public CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS app CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    cmd_migrate(args)
    cmd_bootstrap_db(args)
    cmd_seed_base(args)
    if not args.no_seed:
        cmd_seed_dev(argparse.Namespace(reset_passwords=False))
    s = get_settings()
    if s.image_storage == "local_dev":
        import shutil
        media = Path(s.media_root) / "listings"
        if media.exists():
            shutil.rmtree(media, ignore_errors=True)
            print(f"Fotos locales borradas: {media}")
    if s.redis_url:
        try:
            import redis
            redis.Redis.from_url(s.redis_url).flushdb()
            print("Contadores de rate limit (Redis) reiniciados")
        except Exception:  # noqa: BLE001
            print("Aviso: no se pudo limpiar Redis (no es necesario)")
    print("Listo. Reiniciá la API y el worker:  docker compose restart api worker")


# --------------------------------------------------------------------------- jobs
def job_expire_listings(conn) -> int:
    ids = [r["id"] for r in rows(conn, "SELECT id FROM app.listings WHERE status = 'published' AND expires_at <= now() LIMIT 500")]
    for lid in ids:
        _q(conn, "UPDATE app.listings SET status = 'expired' WHERE id = :l", l=lid)
        owner = scalar(conn, "SELECT owner_user_id FROM app.listings WHERE id = :l", {"l": lid})
        _q(conn, "SELECT app.enqueue_notification(:u, 'listing.expired', 'Tu publicación venció', 'Podés renovarla desde Mis publicaciones.', 'listing', :l, '/mis-publicaciones')",
           u=owner, l=lid)
    return len(ids)


def job_expiry_notices(conn) -> int:
    days = scalar(conn, "SELECT app.setting_int('listings.expiry_notice_days', 3)")
    items = rows(conn, """SELECT l.id, l.owner_user_id, l.title FROM app.listings l WHERE l.status = 'published'
                           AND l.expires_at <= now() + make_interval(days => :d)
                           AND NOT EXISTS (SELECT 1 FROM app.notifications n WHERE n.entity_id = l.id AND n.type_code = 'listing.expiring'
                                           AND n.created_at > l.published_at)""", {"d": days})
    for i in items:
        _q(conn, "SELECT app.enqueue_notification(:u, 'listing.expiring', 'Tu publicación vence pronto', :t, 'listing', :l, '/mis-publicaciones')",
           u=i["owner_user_id"], t=f"{i['title'] or 'Tu publicación'}: renovala para que siga visible.", l=i["id"])
    return len(items)


def job_purge_images(conn) -> int:
    from app.services.media import storage_for
    due = rows(conn, """SELECT i.id, i.public_id, i.storage_provider::text AS provider, i.status::text AS status FROM app.listing_images i
                         LEFT JOIN app.retention_policies r ON r.code = 'media_deleted'
                        WHERE (i.status = 'purge_scheduled' AND i.purge_after <= now())
                           OR (i.status IN ('deleted','replaced') AND i.updated_at <= now() - coalesce(r.duration, interval '30 days'))
                        LIMIT 200""")
    done = 0
    for img in due:
        try:
            storage_for(img["provider"]).delete(img["public_id"])
        except Exception:  # noqa: BLE001 - se reintenta en la próxima corrida
            log.warning("image_purge_failed", extra={"image_id": str(img["id"])})
            continue
        _q(conn, "UPDATE app.listing_images SET status = 'purged', is_cover = false WHERE id = :i", i=img["id"])
        done += 1
    return done


def job_purge_identifiers(conn) -> int:
    return _q(conn, "DELETE FROM app.vehicle_identifiers WHERE purge_after IS NOT NULL AND purge_after <= now()").rowcount


def job_aggregate_stats(conn) -> int:
    """Recalcula listing_stats_daily de los últimos 2 días desde analytics_events (idempotente)."""
    return _q(conn, """
        INSERT INTO app.listing_stats_daily (listing_id, day, impressions, views, favorites, unfavorites, contacts, contact_reveals, shares, promotion_clicks)
        SELECT e.listing_id, e.occurred_at::date,
               count(*) FILTER (WHERE event_name = 'listing_impression'), count(*) FILTER (WHERE event_name = 'listing_view'),
               count(*) FILTER (WHERE event_name = 'listing_favorite'), count(*) FILTER (WHERE event_name = 'listing_unfavorite'),
               count(*) FILTER (WHERE event_name = 'listing_contact'), count(*) FILTER (WHERE event_name = 'listing_contact_reveal'),
               count(*) FILTER (WHERE event_name = 'listing_share'), count(*) FILTER (WHERE event_name = 'promotion_click')
          FROM app.analytics_events e JOIN app.listings l ON l.id = e.listing_id
         WHERE e.listing_id IS NOT NULL AND e.occurred_at >= current_date - 1
         GROUP BY 1, 2
        ON CONFLICT (listing_id, day) DO UPDATE SET impressions = EXCLUDED.impressions, views = EXCLUDED.views, favorites = EXCLUDED.favorites,
            unfavorites = EXCLUDED.unfavorites, contacts = EXCLUDED.contacts, contact_reveals = EXCLUDED.contact_reveals, shares = EXCLUDED.shares,
            promotion_clicks = EXCLUDED.promotion_clicks""").rowcount


def job_subscriptions(conn) -> dict:
    """Vencimientos por fecha REAL guardada (nunca se activa nada por fecha: activar es del proveedor o de finanzas).
    · canceladas cuyo período terminó → expired
    · manual / transferencia (no se renuevan solas) con período terminado → expired
    · Mercado Pago sin cobro aprobado al terminar el período → grace_period; terminada la gracia → expired
    Al perder el plan se pausan las publicaciones que exceden el límite del plan que queda."""
    grace = scalar(conn, "SELECT app.setting_int('billing.grace_days', 10)")
    notice = scalar(conn, "SELECT app.setting_int('billing.expiry_notice_days', 7)")
    ended = rows(conn, """UPDATE app.subscriptions s SET status = 'expired', ended_at = now()
                           WHERE (s.status = 'canceled' AND s.current_period_end <= now())
                              OR (s.status = 'active' AND s.provider IN ('manual','bank_transfer') AND s.current_period_end <= now())
                              OR (s.status = 'grace_period' AND s.grace_until <= now())
                          RETURNING s.id, s.agency_id, s.user_id""")
    graced = rows(conn, """UPDATE app.subscriptions s SET status = 'grace_period', grace_until = s.current_period_end + make_interval(days => :g)
                            WHERE s.status IN ('active','payment_failed') AND s.provider = 'mercadopago' AND s.current_period_end <= now()
                           RETURNING s.id, s.agency_id""", {"g": grace})
    paused = 0
    for s in ended:
        paused += scalar(conn, "SELECT app.enforce_plan_limit(:u, :a)", {"u": s["user_id"], "a": s["agency_id"]}) or 0
        owner = scalar(conn, "SELECT user_id FROM app.agency_members WHERE agency_id = :a AND role = 'owner' AND status = 'active'", {"a": s["agency_id"]})
        if owner:
            _q(conn, "SELECT app.enqueue_notification(:u, 'subscription.expired', 'Tu plan terminó', 'Las publicaciones que exceden el plan gratuito quedaron pausadas en tu inventario.', 'agency', :a, '/suscripcion')",
               u=owner, a=s["agency_id"])
    for s in graced:
        owner = scalar(conn, "SELECT user_id FROM app.agency_members WHERE agency_id = :a AND role = 'owner' AND status = 'active'", {"a": s["agency_id"]})
        if owner:
            _q(conn, "SELECT app.enqueue_notification(:u, 'subscription.payment_failed', 'No pudimos confirmar el cobro', 'Tu plan sigue activo unos días. Revisá el medio de pago en Mercado Pago.', 'agency', :a, '/suscripcion')",
               u=owner, a=s["agency_id"])
    expiring = rows(conn, """SELECT s.id, s.agency_id, s.current_period_end FROM app.subscriptions s
                              WHERE s.status = 'active' AND s.provider IN ('manual','bank_transfer')
                                AND s.current_period_end <= now() + make_interval(days => :n)
                                AND NOT EXISTS (SELECT 1 FROM app.notifications x WHERE x.entity_id = s.agency_id AND x.type_code = 'subscription.expiring'
                                                AND x.created_at > s.current_period_start)""", {"n": notice})
    for s in expiring:
        owner = scalar(conn, "SELECT user_id FROM app.agency_members WHERE agency_id = :a AND role = 'owner' AND status = 'active'", {"a": s["agency_id"]})
        if owner:
            _q(conn, "SELECT app.enqueue_notification(:u, 'subscription.expiring', 'Tu plan termina pronto', :b, 'agency', :a, '/suscripcion')",
               u=owner, b=f"Vence el {s['current_period_end']:%d/%m/%Y}. Después las publicaciones que excedan el plan gratuito se pausan.", a=s["agency_id"])
    return {"expired": len(ended), "grace": len(graced), "paused_listings": paused, "notices": len(expiring)}


def job_promotions(conn) -> int:
    """Promociones activas o pausadas cuya fecha de fin pasó → finished (con evento)."""
    done = rows(conn, """UPDATE app.promotions SET status = 'finished' WHERE status IN ('active','paused') AND ends_at <= now()
                         RETURNING id, CAST(status AS text) AS status""")
    for p in done:
        _q(conn, """INSERT INTO app.promotion_events (promotion_id, event, to_status, actor_type, reason)
                   VALUES (:p, 'finished', 'finished', 'system', 'Fin del período contratado')""", p=p["id"])
    return len(done)


# ---- fase 4
def job_expire_posts(conn) -> int:
    """Taxis, servicios, repuestos y empleos publicados cuya vigencia terminó → expired (con aviso al dueño)."""
    items = rows(conn, "SELECT id, owner_user_id, title FROM app.posts WHERE status = 'published' AND expires_at <= now() LIMIT 500")
    for i in items:
        _q(conn, "UPDATE app.posts SET status = 'expired' WHERE id = :p", p=i["id"])
        _q(conn, "SELECT app.enqueue_notification(:u, 'post.expired', 'Tu publicación venció', :t, 'post', :p, '/mis-publicaciones')",
           u=i["owner_user_id"], t=(i["title"] or "Tu publicación")[:200], p=i["id"])
    return len(items)


def job_plan_limits(conn) -> int:
    """Cuentas cuyo plan cambió (baja de plan, vencimiento, repuestos sin pago o sin verificación): se PAUSA lo que
    excede. Nunca se borra nada: queda en el inventario y vuelve a publicarse cuando haya cupo."""
    return scalar(conn, "SELECT app.enforce_all_plan_limits()") or 0


def job_purge_messages(conn) -> int:
    """Retención de mensajes (política `messages`, 12 meses desde la última actividad): se borran los mensajes de
    las conversaciones vencidas. Los que tienen una denuncia siguen la retención de denuncias. Devuelve conversaciones purgadas."""
    dur = scalar(conn, "SELECT duration FROM app.retention_policies WHERE code = 'messages'")
    if dur is None:
        return 0
    convs = [r["id"] for r in rows(conn, """SELECT c.id FROM app.conversations c
                                             WHERE coalesce(c.last_message_at, c.created_at) < now() - CAST(:d AS interval)
                                               AND EXISTS (SELECT 1 FROM app.messages m WHERE m.conversation_id = c.id
                                                           AND NOT EXISTS (SELECT 1 FROM app.reports r WHERE r.message_id = m.id))
                                             LIMIT 500""", {"d": dur})]
    if convs:
        _q(conn, """DELETE FROM app.messages m WHERE m.conversation_id = ANY(CAST(:c AS uuid[]))
                     AND NOT EXISTS (SELECT 1 FROM app.reports r WHERE r.message_id = m.id)""", c=[str(x) for x in convs])
    return len(convs)


def job_saved_searches(conn) -> int:
    """Búsquedas guardadas con aviso: si aparecieron publicaciones nuevas que coinciden, UNA notificación por búsqueda
    y por período (instant / daily / weekly). Usa el mismo buscador público: nunca avisa algo que no se ve."""
    from app.services import search_service
    due = rows(conn, """SELECT id, user_id, name, filters, last_seen_listing_published_at FROM app.saved_searches
                         WHERE notification_enabled
                           AND (last_notified_at IS NULL OR last_notified_at <= now() - CASE notify_frequency
                                WHEN 'weekly' THEN interval '7 days' WHEN 'daily' THEN interval '1 day' ELSE interval '0' END)
                         ORDER BY last_notified_at NULLS FIRST LIMIT 500""")
    sent = 0
    for ss in due:
        try:
            where, params, _ = search_service.build_where(conn, search_service.normalize_filters(ss["filters"]))
        except Exception:  # noqa: BLE001 — un filtro viejo que ya no se puede interpretar no frena al resto
            log.warning("saved_search_skipped", extra={"saved_search": str(ss["id"])})
            continue
        got = row(conn, f"""SELECT count(*) AS n, max(published_at) AS newest FROM api_public.listings
                             WHERE {where} AND published_at > :since""",                       # where: solo placeholders ligados
                  {**params, "since": ss["last_seen_listing_published_at"] or datetime(1970, 1, 1, tzinfo=UTC)})
        if not got["n"]:
            continue
        n = got["n"]
        _q(conn, "SELECT app.enqueue_notification(:u, 'search.new_results', :t, :b, 'saved_search', :s, '/busquedas')",
           u=ss["user_id"], s=ss["id"], t="Hay novedades en tu búsqueda guardada",
           b=f"{ss['name']}: {n} {'publicación nueva' if n == 1 else 'publicaciones nuevas'}.")
        _q(conn, "UPDATE app.saved_searches SET last_notified_at = now(), last_seen_listing_published_at = :n WHERE id = :s", n=got["newest"], s=ss["id"])
        sent += 1
    return sent


def job_ensure_partitions(conn) -> None:
    # Solo meses FUTUROS: el mes en curso ya puede tener filas en la partición default y crearlo fallaría.
    for offset in (1, 2):
        start = scalar(conn, "SELECT date_trunc('month', now() + make_interval(months => :o))::date", {"o": offset})
        name = f"analytics_events_{start:%Y_%m}"
        if not scalar(conn, "SELECT to_regclass(:n)", {"n": f"app.{name}"}):
            try:
                with conn.begin_nested():  # savepoint: un fallo no aborta el resto
                    _q(conn, f"CREATE TABLE app.{name} PARTITION OF app.analytics_events FOR VALUES FROM ('{start}') TO ('{start}'::date + interval '1 month')")
                    _q(conn, f"REVOKE ALL ON app.{name} FROM girando_app, girando_worker")
                log.info("partition_created", extra={"partition": name})
            except Exception:  # noqa: BLE001
                log.warning("partition_create_skipped", extra={"partition": name})


def job_exchange_rate(conn) -> None:
    from app.integrations import NotConfigured
    from app.integrations.external import ExchangeRateService
    today = date.today()
    if scalar(conn, "SELECT 1 FROM app.exchange_rates WHERE currency = 'USD' AND valid_on = :d", {"d": today}):
        return
    try:
        rate = ExchangeRateService().fetch_usd(today)
    except NotConfigured:
        return
    except Exception as e:  # noqa: BLE001 - sin red / feriado: no se inventa cotización
        log.warning("fx_fetch_failed", extra={"error": str(e)[:200]})
        return
    _q(conn, "INSERT INTO app.exchange_rates (currency, rate_to_ars, source, valid_on) VALUES ('USD', :r, 'bcra_a3500', :d) ON CONFLICT DO NOTHING",
       r=rate, d=today)


def run_jobs_once() -> dict:
    out = {}
    for name, fn in (("expire", job_expire_listings), ("notices", job_expiry_notices), ("images", job_purge_images),
                     ("identifiers", job_purge_identifiers), ("stats", job_aggregate_stats), ("fx", job_exchange_rate),
                     ("subscriptions", job_subscriptions), ("promotions", job_promotions),
                     ("posts", job_expire_posts), ("plan_limits", job_plan_limits), ("messages", job_purge_messages),
                     ("saved_searches", job_saved_searches)):
        try:
            with unit_of_work("worker") as conn:
                out[name] = fn(conn)
        except Exception:  # noqa: BLE001
            log.exception("job_failed", extra={"job": name})
            out[name] = "error"
    try:
        with owner_engine().begin() as conn:
            job_ensure_partitions(conn)
    except Exception:  # noqa: BLE001
        log.exception("partitions_failed")
    return out


def cmd_jobs(args):
    while True:
        log.info("jobs_run", extra={"result": run_jobs_once()})
        if not args.loop:
            return
        time.sleep(args.loop)


def cmd_create_superadmin(args):
    password = os.environ.get("SUPERADMIN_PASSWORD")
    if not password:
        sys.exit("Definí SUPERADMIN_PASSWORD en el entorno")
    from app.core.security import validate_password_strength
    if problem := validate_password_strength(password):
        sys.exit(problem)
    with unit_of_work("worker") as conn:
        uid = scalar(conn, "SELECT id FROM app.users WHERE email = :e", {"e": args.email.lower()})
        if not uid:
            uid = scalar(conn, "INSERT INTO app.users (email, password_hash, status) VALUES (:e, :h, 'active') RETURNING id",
                         {"e": args.email.lower(), "h": hash_password(password)})
            _q(conn, "INSERT INTO app.user_profiles (user_id, display_name) VALUES (:u, 'Administración')", u=uid)
            _q(conn, "INSERT INTO app.user_personal_data (user_id) VALUES (:u)", u=uid)
        _q(conn, """INSERT INTO app.staff_roles (user_id, role) SELECT :u, 'superadmin'
                   WHERE NOT EXISTS (SELECT 1 FROM app.staff_roles WHERE user_id = :u AND role = 'superadmin' AND revoked_at IS NULL)""", u=uid)
    print("superadmin listo:", args.email)


def main():
    setup_logging(get_settings().log_level)
    p = argparse.ArgumentParser(prog="girando")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    sub.add_parser("bootstrap-db").set_defaults(fn=cmd_bootstrap_db)
    sub.add_parser("seed-base").set_defaults(fn=cmd_seed_base)
    sd = sub.add_parser("seed-dev")
    sd.add_argument("--reset-passwords", action="store_true", help="vuelve a poner DEV_SEED_PASSWORD en las cuentas @girando.test")
    sd.set_defaults(fn=cmd_seed_dev)
    rd = sub.add_parser("reset-dev-db", help="SOLO local: borra y recrea la base de desarrollo (pide --confirm <nombre de la base>)")
    rd.add_argument("--confirm", required=True)
    rd.add_argument("--no-seed", action="store_true")
    rd.set_defaults(fn=cmd_reset_dev_db)
    j = sub.add_parser("jobs")
    j.add_argument("--loop", type=int, default=0, help="segundos entre corridas (0 = una vez)")
    j.set_defaults(fn=cmd_jobs)
    c = sub.add_parser("create-superadmin")
    c.add_argument("email")
    c.set_defaults(fn=cmd_create_superadmin)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

