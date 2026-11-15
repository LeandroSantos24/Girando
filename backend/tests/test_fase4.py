"""Fase 4: filtros del marketplace, financiación por entidad (TNA/TEA/CFT), cupo gratis compartido,
rutas de cobro (alta, mejora, baja, cancelación, promociones) con idempotencia, candado de repuestos,
verticales (taxis, servicios, repuestos, empleos), mensajería sin CVs, publicidad medida y recomendaciones
con consentimiento. Todo por API directa contra PostgreSQL real."""
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.core.db import RequestContext, unit_of_work
from tests.conftest import catalog_ids, full_listing_payload, geo_id, make_agency, make_staff, new_client, register


def _staff(role: str):
    c = new_client()
    email, _ = register(c, name=f"Staff {role}")
    make_staff(email, role)
    return c


def _w():
    return unit_of_work("worker")


def _user(name="Persona"):
    c = new_client()
    register(c, name=name)
    return c


def _uid(c):
    return c.get("/api/me/profile").json()["id"]


def _published_listing(client, **over):
    r = client.post("/api/me/listings", json=full_listing_payload(client, **over))
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200
    assert _staff("moderator").post(f"/api/admin/listings/{lid}/approve", json={}).status_code == 200
    return lid, client.get(f"/api/me/listings/{lid}").json()["public_code"]


def _grant(agency_id, code):
    sup = _staff("superadmin")
    plan = next(p for p in sup.get("/api/admin/plans").json()["items"] if p["code"] == code)
    r = sup.post(f"/api/admin/agencies/{agency_id}/plan", json={"plan_id": plan["id"], "notes": "Plan de prueba fase 4"})
    assert r.status_code == 201, r.text


def _plan(client, code):
    return next(p for p in client.get("/api/plans").json()["items"] if p["code"] == code)


def _post(client, vertical, details, **over):
    body = {"vertical": vertical, "geo_area_id": geo_id(client), "title": f"Publicación de {vertical}", "details": details, **over}
    return client.post("/api/me/posts", json=body)


def _publish_post(client, pid):
    r = client.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"})
    assert r.status_code == 200, r.text
    r = _staff("moderator").post(f"/api/admin/posts/{pid}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "published", r.text
    return r.json()["public_code"]


JOB = {"role": "driver", "license_required": True, "license_classes": ["D1"], "workday": "full_time", "modality": "on_route"}
TAXI = {"offer_kind": "permit_only", "service_type": "taxi", "permit_number": "1234", "permit_holder_declared": "Titular Declarado",
        "permit_price": "30000000", "has_meter": True}


@pytest.fixture
def sim():
    """Simulador local del proveedor de pagos (solo desarrollo/tests)."""
    s = get_settings()
    s.payments_simulator = True
    yield
    s.payments_simulator = False


def _simulate(client, target, id_, outcome="approved", event_id=None):
    body = {"target": target, "id": str(id_), "outcome": outcome}
    if event_id:
        body["event_id"] = event_id
    return client.post("/api/dev/payments/simulate", json=body)


# =========================================================================== 1. marketplace: filtros
def test_filters_color_tradein_bodytype_and_counters(client):
    register(client)
    lid, _ = _published_listing(client, color="Rojo fuego", color_family="red", accepts_trade_in=True)
    anon = new_client()
    assert any(i["id"] == lid for i in anon.get("/api/listings", params={"color": "red"}).json()["items"])
    assert all(i["id"] != lid for i in anon.get("/api/listings", params={"color": "blue"}).json()["items"])
    assert any(i["id"] == lid for i in anon.get("/api/listings", params={"trade_in": True, "doors": 5, "year_min": 2015, "km_max": 100000}).json()["items"]) or \
        any(i["id"] == lid for i in anon.get("/api/listings", params={"trade_in": True, "year_min": 2015, "km_max": 100000}).json()["items"])
    f = anon.get("/api/listings/facets").json()
    assert any(o["value"] == "red" and o["count"] >= 1 for o in f["color"])            # contadores reales por opción
    assert f["flags"]["trade_in"] >= 1 and f["flags"]["total"] >= f["flags"]["trade_in"]
    # carrocerías nuevas aceptadas por la API; valores inválidos no
    for body in ("crossover", "roadster", "mpv", "panel_van", "light_truck", "off_road", "minivan", "wagon", "convertible"):
        assert anon.get("/api/listings", params={"body_type": body}).status_code == 200, body
    assert anon.get("/api/listings", params={"body_type": "nave-espacial"}).status_code == 422
    assert anon.get("/api/listings", params={"color": "fucsia"}).status_code == 422
    with _w() as c:   # la migración no dejó 'chassis' en el catálogo
        assert c.execute(text("SELECT count(*) FROM app.vehicle_versions WHERE body_type = 'chassis'")).scalar() == 0
    # versiones del modelo elegido, con contador
    ids = catalog_ids(anon)
    fv = anon.get("/api/listings/facets", params={"model_id": ids["model_id"]}).json()
    assert any(v["value"] == ids["version_id"] for v in fv["version"])
    assert anon.get("/api/listings/facets").json()["version"] == []


def test_price_filter_is_normalized_with_bcra_rate(client):
    register(client)
    lid, _ = _published_listing(client, price_amount="10000", currency="USD")
    anon = new_client()
    params = {"price_min": 9_000_000, "price_max": 11_000_000, "currency": "ARS"}
    assert all(i["id"] != lid for i in anon.get("/api/listings", params=params).json()["items"])   # sin cotización no se mezclan monedas
    try:
        with _w() as c:
            c.execute(text("INSERT INTO app.exchange_rates (currency, rate_to_ars, source, valid_on) VALUES ('USD', 1000, 'test', current_date)"))
        hit = next(i for i in anon.get("/api/listings", params=params).json()["items"] if i["id"] == lid)
        assert float(hit["price_ars"]) == 10_000_000 and hit["currency"] == "USD"                    # se muestra el precio que cargó el vendedor
        assert any(i["id"] == lid for i in anon.get("/api/listings", params={"price_max": 10500, "currency": "USD"}).json()["items"])
    finally:
        with _w() as c:
            c.execute(text("DELETE FROM app.exchange_rates WHERE source = 'test'"))


# =========================================================================== 2. financiación por entidad
def _entity(admin, **over):
    body = {"name": "Banco de Prueba", "slug": f"banco-{datetime.now(UTC).timestamp():.0f}-{id(over) % 9999}", "kind": "bank", **over}
    return admin.post("/api/admin/financing-entities", json=body)


def test_financing_offer_needs_moderation_and_all_three_rates(client):
    register(client)
    ag = make_agency(client, name="Agencia Financia")
    _grant(ag["id"], "agencia-30")
    lid, code = _published_listing(client, agency_id=ag["id"], price_amount="10000000")
    admin = _staff("admin")
    # logo solo con autorización anotada (API y base)
    assert _entity(admin, logo_public_id="logos/banco").status_code == 422
    assert _entity(admin, logo_authorized=True, logo_public_id="logos/banco").status_code == 422
    ent = _entity(admin)
    assert ent.status_code == 201 and ent.json()["logo_authorized"] is False
    with pytest.raises(DBAPIError), _w() as c:
        c.execute(text("UPDATE app.financing_entities SET logo_public_id = 'x' WHERE id = :e"), {"e": ent.json()["id"]})
    base = {"entity_id": ent.json()["id"], "type": "pledge_loan", "title": "Prendario 24 cuotas", "min_down_payment_pct": "30",
            "terms_months": [12, 24], "valid_until": (date.today() + timedelta(days=60)).isoformat(), "source": "Lista de tasas de la agencia"}
    # tasa a medias: rechazada por la API y por la base
    assert client.post(f"/api/me/agencies/{ag['id']}/financing-offers", json={**base, "tna": "60"}).status_code == 422
    with pytest.raises(DBAPIError), _w() as c:
        c.execute(text("""INSERT INTO app.financing_offers (entity_id, agency_id, created_by, type, title, terms_months, tna, valid_until, source)
                          VALUES (:e, :a, :u, 'pledge_loan', 'Solo TNA', '{12}', 60, current_date + 10, 'x y z')"""),
                  {"e": ent.json()["id"], "a": ag["id"], "u": _uid(client)})
    r = client.post(f"/api/me/agencies/{ag['id']}/financing-offers", json={**base, "tna": "60", "tea": "79.59", "cft": "102.36", "rate_kind": "fixed"})
    assert r.status_code == 201 and r.json()["status"] == "draft", r.text
    oid = r.json()["id"]
    assert client.put(f"/api/me/listings/{lid}/financing-offers", json={"offer_ids": [oid]}).status_code == 200
    anon = new_client()
    assert anon.get(f"/api/listings/{code}/financing").json()["offers"] == []                        # sin aprobar no se muestra
    assert client.post(f"/api/me/financing-offers/{oid}/submit").json()["status"] == "pending"
    assert client.post(f"/api/admin/financing-offers/{oid}/approve", json={}).status_code == 403     # la agencia no se aprueba sola
    with pytest.raises(DBAPIError), unit_of_work("app", _uid(client), RequestContext()) as c:        # ni escribiendo directo en la base
        c.execute(text("UPDATE app.financing_offers SET status = 'approved' WHERE id = :o"), {"o": oid})
    mod = _staff("moderator")
    assert mod.post(f"/api/admin/financing-offers/{oid}/reject", json={}).status_code == 422         # rechazar pide motivo
    assert mod.post(f"/api/admin/financing-offers/{oid}/approve", json={}).json()["status"] == "approved"
    fin = anon.get(f"/api/listings/{code}/financing").json()
    o = fin["offers"][0]
    assert (float(o["tna"]), float(o["tea"]), float(o["cft"])) == (60.0, 79.59, 102.36) and o["rate_kind"] == "fixed"
    assert float(o["down_payment"]) == 3_000_000 and float(o["financed_amount"]) == 7_000_000 and o["term_max"] == 24
    assert o["logo_authorized"] is False and o["logo_public_id"] is None and o["entity_name"] == "Banco de Prueba"
    assert "orientativa" in fin["disclaimer"].lower()
    # filtros de financiación
    assert any(i["id"] == lid and i["has_financing"] for i in anon.get("/api/listings", params={"financing_entity_id": ent.json()["id"]}).json()["items"])
    assert any(i["id"] == lid for i in anon.get("/api/listings", params={"down_payment_max": 3_000_000}).json()["items"])
    assert all(i["id"] != lid for i in anon.get("/api/listings", params={"down_payment_max": 2_000_000}).json()["items"])
    inst = float(o["installment_min"])
    assert any(i["id"] == lid for i in anon.get("/api/listings", params={"installment_max": inst + 1}).json()["items"])
    assert all(i["id"] != lid for i in anon.get("/api/listings", params={"installment_max": inst - 1000}).json()["items"])
    assert any(e["value"] == ent.json()["id"] for e in anon.get("/api/listings/facets").json()["financing_entity"])
    # calculadora orientativa: sistema francés sobre la TNA
    s = anon.get(f"/api/listings/{code}/financing/simulate", params={"offer_id": oid, "down_payment": 4_000_000, "months": 12}).json()
    i = 60 / 1200
    assert s["orientative"] is True and abs(float(s["installment"]) - 6_000_000 * i / (1 - (1 + i) ** -12)) < 1
    assert anon.get(f"/api/listings/{code}/financing/simulate", params={"offer_id": oid, "down_payment": 4_000_000, "months": 18}).status_code == 422
    assert anon.get(f"/api/listings/{code}/financing/simulate", params={"offer_id": oid, "down_payment": 1_000_000, "months": 12}).status_code == 422
    # editar una oferta aprobada la devuelve a revisión y deja de mostrarse
    r = client.patch(f"/api/me/financing-offers/{oid}", json={**base, "tna": "40", "tea": "48.21", "cft": "65", "rate_kind": "fixed"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert anon.get(f"/api/listings/{code}/financing").json()["offers"] == []
    # historial de precio público
    assert client.patch(f"/api/me/listings/{lid}", json={"price_amount": "9500000"}).status_code == 200
    hist = anon.get(f"/api/listings/{code}/price-history").json()["items"]
    assert float(hist[-1]["new_amount"]) == 9_500_000 and "changed_by" not in hist[-1]


def test_offer_without_rate_does_not_invent_one(client):
    register(client)
    ag = make_agency(client, name="Agencia Sin Tasa")
    _grant(ag["id"], "agencia-30")
    lid, code = _published_listing(client, agency_id=ag["id"], price_amount="8000000")
    r = client.post(f"/api/me/agencies/{ag['id']}/financing-offers", json={
        "type": "dealer_financing", "title": "Financiación propia", "min_down_payment_pct": "50", "terms_months": [6],
        "valid_until": (date.today() + timedelta(days=30)).isoformat(), "source": "Condiciones de la agencia", "applies_to_all": True})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    client.post(f"/api/me/financing-offers/{oid}/submit")
    assert _staff("moderator").post(f"/api/admin/financing-offers/{oid}/approve", json={}).status_code == 200
    o = new_client().get(f"/api/listings/{code}/financing").json()["offers"][0]      # applies_to_all: sin asociarla una por una
    assert o["tna"] is None and o["cft"] is None and o["installment_min"] is None and float(o["down_payment"]) == 4_000_000
    s = new_client().get(f"/api/listings/{code}/financing/simulate", params={"offer_id": oid, "down_payment": 4_000_000, "months": 6}).json()
    assert s["installment"] is None and "no informa tasa" in s["note"]


# =========================================================================== 3. cupo gratis: 1 en total
def test_particular_has_one_free_slot_vehicle_or_job(client):
    register(client)
    _published_listing(client)
    r = _post(client, "job", JOB)
    assert r.status_code == 201                                           # el borrador se puede crear (inventario)
    r2 = client.post(f"/api/me/posts/{r.json()['id']}/transition", json={"to": "pending"})
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "LIMITE_ALCANZADO"
    with pytest.raises(DBAPIError), unit_of_work("app", _uid(client), RequestContext()) as c:   # ni escribiendo directo en la base
        c.execute(text("UPDATE app.posts SET status = 'pending' WHERE id = :p"), {"p": r.json()["id"]})
    usage = client.get("/api/me/plan").json()
    assert usage["limit"] == 1 and usage["used"] == 1 and usage["at_limit"] is True

    other = _user("Empleador")                                           # al revés: primero el empleo, después el vehículo
    pid = _post(other, "job", JOB).json()["id"]
    assert other.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"}).status_code == 200
    lid = other.post("/api/me/listings", json=full_listing_payload(other)).json()["id"]
    r = other.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMITE_ALCANZADO"
    tid = _post(other, "taxi", TAXI, price_amount="30000000").json()["id"]            # y el taxi comparte el mismo cupo
    assert other.post(f"/api/me/posts/{tid}/transition", json={"to": "pending"}).status_code == 409
    assert other.post(f"/api/me/posts/{pid}/transition", json={"to": "draft"}).status_code == 200   # al liberar el cupo, se puede
    assert other.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200


# =========================================================================== 4. cobros: alta, mejora, baja, cancelación
def test_payments_are_off_without_gateway(client):
    register(client)
    ag = make_agency(client, name="Sin Pasarela")
    r = client.post(f"/api/me/agencies/{ag['id']}/subscription", json={"plan_id": _plan(client, "agencia-30")["id"]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "PAGOS_NO_CONFIGURADOS"
    assert _simulate(client, "subscription", ag["id"]).status_code == 404     # el simulador no existe si no está habilitado
    with pytest.raises(ValueError):                                           # y en producción la API no arranca con el simulador
        from app.core.config import Settings
        Settings(env="production", payments_simulator=True, cookie_secure=True, image_storage="cloudinary",
                 jwt_secret="x" * 48, cors_origins="https://girando.app")


def test_agency_subscribes_and_upgrades_30_60_100_only_with_approved_payment(client, sim):
    register(client)
    ag = make_agency(client, name="Agencia Crece")
    limit = lambda: client.get(f"/api/me/agencies/{ag['id']}/billing").json()["usage"]["limit"]  # noqa: E731
    p30, p60, p100 = (_plan(client, c) for c in ("agencia-30", "agencia-60", "agencia-100"))
    assert (p30["max_active_listings"], p60["max_active_listings"], p100["max_active_listings"]) == (30, 60, 100)
    r = client.post(f"/api/me/agencies/{ag['id']}/subscription", json={"plan_id": p30["id"]})
    assert r.status_code == 201 and r.json()["simulated"] is True and r.json()["status"] == "pending"
    sub_id = r.json()["subscription_id"]
    assert limit() == 1                                                       # pedir el plan no da nada
    intruder = _user("Intruso")
    assert _simulate(intruder, "subscription", sub_id).status_code == 404     # nadie aprueba pagos ajenos
    assert _simulate(client, "subscription", sub_id, outcome="rejected", event_id="alta-rechazo").status_code == 200
    assert limit() == 1                                                       # pago rechazado: sigue sin plan
    assert _simulate(client, "subscription", sub_id, event_id="alta-ok").json() == {"ok": True}
    assert limit() == 30
    assert _simulate(client, "subscription", sub_id, event_id="alta-ok").json() == {"ok": True, "duplicate": True}   # webhook repetido
    b = client.get(f"/api/me/agencies/{ag['id']}/billing").json()
    assert b["subscription"]["status"] == "active" and len([p for p in b["payments"] if p["status"] == "approved"]) == 1
    end_30 = b["subscription"]["current_period_end"]

    # subir a 60: el límite cambia recién con el pago aprobado
    r = client.post(f"/api/me/agencies/{ag['id']}/subscription/upgrade", json={"plan_id": p60["id"]})
    assert r.status_code == 201 and float(r.json()["amount"]) == float(p60["price_amount"]), r.text
    pay60 = r.json()["payment_id"]
    assert limit() == 30
    assert _simulate(intruder, "payment", pay60).status_code == 404
    assert _simulate(client, "payment", pay60, outcome="rejected", event_id="up60-no").status_code == 200
    assert limit() == 30
    assert _simulate(client, "payment", pay60, event_id="up60-ok").json() == {"ok": True}
    assert limit() == 60
    assert _simulate(client, "payment", pay60, event_id="up60-ok").json()["duplicate"] is True
    assert _simulate(client, "payment", pay60, event_id="up60-otra-vez").status_code == 200       # otro aviso del mismo pago: no reaplica
    b = client.get(f"/api/me/agencies/{ag['id']}/billing").json()
    assert b["subscription"]["plan_name"] == "Agencia 60" and float(b["subscription"]["price_amount"]) == float(p60["price_amount"])
    assert b["subscription"]["current_period_end"] >= end_30                  # el período se reinicia desde el pago (sin prorrateo)

    # subir a +60 (100)
    pay100 = client.post(f"/api/me/agencies/{ag['id']}/subscription/upgrade", json={"plan_id": p100["id"]}).json()["payment_id"]
    assert _simulate(client, "payment", pay100, event_id="up100-ok").status_code == 200 and limit() == 100
    # "subir" a un plan menor o igual no es una mejora; el plan de otro rubro tampoco
    r = client.post(f"/api/me/agencies/{ag['id']}/subscription/upgrade", json={"plan_id": p30["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_ES_UNA_MEJORA"
    assert client.post(f"/api/me/agencies/{ag['id']}/subscription/upgrade", json={"plan_id": _plan(client, "repuestos")["id"]}).status_code == 422
    # bajar de plan: queda pendiente, el límite no cambia hasta la renovación
    r = client.post(f"/api/me/agencies/{ag['id']}/subscription/downgrade", json={"plan_id": p30["id"]})
    assert r.status_code == 200 and r.json()["pending_plan"] == "Agencia 30" and limit() == 100
    with pytest.raises(DBAPIError), unit_of_work("app", _uid(client), RequestContext()) as c:   # el titular no puede "bajar" hacia arriba gratis
        c.execute(text("UPDATE app.subscriptions SET pending_plan_id = :p WHERE id = :s"), {"p": p100["id"], "s": sub_id})
    assert client.delete(f"/api/me/agencies/{ag['id']}/subscription/downgrade").status_code == 200
    # el historial del usuario muestra pagos y cambios de plan
    h = client.get("/api/me/history").json()
    assert sum(1 for p in h["payments"] if p["status"] == "approved") == 3 and any(p["is_plan_change"] for p in h["payments"])
    assert intruder.get("/api/me/history").json()["payments"] == []
    # cancelar
    assert client.post(f"/api/me/agencies/{ag['id']}/subscription/cancel").json()["status"] == "canceled"
    assert limit() == 100                                                     # cancelada: sigue hasta el fin del período pago
    with _w() as c:                                                           # todo quedó en auditoría
        n = c.execute(text("SELECT count(*) FROM app.audit_logs WHERE entity_type = 'subscriptions' AND entity_id = :s"), {"s": sub_id}).scalar()
    assert n >= 4


def test_downgrade_applies_on_renewal_and_pauses_excess_without_deleting(client, sim):
    with _w() as c:       # dos planes chicos para poder excederlos en un test
        for code, n, price, order in (("test-dos", 2, 2000, 98), ("test-uno", 1, 1000, 99)):
            c.execute(text("""INSERT INTO app.plans (code, name, audience, price_amount, billing_period, max_active_listings, sort_order)
                              VALUES (:c, :c, 'agency', :p, 'month', :n, :o) ON CONFLICT (code) DO NOTHING"""), {"c": code, "n": n, "p": price, "o": order})
    register(client)
    ag = make_agency(client, name="Agencia Baja")
    sub_id = client.post(f"/api/me/agencies/{ag['id']}/subscription", json={"plan_id": _plan(client, "test-dos")["id"]}).json()["subscription_id"]
    assert _simulate(client, "subscription", sub_id, event_id="baja-alta").status_code == 200
    a, _ = _published_listing(client, agency_id=ag["id"])
    b, _ = _published_listing(client, year=2016, agency_id=ag["id"])
    assert client.post(f"/api/me/agencies/{ag['id']}/subscription/downgrade", json={"plan_id": _plan(client, "test-uno")["id"]}).status_code == 200
    statuses = lambda: sorted(i["status"] for i in client.get("/api/me/listings", params={"agency_id": ag["id"], "group": "todas"}).json()["items"])  # noqa: E731
    assert statuses() == ["published", "published"]                           # hasta la renovación no cambia nada
    with _w() as c:                                                           # llega la fecha de renovación
        c.execute(text("UPDATE app.subscriptions SET current_period_end = now() + interval '1 day' WHERE id = :s"), {"s": sub_id})
    assert _simulate(client, "subscription", sub_id, event_id="baja-renueva").status_code == 200
    bill = client.get(f"/api/me/agencies/{ag['id']}/billing").json()
    assert bill["usage"]["limit"] == 1 and float(bill["subscription"]["price_amount"]) == 1000
    assert statuses() == ["paused", "published"]                              # lo que excede se pausa, no se borra
    assert {a, b} == {i["id"] for i in client.get("/api/me/listings", params={"agency_id": ag["id"], "group": "todas"}).json()["items"]}


def test_particular_buys_featured_listing_and_it_activates_only_when_paid(client, sim):
    sup = _staff("superadmin")
    prod = next(p for p in sup.get("/api/admin/promotion-products").json()["items"] if p["code"] == "destacada")
    assert _staff("admin").patch(f"/api/admin/promotion-products/{prod['id']}", json={"is_active": True}).status_code == 403   # precios: solo Super Admin
    assert sup.patch(f"/api/admin/promotion-products/{prod['id']}", json={"is_active": True, "price_amount": "5000"}).json()["is_active"] is True
    register(client)
    lid, code = _published_listing(client)
    assert any(p["code"] == "destacada" and float(p["price_amount"]) == 5000 for p in new_client().get("/api/promotion-products").json()["items"])
    other = _user("Otro")
    assert other.post("/api/me/promotions", json={"product_code": "destacada", "listing_id": lid}).status_code == 422   # no destaca lo ajeno
    r = client.post("/api/me/promotions", json={"product_code": "destacada", "listing_id": lid})
    assert r.status_code == 201 and float(r.json()["amount"]) == 5000, r.text
    pay, promo = r.json()["payment_id"], r.json()["promotion_id"]
    assert client.post("/api/me/promotions", json={"product_code": "destacada", "listing_id": lid}).status_code == 409
    in_ads = lambda: any(a["public_code"] == code for a in new_client().get("/api/ads", params={"page": "home"}).json()["items"])  # noqa: E731
    assert not in_ads()
    assert sup.post(f"/api/admin/promotions/{promo}/activate", json={}).status_code == 409     # ni el Super Admin la activa sin pago
    assert _simulate(client, "payment", pay, outcome="rejected", event_id="promo-no").status_code == 200 and not in_ads()
    assert _simulate(client, "payment", pay, event_id="promo-ok").status_code == 200 and in_ads()
    mine = client.get("/api/me/promotions").json()["items"][0]
    assert mine["status"] == "active" and mine["payment_status"] == "approved" and mine["disclosure_label"] == "Patrocinado"
    with _w() as c:
        ev = [r[0] for r in c.execute(text("SELECT event::text FROM app.promotion_events WHERE promotion_id = :p ORDER BY id"), {"p": promo})]
    assert ev == ["payment_failed", "payment_approved", "activated"]
    sup.patch(f"/api/admin/promotion-products/{prod['id']}", json={"is_active": False})


# =========================================================================== 5. repuestos: pago + verificación
def test_parts_store_needs_payment_and_onsite_verification(client, sim):
    register(client)
    store = make_agency(client, name="Repuestos del Test", kind="parts_store")
    part = {"category": "brakes", "condition": "new", "brand_id": catalog_ids(client)["brand_id"], "part_brand": "Marca X"}
    pid = _post(client, "part", part, agency_id=store["id"], price_amount="45000").json()["id"]
    r = client.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REQUIERE_PAGO_Y_VERIFICACION"
    # sin pago aprobado no se puede ni pedir la verificación presencial, ni verificarla desde el Admin
    r = client.post(f"/api/me/agencies/{store['id']}/verification")
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAGO_REQUERIDO_ANTES_DE_VERIFICAR"
    mod = _staff("moderator")
    assert mod.post(f"/api/admin/agencies/{store['id']}/verify", json={}).status_code == 409
    # paga la suscripción de repuestos ($ 4.000, valor inicial editable)
    plan = _plan(client, "repuestos")
    assert float(plan["price_amount"]) == 4000 and plan["requires_verification"] is True
    assert client.post(f"/api/me/agencies/{store['id']}/subscription", json={"plan_id": _plan(client, "agencia-30")["id"]}).status_code == 422
    sub_id = client.post(f"/api/me/agencies/{store['id']}/subscription", json={"plan_id": plan["id"]}).json()["subscription_id"]
    assert client.post(f"/api/me/agencies/{store['id']}/verification").status_code == 409        # pedido de plan sin pagar: todavía no
    assert _simulate(client, "subscription", sub_id, event_id="rep-ok").status_code == 200
    r = client.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REQUIERE_PAGO_Y_VERIFICACION"   # pagó pero falta la verificación
    assert client.post(f"/api/me/agencies/{store['id']}/verification").status_code == 201
    vid = next(v["id"] for v in mod.get("/api/admin/verifications").json()["items"] if v["agency_id"] == store["id"])
    keys = [i["key"] for i in mod.get(f"/api/admin/verifications/{vid}").json()["items"]]
    assert {"visita", "responsable", "pago"} <= set(keys)                     # checklist propio de repuestos
    assert mod.post(f"/api/admin/agencies/{store['id']}/verify", json={}).json()["status"] == "verified"
    code = _publish_post(client, pid)
    anon = new_client()
    hit = next(i for i in anon.get("/api/posts", params={"vertical": "part", "category": "brakes"}).json()["items"] if i["public_code"] == code)
    assert hit["agency_verified"] is True and hit["condition"] == "new"
    assert any(i["public_code"] == code for i in anon.get("/api/posts", params={"vertical": "part", "brand_id": part["brand_id"]}).json()["items"])
    assert any(o["value"] == "brakes" for o in anon.get("/api/posts/facets", params={"vertical": "part"}).json()["category"])
    # la suscripción se vence: deja de verse en el acto y el worker pausa el catálogo (no lo borra)
    with _w() as c:
        c.execute(text("UPDATE app.subscriptions SET status = 'expired', ended_at = now() WHERE id = :s"), {"s": sub_id})
    assert all(i["public_code"] != code for i in anon.get("/api/posts", params={"vertical": "part"}).json()["items"])
    from app.cli import job_plan_limits
    with _w() as c:
        assert job_plan_limits(c) >= 1
    assert client.get(f"/api/me/posts/{pid}").json()["status"] == "paused"
    # un particular o una agencia de autos no publican repuestos
    assert _post(_user("Suelto"), "part", part).status_code == 422
    car_agency = make_agency(client, name="Autos y nada más")
    assert _post(client, "part", part, agency_id=car_agency["id"]).status_code == 422


# =========================================================================== 6. taxis, servicios y empleos
def test_taxi_post_shows_legal_notice_and_seal_is_only_by_girando(client):
    register(client)
    r = _post(client, "taxi", {**TAXI, "offer_kind": "vehicle_only"})
    assert r.status_code == 422                                              # vehículo apto taxi no lleva número de permiso
    r = _post(client, "taxi", TAXI, price_amount="30000000", title="Permiso de taxi Godoy Cruz")
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    code = _publish_post(client, pid)
    anon = new_client()
    res = anon.get("/api/posts", params={"vertical": "taxi", "offer_kind": "permit_only", "service_type": "taxi"}).json()
    assert "Ley 9086" in res["legal_notice"] and "no garantiza" in res["legal_notice"]
    hit = next(i for i in res["items"] if i["public_code"] == code)
    assert hit["permit_verified"] is False and hit["permit_number"] == "1234" and "permit_holder_declared" not in hit   # el titular nunca es público
    det = anon.get(f"/api/posts/{code}").json()
    assert "Dirección de Transporte" in det["legal_notice"] and "permit_holder_declared" not in det and det["vehicle_age_note"]
    assert all(i["public_code"] != code for i in anon.get("/api/posts", params={"vertical": "taxi", "verified": True}).json()["items"])
    assert client.post(f"/api/admin/posts/{pid}/seal", json={"verified": True, "note": "Me lo verifico solo"}).status_code == 403
    with pytest.raises(DBAPIError), unit_of_work("app", _uid(client), RequestContext()) as c:
        c.execute(text("UPDATE app.taxi_posts SET permit_verified_at = now() WHERE post_id = :p"), {"p": pid})
    mod = _staff("moderator")
    assert mod.post(f"/api/admin/posts/{pid}/seal", json={"verified": True}).status_code == 422       # el sello exige anotar qué se comprobó
    assert mod.post(f"/api/admin/posts/{pid}/seal", json={"verified": True, "note": "Constancia de la Dirección de Transporte vista"}).status_code == 200
    assert any(i["public_code"] == code for i in anon.get("/api/posts", params={"vertical": "taxi", "verified": True}).json()["items"])
    # cambiar el número declarado quita el sello
    assert client.post(f"/api/me/posts/{pid}/transition", json={"to": "paused"}).status_code == 200
    client.patch(f"/api/me/posts/{pid}", json={"details": {**TAXI, "permit_number": "9999"}})
    with _w() as c:
        assert c.execute(text("SELECT permit_verified_at FROM app.taxi_posts WHERE post_id = :p"), {"p": pid}).scalar() is None


def test_service_provider_one_card_per_category_and_zone(client):
    register(client)
    assert _post(client, "service", {"category": "tow"}).status_code == 422                  # un particular no publica servicios
    prov = make_agency(client, name="Grúas del Test", kind="service_provider")
    assert client.get(f"/api/me/agencies/{prov['id']}/billing").json()["usage"]["plan"]["code"] == "servicios"   # plan gratis por defecto, configurable
    assert _post(client, "service", {"category": "insurance_broker"}, agency_id=prov["id"]).status_code == 422   # productor sin matrícula SSN
    r = _post(client, "service", {"category": "tow", "open_24h": True, "at_home": True, "vehicle_types": ["car", "light_truck"]}, agency_id=prov["id"])
    assert r.status_code == 201, r.text
    code = _publish_post(client, r.json()["id"])
    dup = _post(client, "service", {"category": "tow"}, agency_id=prov["id"]).json()["id"]
    r = client.post(f"/api/me/posts/{dup}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "FICHA_DUPLICADA"
    other_zone = _post(client, "service", {"category": "tow"}, agency_id=prov["id"], geo_area_id=geo_id(client, "Maipú")).json()["id"]
    assert client.post(f"/api/me/posts/{other_zone}/transition", json={"to": "pending"}).status_code == 200      # otra zona sí
    broker = _post(client, "service", {"category": "insurance_broker", "license_number": "84584"}, agency_id=prov["id"]).json()["id"]
    bcode = _publish_post(client, broker)
    anon = new_client()
    q = lambda **p: [i["public_code"] for i in anon.get("/api/posts", params={"vertical": "service", **p}).json()["items"]]  # noqa: E731
    assert code in q(category="tow", open_24h=True, at_home=True, vehicle_type="light_truck") and code not in q(category="mechanic")
    assert bcode in q(category="insurance_broker") and bcode not in q(category="insurance_broker", verified=True)   # matrícula declarada ≠ verificada
    assert _staff("moderator").post(f"/api/admin/posts/{broker}/seal", json={"verified": True, "note": "Matrícula vista en el registro de la SSN"}).status_code == 200
    assert bcode in q(category="insurance_broker", verified=True)
    f = anon.get("/api/posts/facets", params={"vertical": "service"}).json()
    assert {o["value"] for o in f["category"]} >= {"tow", "insurance_broker"} and f["total"] >= 2


def test_post_permissions_by_direct_api(client):
    register(client)
    pid = _post(client, "job", JOB).json()["id"]
    other = _user("Ajeno")
    assert other.get(f"/api/me/posts/{pid}").status_code == 404
    assert other.patch(f"/api/me/posts/{pid}", json={"title": "Me lo apropio"}).status_code == 404
    assert other.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"}).status_code == 404
    assert client.post(f"/api/admin/posts/{pid}/approve", json={}).status_code == 403            # el dueño no se aprueba
    assert client.get("/api/admin/posts").status_code == 403 and client.get("/api/admin/financing-offers").status_code == 403
    assert client.get("/api/admin/reported-messages").status_code == 403
    assert client.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"}).status_code == 200
    with pytest.raises(DBAPIError), unit_of_work("app", _uid(client), RequestContext()) as c:
        c.execute(text("UPDATE app.posts SET status = 'published' WHERE id = :p"), {"p": pid})
    assert new_client().get("/api/me/posts").status_code == 401
    mod = _staff("moderator")
    assert mod.post(f"/api/admin/posts/{pid}/reject", json={}).status_code == 422                # rechazar pide motivo
    assert mod.post(f"/api/admin/posts/{pid}/request_changes", json={"reason": "Falta el detalle del puesto"}).json()["status"] == "requires_changes"
    assert any(n["type_code"] == "listing.changes_requested" for n in client.get("/api/me/notifications").json()["items"])


# =========================================================================== 7. empleos + mensajería sin CVs
def test_candidate_contacts_employer_by_messages_without_cv(client):
    register(client, name="Empleador SA")
    code = _publish_post(client, _post(client, "job", JOB, title="Chofer de reparto con D1").json()["id"])
    anon = new_client()
    assert any(i["public_code"] == code and i["license_classes"] == ["D1"] for i in
               anon.get("/api/posts", params={"vertical": "job", "role": "driver", "license_class": "D1", "modality": "on_route"}).json()["items"])
    assert anon.post("/api/me/conversations", json={"post_code": code, "message": "Hola"}).status_code == 401
    assert client.post("/api/me/conversations", json={"post_code": code, "message": "Me postulo solo"}).status_code == 422   # no a tu propio aviso
    cand = _user("Candidata")
    r = cand.post("/api/me/conversations", json={"post_code": code, "message": "Hola, tengo licencia D1 y 5 años de experiencia."})
    assert r.status_code == 201, r.text
    conv = r.json()
    assert conv["vertical"] == "job" and conv["counterpart"] == "Empleador SA"
    blob = str(conv) + str(cand.get(f"/api/me/conversations/{conv['id']}").json())
    assert "@girando.test" not in blob and "phone" not in blob and "user_id" not in blob              # sin emails, teléfonos ni ids de usuario
    # no existe ninguna ruta para subir CVs o adjuntos
    paths = anon.get("/openapi.json").json()["paths"]
    assert not any(k in p.lower() for p in paths for k in ("cv", "resume", "curriculum", "attachment", "adjunto"))
    inbox = client.get("/api/me/conversations").json()
    assert inbox["unread_total"] == 1 and inbox["items"][0]["counterpart"] == "Candidata"
    assert any(n["type_code"] == "message.new" for n in client.get("/api/me/notifications").json()["items"])
    assert "experiencia" not in str(client.get("/api/me/notifications").json())                      # la notificación no copia el texto
    msgs = client.get(f"/api/me/conversations/{conv['id']}").json()["messages"]
    assert msgs[0]["mine"] is False and client.get("/api/me/conversations").json()["unread_total"] == 0
    assert client.post(f"/api/me/conversations/{conv['id']}/messages", json={"body": "Gracias, te esperamos el lunes."}).status_code == 201
    r = cand.post(f"/api/me/conversations/{conv['id']}/messages", json={"body": "Hola, tengo licencia D1 y 5 años de experiencia."})
    assert r.status_code == 429 and r.json()["error"]["code"] == "MENSAJE_REPETIDO"
    third = _user("Tercero")
    assert third.get(f"/api/me/conversations/{conv['id']}").status_code == 404
    assert third.post(f"/api/me/conversations/{conv['id']}/messages", json={"body": "Me meto"}).status_code == 404
    # reportar y moderar: moderación solo ve conversaciones con reporte
    mid = next(m["id"] for m in cand.get(f"/api/me/conversations/{conv['id']}").json()["messages"] if not m["mine"])
    mod = _staff("moderator")
    assert all(m["message_id"] != mid for m in mod.get("/api/admin/reported-messages").json()["items"])
    reason = next(x["id"] for x in anon.get("/api/report-reasons", params={"target": "message"}).json()["items"])
    assert cand.post(f"/api/me/messages/{mid}/report", json={"reason_id": reason}).status_code == 201
    assert any(m["message_id"] == mid for m in mod.get("/api/admin/reported-messages").json()["items"])
    assert mod.post(f"/api/admin/messages/{mid}/hide").status_code == 200
    hidden = next(m for m in cand.get(f"/api/me/conversations/{conv['id']}").json()["messages"] if m["id"] == mid)
    assert hidden["hidden"] is True and hidden["body"] is None
    # bloquear: no se puede seguir escribiendo, ni en otra publicación
    assert cand.post(f"/api/me/conversations/{conv['id']}/block").status_code == 200
    r = client.post(f"/api/me/conversations/{conv['id']}/messages", json={"body": "¿Seguís ahí?"})
    assert r.status_code == 403 and r.json()["error"]["code"] in ("CONVERSACION_BLOQUEADA", "USUARIO_BLOQUEADO")


def test_message_retention_job_purges_old_conversations(client):
    register(client, name="Vende")
    _, code = _published_listing(client)
    buyer = _user("Compra")
    conv = buyer.post("/api/me/conversations", json={"listing_code": code, "message": "¿Sigue disponible?"}).json()
    assert conv["vertical"] == "vehicle"
    from app.cli import job_purge_messages
    with _w() as c:
        assert job_purge_messages(c) == 0                                    # dentro del plazo de retención no se borra nada
        c.execute(text("UPDATE app.conversations SET last_message_at = now() - interval '13 months' WHERE id = :c"), {"c": conv["id"]})
        assert job_purge_messages(c) == 1
    assert buyer.get(f"/api/me/conversations/{conv['id']}").json()["messages"] == []


# =========================================================================== 8. publicidad medida y recomendaciones con consentimiento
def test_ads_events_are_real_and_respect_consent(client):
    register(client)
    lid, code = _published_listing(client)
    sup = _staff("superadmin")
    now = datetime.now(UTC)
    promo = sup.post("/api/admin/promotions", json={"type": "featured_listing", "placement": "home_featured", "listing_code": code, "notes": "Cortesía de prueba",
                                                    "starts_at": (now - timedelta(hours=1)).isoformat(), "ends_at": (now + timedelta(days=3)).isoformat()}).json()
    assert sup.post(f"/api/admin/promotions/{promo['id']}/activate", json={}).status_code == 200
    visitor = new_client()
    ad = next(a for a in visitor.get("/api/ads", params={"vertical": "vehicles", "page": "home"}).json()["items"] if a["promotion_id"] == promo["id"])
    assert ad["disclosure_label"] == "Patrocinado"                           # siempre rotulado
    ev = lambda name: {"name": name, "promotion_id": promo["id"], "placement": "home_featured", "vertical": "vehicles", "page": "home"}  # noqa: E731
    assert visitor.get("/api/consents/cookies").json() == {"decided": False, "analytics": False}
    assert visitor.post("/api/events", json={"events": [ev("promotion_impression"), ev("promotion_click")]}).json()["accepted"] == 2
    fake = "00000000-0000-4000-8000-000000000000"
    assert visitor.post("/api/events", json={"events": [{**ev("promotion_impression"), "promotion_id": fake}]}).json()["accepted"] == 0   # no se infla nada
    assert visitor.post("/api/events", json={"events": [{"name": "page_view"}]}).status_code == 422
    with _w() as c:
        got = c.execute(text("""SELECT count(*), count(user_id), count(anonymous_id), bool_or(consent_analytics) FROM app.analytics_events
                                 WHERE promotion_id = :p"""), {"p": promo["id"]}).one()
    assert tuple(got) == (2, 0, 0, False)                                    # sin consentimiento: se cuenta, sin identificadores
    assert visitor.post("/api/consents/cookies", json={"analytics": True}).json()["analytics"] is True
    assert visitor.get("/api/consents/cookies").json()["analytics"] is True
    visitor.post("/api/events", json={"events": [ev("promotion_impression")]})
    with _w() as c:
        assert c.execute(text("SELECT count(anonymous_id) FROM app.analytics_events WHERE promotion_id = :p AND consent_analytics"), {"p": promo["id"]}).scalar() == 1
    assert visitor.post("/api/consents/cookies", json={"analytics": False}).json()["analytics"] is False     # se puede retirar
    visitor.post("/api/events", json={"events": [ev("promotion_impression")]})
    with _w() as c:
        assert c.execute(text("SELECT count(anonymous_id) FROM app.analytics_events WHERE promotion_id = :p"), {"p": promo["id"]}).scalar() == 1
    rep = sup.get(f"/api/me/promotions/{promo['id']}/report").json()         # reporte para el anunciante: números reales
    assert int(rep["promotion"]["impressions"]) == 3 and int(rep["promotion"]["clicks"]) == 1 and rep["ctr"] is None
    assert _user("Curioso").get(f"/api/me/promotions/{promo['id']}/report").status_code == 404


def test_recommendations_are_explained_and_personalized_only_with_consent(client):
    register(client, name="Vendedor A")
    lid_a, code_a = _published_listing(client)
    seller_b = _user("Vendedor B")
    lid_b, code_b = _published_listing(seller_b, price_amount="9900000")
    anon = new_client()
    sim_items = anon.get(f"/api/listings/{code_a}/similar").json()
    hit = next(i for i in sim_items["items"] if i["id"] == lid_b)
    assert sim_items["basis"] == "contexto" and {"Mismo modelo", "Precio parecido", "Misma zona"} <= set(hit["reasons"])
    assert all(i["id"] != lid_a for i in sim_items["items"])
    fan = _user("Interesado")
    assert fan.put(f"/api/me/favorites/{lid_a}").status_code in (200, 201, 204)
    r = fan.get("/api/recommendations").json()
    assert r["personalized"] is False and r["basis"] != "actividad"          # sin consentimiento no se usa su actividad
    r = fan.get("/api/recommendations", params={"model_id": catalog_ids(fan)["model_id"]}).json()
    assert r["basis"] == "contexto" and all(i["reasons"] for i in r["items"])
    assert fan.post("/api/consents/cookies", json={"analytics": True}).status_code == 200
    r = fan.get("/api/recommendations").json()
    assert r["personalized"] is True and r["basis"] == "actividad"
    assert any(i["id"] == lid_b and "Mismo modelo" in i["reasons"] for i in r["items"]) and all(i["id"] != lid_a for i in r["items"])
    # historial: vistos recientemente (propio, borrable) y búsquedas guardadas con aviso
    fan.get(f"/api/listings/{code_b}")
    assert [v["id"] for v in fan.get("/api/me/history").json()["recently_viewed"]] == [lid_b]
    assert fan.delete("/api/me/history/viewed").status_code == 204 and fan.get("/api/me/history").json()["recently_viewed"] == []
    assert fan.post("/api/me/saved-searches", json={"name": "Gol", "filters": {"hack": "1"}}).status_code == 422
    ss = fan.post("/api/me/saved-searches", json={"name": "Gol Trend hasta 10M", "filters": {"q": "gol", "price_max": 10000000, "body_type": ["hatchback"]}})
    assert ss.status_code == 201, ss.text
    lid_c, _ = _published_listing(_user("Vendedor C"), price_amount="9000000")
    from app.cli import job_saved_searches
    with _w() as c:
        assert job_saved_searches(c) >= 1
    assert any(n["type_code"] == "search.new_results" for n in fan.get("/api/me/notifications").json()["items"])
    with _w() as c:
        job_saved_searches(c)                                               # no repite el aviso dentro de la frecuencia
    assert sum(1 for n in fan.get("/api/me/notifications").json()["items"] if n["type_code"] == "search.new_results") == 1


def test_favorite_gets_notified_on_price_drop(client):
    register(client)
    lid, _ = _published_listing(client)
    fan = _user("Guardó")
    fan.put(f"/api/me/favorites/{lid}")
    assert client.patch(f"/api/me/listings/{lid}", json={"price_amount": "9900000"}).status_code == 200     # sube: no avisa
    assert not any(n["type_code"] == "favorite.price_drop" for n in fan.get("/api/me/notifications").json()["items"])
    assert client.patch(f"/api/me/listings/{lid}", json={"price_amount": "8900000"}).status_code == 200
    assert any(n["type_code"] == "favorite.price_drop" for n in fan.get("/api/me/notifications").json()["items"])
