"""Suscripciones: el frontend nunca activa nada. Solo el webhook firmado de Mercado Pago + GET al recurso."""
import hashlib
import hmac

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import scalar, unit_of_work
from tests.conftest import full_listing_payload, geo_id, new_client, register


def _cuit():
    import random
    base = "30" + "".join(random.choice("0123456789") for _ in range(8))
    s = sum(int(d) * w for d, w in zip(base, [5, 4, 3, 2, 7, 6, 5, 4, 3, 2], strict=True))
    dv = 11 - s % 11
    if dv == 10:
        return _cuit()
    return base + str(0 if dv == 11 else dv)


def _agency(c):
    r = c.post("/api/me/agencies", json={"legal_name": "Autos Test S.R.L.", "trade_name": "Autos Test", "cuit": _cuit(), "geo_area_id": geo_id(c)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _agency_plan(c):
    return next(p for p in c.get("/api/plans").json()["items"] if p["audience"] == "agency" and float(p["price_amount"]) > 0)


def test_subscribe_without_mp_is_refused_and_creates_nothing(client):
    register(client)
    aid = _agency(client)
    plan = _agency_plan(client)
    r = client.post(f"/api/me/agencies/{aid}/subscription", json={"plan_id": plan["id"]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "PAGOS_NO_CONFIGURADOS"
    b = client.get(f"/api/me/agencies/{aid}/billing").json()
    assert b["subscription"] is None and b["usage"]["limit"] == 1 and b["payments_enabled"] is False


def test_user_cannot_self_activate_subscription(client):
    register(client)
    aid = _agency(client)
    plan = _agency_plan(client)
    uid = client.get("/api/me/profile").json()["id"]
    import pytest
    from sqlalchemy.exc import DBAPIError

    from app.core.db import RequestContext
    # Aun escribiendo directo en la base con el rol de la app, el trigger impide nacer activa
    with pytest.raises(DBAPIError), unit_of_work("app", uid, RequestContext()) as conn:
        conn.execute(text("""INSERT INTO app.subscriptions (plan_id, agency_id, created_by, provider, price_amount, currency, billing_period, status, started_at, current_period_end)
                             VALUES (:p, :a, :u, 'mercadopago', 1, 'ARS', 'month', 'active', now(), now() + interval '1 month')"""),
                     {"p": plan["id"], "a": aid, "u": uid})


def _sign(secret, data_id, req_id, ts="1700000000"):
    v1 = hmac.new(secret.encode(), f"id:{data_id};request-id:{req_id};ts:{ts};".encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_webhook_signature_and_activation(client, monkeypatch):
    register(client)
    aid = _agency(client)
    plan = _agency_plan(client)
    monkeypatch.setenv("MERCADOPAGO_ACCESS_TOKEN", "TEST-token")
    monkeypatch.setenv("MERCADOPAGO_WEBHOOK_SECRET", "whsec-test")
    get_settings.cache_clear()
    try:
        from app.integrations import external
        monkeypatch.setattr(external.MercadoPagoService, "create_preapproval", lambda self, **kw: {"id": "pre-123", "init_point": "https://www.mercadopago.com.ar/subscriptions/checkout?x=1"})
        r = client.post(f"/api/me/agencies/{aid}/subscription", json={"plan_id": plan["id"]})
        assert r.status_code == 201, r.text
        sub_id = r.json()["subscription_id"]
        assert client.get(f"/api/me/agencies/{aid}/billing").json()["subscription"]["status"] == "pending"

        # 1) webhook sin firma válida → 401, se registra pero no se procesa
        anon = new_client()
        r = anon.post("/api/webhooks/mercadopago?type=subscription_preapproval&data.id=pre-123", json={"type": "subscription_preapproval", "data": {"id": "pre-123"}},
                      headers={"x-signature": "ts=1,v1=deadbeef", "x-request-id": "req-1"})
        assert r.status_code == 401
        assert client.get(f"/api/me/agencies/{aid}/billing").json()["subscription"]["status"] == "pending"

        # 2) firma válida → el backend consulta a MP (la verdad) y recién ahí activa
        monkeypatch.setattr(external.MercadoPagoService, "get_resource",
                            lambda self, topic, rid: {"id": "pre-123", "status": "authorized", "external_reference": sub_id, "next_payment_date": "2030-01-01T00:00:00Z"})
        r = anon.post("/api/webhooks/mercadopago?type=subscription_preapproval&data.id=pre-123", json={"type": "subscription_preapproval", "data": {"id": "pre-123"}},
                      headers={"x-signature": _sign("whsec-test", "pre-123", "req-2"), "x-request-id": "req-2"})
        assert r.status_code == 200, r.text
        b = client.get(f"/api/me/agencies/{aid}/billing").json()
        assert b["subscription"]["status"] == "active"
        assert b["usage"]["limit"] == plan["max_active_listings"]  # el plan efectivo cambió en la base

        # 3) idempotencia: el mismo evento no se procesa dos veces
        r = anon.post("/api/webhooks/mercadopago?type=subscription_preapproval&data.id=pre-123", json={"type": "subscription_preapproval", "data": {"id": "pre-123"}},
                      headers={"x-signature": _sign("whsec-test", "pre-123", "req-2"), "x-request-id": "req-2"})
        assert r.json().get("duplicate") is True
        with unit_of_work("worker") as conn:
            assert scalar(conn, "SELECT count(*) FROM app.payment_events WHERE resource_id = 'pre-123'") == 2
            assert scalar(conn, "SELECT count(*) FROM app.payment_events WHERE resource_id = 'pre-123' AND signature_valid AND processing_status = 'processed'") == 1

        # 4) la agencia ahora publica con el límite del plan pagado
        lid = client.post("/api/me/listings", json={**full_listing_payload(client), "agency_id": aid}).json()["id"]
        assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200
    finally:
        monkeypatch.delenv("MERCADOPAGO_ACCESS_TOKEN")
        monkeypatch.delenv("MERCADOPAGO_WEBHOOK_SECRET")
        get_settings.cache_clear()


def test_admin_billing_requires_finance(client):
    register(client)
    assert client.get("/api/admin/subscriptions").status_code == 403
    assert client.get("/api/admin/payments").status_code == 403
