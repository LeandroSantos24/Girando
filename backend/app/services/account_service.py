"""Datos de la cuenta calculados por el backend: roles, agencias, plan efectivo y uso."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.engine import Connection

from app.core.db import row, rows, scalar

MAIN_SLOT = {"parts_store": "part", "service_provider": "service", "company": "job"}


def plan_usage(conn: Connection, user_id: UUID, agency_id: UUID | None) -> dict:
    """Plan efectivo y uso del cupo principal de la cuenta. Los números salen de las mismas funciones de la
    base que hacen cumplir el límite (app.limit_for / app.active_counts): la pantalla nunca muestra otra cuenta.
      · particular: un solo cupo gratis para vehículo, taxi o empleo.
      · agencia: vehículos + taxis; casa de repuestos: ítems; prestador: fichas; empresa: empleos."""
    plan = row(conn, """SELECT (p).id, (p).code, (p).name, (p).max_active_listings, (p).audience::text AS audience,
                               (p).stats_level, (p).max_members, (p).max_active_jobs, (p).requires_verification,
                               (p).price_amount, (p).billing_period::text AS billing_period
                          FROM (SELECT app.effective_plan(:u, :a) AS p) x""", {"u": user_id, "a": agency_id})
    kind = scalar(conn, "SELECT kind::text FROM app.agencies WHERE id = :a", {"a": agency_id}) if agency_id else None
    what = MAIN_SLOT.get(kind, "vehicle")
    lim = row(conn, "SELECT used, max_allowed FROM app.limit_for(:u, :a, :w, NULL)", {"u": user_id, "a": agency_id, "w": what}) if plan else None
    counts = row(conn, "SELECT vehicles, taxis, jobs, services, parts FROM app.active_counts(:u, :a, NULL)", {"u": user_id, "a": agency_id})
    used, limit = (lim["used"], lim["max_allowed"]) if lim else (0, 0)
    sub = None
    if agency_id:
        sub = row(conn, """SELECT s.status::text AS status, p.name AS plan_name, s.current_period_end, s.provider::text AS provider,
                                  pp.name AS pending_plan_name
                             FROM app.subscriptions s JOIN app.plans p ON p.id = s.plan_id LEFT JOIN app.plans pp ON pp.id = s.pending_plan_id
                            WHERE s.agency_id = :a ORDER BY s.created_at DESC LIMIT 1""", {"a": agency_id})
    out = {"plan": plan, "used": used, "limit": limit, "at_limit": bool(plan) and used >= limit, "subscription": sub,
           "slot": what, "counts": counts, "account_kind": kind or "particular"}
    if agency_id and what != "job" and plan:
        out["jobs"] = {"used": counts["jobs"], "limit": plan["max_active_jobs"]}
    return out


def me_summary(conn: Connection, user_id: UUID) -> dict:
    u = row(conn, """SELECT u.id, u.email::text AS email, u.status::text AS status, u.email_verified_at IS NOT NULL AS email_verified,
                            u.identity_verified_at IS NOT NULL AS identity_verified, u.created_at, u.phone_e164,
                            p.display_name, p.avatar_public_id, p.bio, p.geo_area_id, p.is_public, p.show_phone_default,
                            p.contact_whatsapp_e164, p.contact_phone_e164, p.instagram_url, p.tiktok_url, p.facebook_url,
                            p.x_url, p.youtube_url, p.website_url,
                            pd.first_name, pd.last_name, g.name AS locality
                       FROM app.users u
                       LEFT JOIN app.user_profiles p ON p.user_id = u.id
                       LEFT JOIN app.user_personal_data pd ON pd.user_id = u.id
                       LEFT JOIN app.geo_areas g ON g.id = p.geo_area_id
                      WHERE u.id = :u""", {"u": user_id})
    roles = [r["role"] for r in rows(conn, "SELECT role::text FROM app.staff_roles WHERE user_id = :u AND revoked_at IS NULL", {"u": user_id})]
    agencies = rows(conn, """SELECT a.id, a.trade_name, a.slug, a.status::text AS status, a.kind::text AS kind, m.role::text AS member_role,
                                    app.agency_verification_state(a.id) AS verification_state,
                                    (SELECT count(*) FROM app.listings l WHERE l.agency_id = a.id AND l.status NOT IN ('sold','deleted')) AS inventory_total
                               FROM app.agency_members m JOIN app.agencies a ON a.id = m.agency_id
                              WHERE m.user_id = :u AND m.status = 'active' ORDER BY a.trade_name""", {"u": user_id})
    # Rol "de producto" derivado (user / agency_member / agency_admin / admin / super_admin)
    if "superadmin" in roles:
        product_role = "super_admin"
    elif roles:
        product_role = "admin"
    elif any(a["member_role"] in ("owner", "admin") for a in agencies):
        product_role = "agency_admin"
    elif agencies:
        product_role = "agency_member"
    else:
        product_role = "user"
    return {**u, "staff_roles": roles, "role": product_role, "agencies": agencies,
            "particular_usage": plan_usage(conn, user_id, None),
            "unread_notifications": scalar(conn, "SELECT count(*) FROM app.notifications WHERE user_id = :u AND read_at IS NULL", {"u": user_id})}
