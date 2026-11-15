"""Fase 3: períodos por calendario, plan manual, inventario vs publicadas, promociones reales,
Home administrable, tracking de clics externos, verificación con checklist y guardas del reset local."""
import argparse
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import full_listing_payload, make_agency, make_staff, new_client, register


def _staff(role: str):
    c = new_client()
    email, _ = register(c, name=f"Staff {role}")
    make_staff(email, role)
    return c


def _w():
    from app.core.db import unit_of_work
    return unit_of_work("worker")


def _published_listing(client, **over):
    lid = client.post("/api/me/listings", json=full_listing_payload(client, **over)).json()["id"]
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200
    assert _staff("moderator").post(f"/api/admin/listings/{lid}/approve", json={}).status_code == 200
    return lid, client.get(f"/api/me/listings/{lid}").json()["public_code"]


# --------------------------------------------------------------------------- períodos
@pytest.mark.parametrize("start,anchor,expected", [
    ("2027-01-31 12:00-03", None, "2027-02-28"),     # enero 31 → fin de febrero
    ("2027-02-28 12:00-03", 31, "2027-03-31"),       # vuelve al ancla 31
    ("2027-04-30 09:00-03", 31, "2027-05-31"),
    ("2028-01-31 12:00-03", None, "2028-02-29"),     # bisiesto
    ("2027-12-15 23:30-03", None, "2028-01-15"),     # cambio de año, en hora de Argentina
])
def test_next_period_end_is_calendar_based(start, anchor, expected):
    with _w() as c:
        end = c.execute(text("SELECT (app.next_period_end(CAST(:s AS timestamptz), 'month', :a) AT TIME ZONE 'America/Argentina/Buenos_Aires')::date"),
                        {"s": start, "a": anchor}).scalar()
    assert str(end) == expected


def test_payment_extends_once_and_renews_continuously(client):
    register(client)
    ag = make_agency(client)
    with _w() as c:
        plan = c.execute(text("SELECT id FROM app.plans WHERE code = 'agencia-30'")).scalar()
        uid = c.execute(text("SELECT user_id FROM app.agency_members WHERE agency_id = :a"), {"a": ag["id"]}).scalar()
        sid = c.execute(text("""INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, price_amount, currency, billing_period)
                                VALUES (:p, :a, :u, 'mercadopago', 54900, 'ARS', 'month') RETURNING id"""), {"p": plan, "a": ag["id"], "u": uid}).scalar()
        paid = datetime(2026, 1, 31, 15, 0, tzinfo=UTC)
        pid = c.execute(text("""INSERT INTO app.payments (purpose, subscription_id, payer_user_id, agency_id, provider, status, amount, paid_at, mp_payment_id)
                                VALUES ('subscription', :s, :u, :a, 'mercadopago', 'approved', 54900, :pa, 'mp-1') RETURNING id"""),
                        {"s": sid, "u": uid, "a": ag["id"], "pa": paid}).scalar()
        s1 = c.execute(text("SELECT status::text, current_period_end FROM app.subscriptions WHERE id = :s"), {"s": sid}).one()
        assert s1[0] == "active" and s1[1].astimezone(UTC).date().isoformat() == "2026-02-28"
        # el mismo pago re-notificado (webhook repetido) no extiende otra vez
        c.execute(text("UPDATE app.payments SET status = 'approved', provider_snapshot = '{\"again\": true}' WHERE id = :p"), {"p": pid})
        assert c.execute(text("SELECT current_period_end FROM app.subscriptions WHERE id = :s"), {"s": sid}).scalar() == s1[1]
        # renovación cobrada 2 días antes del fin → continúa desde el fin (ancla 31 → 31 de marzo)
        c.execute(text("""INSERT INTO app.payments (purpose, subscription_id, payer_user_id, agency_id, provider, status, amount, paid_at, mp_payment_id)
                          VALUES ('subscription', :s, :u, :a, 'mercadopago', 'approved', 54900, :pa, 'mp-2')"""),
                  {"s": sid, "u": uid, "a": ag["id"], "pa": s1[1] - timedelta(days=2)})
        end2 = c.execute(text("SELECT (current_period_end AT TIME ZONE 'America/Argentina/Buenos_Aires')::date FROM app.subscriptions WHERE id = :s"), {"s": sid}).scalar()
        assert end2.isoformat() == "2026-03-31"


def test_jobs_expire_manual_plan_and_pause_excess(client):
    from app.cli import job_subscriptions
    register(client)
    ag = make_agency(client)
    sup = _staff("superadmin")
    plan = next(p for p in sup.get("/api/admin/plans").json()["items"] if p["code"] == "agencia-30")
    assert sup.post(f"/api/admin/agencies/{ag['id']}/plan", json={"plan_id": plan["id"], "notes": "Convenio de prueba"}).status_code == 201
    _published_listing(client, agency_id=ag["id"])
    _published_listing(client, year=2016, agency_id=ag["id"])
    assert client.get("/api/me/agencies").json()["items"][0]["usage"]["limit"] == 30
    with _w() as c:  # el plan "termina"
        c.execute(text("UPDATE app.subscriptions SET current_period_end = now() - interval '1 minute' WHERE agency_id = :a AND status = 'active'"), {"a": ag["id"]})
        out = job_subscriptions(c)
    assert out["expired"] >= 1 and out["paused_listings"] >= 1
    items = client.get("/api/me/listings", params={"agency_id": ag["id"], "group": "todas"}).json()["items"]
    assert sorted(i["status"] for i in items) == ["paused", "published"]   # queda 1 publicada (plan gratuito), la otra en inventario


# --------------------------------------------------------------------------- inventario vs publicadas
def test_inventory_unlimited_but_published_capped_in_backend(client):
    register(client)
    ag = make_agency(client)
    with _w() as c:
        c.execute(text("""INSERT INTO app.plans (code, name, audience, price_amount, billing_period, max_active_listings)
                          VALUES ('agencia-test-2', 'Agencia Test 2', 'agency', 1000, 'month', 2) ON CONFLICT (code) DO NOTHING"""))
        plan = c.execute(text("SELECT id FROM app.plans WHERE code = 'agencia-test-2'")).scalar()
    sup = _staff("superadmin")
    r = sup.post(f"/api/admin/agencies/{ag['id']}/plan", json={"plan_id": str(plan), "notes": "Prueba de límite"})
    assert r.status_code == 201, r.text
    ids = [client.post("/api/me/listings", json=full_listing_payload(client, year=2014 + i, agency_id=ag["id"])).json()["id"] for i in range(4)]
    assert all(ids)   # 4 en inventario (borradores): sin límite
    assert client.post(f"/api/me/listings/{ids[0]}/transition", json={"to": "pending"}).status_code == 200
    assert client.post(f"/api/me/listings/{ids[1]}/transition", json={"to": "pending"}).status_code == 200
    r = client.post(f"/api/me/listings/{ids[2]}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMITE_ALCANZADO"
    a = client.get(f"/api/me/agencies/{ag['id']}").json()
    assert a["usage"]["used"] == 2 and a["usage"]["limit"] == 2 and a["inventory"].get("draft") == 2
    # el vehículo 3 nunca aparece en público
    assert all(i["id"] not in ids[2:] for i in new_client().get("/api/listings").json()["items"])


# --------------------------------------------------------------------------- promociones
def test_promotion_lifecycle_and_disclosure(client):
    register(client)
    _, code = _published_listing(client)
    sup = _staff("superadmin")
    now = datetime.now(UTC)
    body = {"type": "featured_listing", "placement": "home_featured", "listing_code": code,
            "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(days=7)).isoformat()}
    paid = sup.post("/api/admin/promotions", json={**body, "price_amount": 4900})
    assert paid.status_code == 201
    r = sup.post(f"/api/admin/promotions/{paid.json()['id']}/activate", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAGO_PENDIENTE"     # sin pago aprobado no se activa
    comp = sup.post("/api/admin/promotions", json={**body, "notes": "Cortesía de lanzamiento"}).json()
    assert sup.post(f"/api/admin/promotions/{comp['id']}/activate", json={}).json()["status"] == "active"
    sp = new_client().get("/api/sponsored", params={"placement": "home_featured"}).json()["items"]
    assert any(s["public_code"] == code and s["disclosure_label"] == "Patrocinado" for s in sp)
    assert sup.post(f"/api/admin/promotions/{comp['id']}/pause", json={}).status_code == 422      # pausar pide motivo
    assert sup.post(f"/api/admin/promotions/{comp['id']}/pause", json={"reason": "Pedido del cliente"}).json()["status"] == "paused"
    assert not any(s["public_code"] == code for s in new_client().get("/api/sponsored").json()["items"])
    from app.cli import job_promotions
    with _w() as c:
        c.execute(text("UPDATE app.promotions SET ends_at = now() - interval '1 second', starts_at = now() - interval '2 days' WHERE id = :p"), {"p": comp["id"]})
        assert job_promotions(c) >= 1
        ev = [r[0] for r in c.execute(text("SELECT event::text FROM app.promotion_events WHERE promotion_id = :p ORDER BY id"), {"p": comp["id"]})]
    assert ev == ["created", "activated", "paused", "finished"]


# --------------------------------------------------------------------------- Home
def test_home_blocks_only_active_and_in_dates():
    sup = _staff("superadmin")
    a = sup.post("/api/admin/home-blocks", json={"kind": "announcement", "title": "Publicá gratis tu auto", "body": "Particulares: 1 publicación activa.",
                                                 "cta_label": "Publicar", "cta_target": "publicar", "status": "active"})
    assert a.status_code == 201, a.text
    sup.post("/api/admin/home-blocks", json={"kind": "announcement", "title": "Borrador interno"})
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    sup.post("/api/admin/home-blocks", json={"kind": "cta", "title": "Todavía no", "status": "active", "starts_at": future})
    titles = [b["title"] for b in new_client().get("/api/home").json()["blocks"]]
    assert "Publicá gratis tu auto" in titles and "Borrador interno" not in titles and "Todavía no" not in titles
    assert sup.post("/api/admin/home-blocks", json={"kind": "cta", "title": "Mal destino", "cta_label": "Ir", "cta_target": "javascript:alert(1)"}).status_code == 422


# --------------------------------------------------------------------------- agencia: perfil, clics externos, estadísticas, verificación
def test_agency_profile_outbound_click_and_stats(client):
    register(client)
    ag = make_agency(client)
    r = client.patch(f"/api/me/agencies/{ag['id']}", json={"website_url": "https://autos-fase3.example", "store_url": "https://autos.mitiendanube.com",
                                                           "whatsapp_e164": "+5492614555555", "description": "Usados seleccionados"})
    assert r.status_code == 200 and r.json()["store_url"] == "https://autos.mitiendanube.com"
    assert client.patch(f"/api/me/agencies/{ag['id']}", json={"website_url": "http://inseguro.example"}).status_code == 422
    anon = new_client()
    r = anon.get(f"/api/out/agency/{ag['slug']}/website", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://autos-fase3.example"
    r = anon.get(f"/api/out/agency/{ag['slug']}/whatsapp", follow_redirects=False)
    assert r.headers["location"] == "https://wa.me/5492614555555"
    assert anon.get(f"/api/out/agency/{ag['slug']}/instagram", follow_redirects=False).status_code == 404   # canal no cargado
    with _w() as c:
        ev = c.execute(text("""SELECT user_id, properties->>'channel' FROM app.analytics_events
                                WHERE agency_id = :a AND event_name = 'external_click' ORDER BY id"""), {"a": ag["id"]}).all()
    assert [e[1] for e in ev] == ["website", "whatsapp"] and all(e[0] is None for e in ev)   # sin datos personales
    st = client.get(f"/api/me/agencies/{ag['id']}/stats").json()
    assert st["external_clicks"] == {"website": 1, "whatsapp": 1} and st["totals"]["external_clicks"] == 2


def test_verification_request_checklist_and_badge(client):
    register(client)
    ag = make_agency(client)
    assert client.get("/api/me/agencies").json()["items"][0]["verification_state"] == "none"
    assert client.post(f"/api/me/agencies/{ag['id']}/verification").status_code == 201
    assert client.post(f"/api/me/agencies/{ag['id']}/verification").status_code == 409     # una sola solicitud abierta
    prof = client.get("/api/me/profile").json()["agencies"][0]                               # la App lee el estado desde el perfil
    assert prof["verification_state"] == "pending" and prof["inventory_total"] == 0
    mod = _staff("moderator")
    vid = next(v["id"] for v in mod.get("/api/admin/verifications").json()["items"] if v["agency_id"] == ag["id"])
    d = mod.get(f"/api/admin/verifications/{vid}").json()
    assert d["items"] and all(not i["done"] for i in d["items"])
    first = d["items"][0]["key"]
    d = mod.patch(f"/api/admin/verifications/{vid}", json={"checklist": [{"key": first, "done": True, "note": "Constancia vista"}],
                                                           "evidence_notes": "Llamado al responsable OK", "assign_to_me": True, "start_review": True}).json()
    assert d["status"] == "review" and next(i for i in d["items"] if i["key"] == first)["done"] is True and d["assigned_to_name"]
    assert new_client().get(f"/api/agencies/{ag['slug']}").json()["is_verified"] is False      # sin aprobación no hay badge
    assert mod.post(f"/api/admin/agencies/{ag['id']}/verify", json={}).json()["status"] == "verified"
    assert new_client().get(f"/api/agencies/{ag['slug']}").json()["is_verified"] is True


# --------------------------------------------------------------------------- finanzas y negocio
def test_business_and_finance_are_real_numbers():
    sup = _staff("superadmin")
    b = sup.get("/api/admin/business").json()
    assert {"users", "agencies", "listings", "subscriptions", "plans", "payments", "promotions", "home_blocks", "events_30d"} <= set(b)
    f = sup.get("/api/admin/finance/summary?months=3").json()
    assert len(f["by_month"]) == 3 and all(float(m["billed"]) >= 0 for m in f["by_month"])


# --------------------------------------------------------------------------- reset local: nunca fuera de desarrollo
def test_reset_dev_db_refuses_outside_development():
    from app.cli import cmd_reset_dev_db
    with pytest.raises(SystemExit):
        cmd_reset_dev_db(argparse.Namespace(confirm="girando_test", no_seed=True))
