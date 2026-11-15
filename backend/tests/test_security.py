from sqlalchemy import text

from tests.conftest import full_listing_payload, new_client, register


def test_user_cannot_edit_foreign_listing(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    other = new_client()
    register(other)
    assert other.get(f"/api/me/listings/{lid}").status_code == 404
    assert other.patch(f"/api/me/listings/{lid}", json={"title": "hackeado"}).status_code == 404
    assert other.post(f"/api/me/listings/{lid}/transition", json={"to": "deleted"}).status_code == 404
    assert other.post(f"/api/me/listings/{lid}/images", files={"file": ("a.jpg", b"x" * 200, "image/jpeg")}).status_code in (404, 422)
    assert client.get(f"/api/me/listings/{lid}").json()["title"] == "Gol Trend muy cuidado"


def test_user_cannot_access_admin(client):
    register(client)
    for path in ("/api/admin/dashboard", "/api/admin/users", "/api/admin/listings", "/api/admin/catalog/brands", "/api/admin/audit"):
        r = client.get(path)
        assert r.status_code == 403, path
    assert new_client().get("/api/admin/dashboard").status_code == 401


def test_user_cannot_escalate_via_payload(client):
    register(client)
    # campos desconocidos (rol, status, plan) se rechazan
    r = client.post("/api/me/listings", json={"title": "x", "status": "published"})
    assert r.status_code == 422
    r = client.patch("/api/me/profile", json={"display_name": "Nuevo", "role": "admin"})
    assert r.status_code == 422


def test_user_cannot_modify_subscription_or_verify_self(client):
    email, user = register(client)
    uid = user["id"]
    from app.core.db import unit_of_work
    with unit_of_work("worker") as conn:
        plan = conn.execute(text("SELECT id FROM app.plans WHERE code = 'agencia-30'")).scalar()
    with unit_of_work("app", uid) as conn:
        try:
            conn.execute(text("""INSERT INTO app.subscriptions (plan_id, user_id, created_by, provider, status, price_amount, currency, billing_period,
                                   started_at, current_period_end) VALUES (:p, :u, :u, 'bank_transfer', 'active', 1, 'ARS', 'month', now(), now() + interval '1 month')"""),
                         {"p": plan, "u": uid})
            raise AssertionError("se pudo crear una suscripción activa")
        except Exception as e:  # noqa: BLE001
            assert "LAS_SUSCRIPCIONES_NACEN_PENDIENTES" in str(e)


def test_identity_self_verification_blocked(client):
    _, user = register(client)
    from app.core.db import unit_of_work
    try:
        with unit_of_work("app", user["id"]) as conn:
            conn.execute(text("UPDATE app.users SET identity_verified_at = now() WHERE id = :u"), {"u": user["id"]})
        raise AssertionError("pudo autoverificarse")
    except Exception as e:  # noqa: BLE001
        assert "CAMPO_NO_EDITABLE" in str(e)


def test_documents_of_others_not_visible(client):
    _, a = register(client)
    b_client = new_client()
    _, b = register(b_client)
    from app.core.db import unit_of_work
    with unit_of_work("app", a["id"]) as conn:
        conn.execute(text("""INSERT INTO app.documents (uploaded_by, owner_user_id, type, storage_provider, storage_bucket, storage_key, mime_type, bytes, sha256)
                             VALUES (:u, :u, 'dni_front', 'r2', 'girando-docs', :k, 'image/jpeg', 1000, digest('x','sha256'))"""),
                     {"u": a["id"], "k": f"docs/user/{a['id']}/dni.jpg"})
    with unit_of_work("app", b["id"]) as conn:
        assert conn.execute(text("SELECT count(*) FROM app.documents")).scalar() == 0
    with unit_of_work("anon") as conn:
        try:
            conn.execute(text("SELECT count(*) FROM app.documents"))
            raise AssertionError("anon leyó documentos")
        except Exception as e:  # noqa: BLE001
            assert "permission denied" in str(e)


def test_security_headers_and_no_cache(client):
    r = client.get("/api/health")
    for h in ("x-content-type-options", "referrer-policy", "permissions-policy", "content-security-policy", "x-request-id"):
        assert h in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_cors_only_allowed_origins(client):
    r = client.options("/api/listings", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    r = client.options("/api/listings", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_production_config_guards(monkeypatch):
    import pytest

    from app.core.config import Settings
    with pytest.raises(ValueError):
        Settings(env="production", cors_origins=["*"], jwt_secret="x" * 40, cookie_secure=True, image_storage="cloudinary",
                 database_url="postgresql+psycopg://a:b@h/d", db_api_password="strong-pass")


def test_xss_payload_stored_as_text(client):
    register(client)
    payload = '<script>alert(1)</script><img src=x onerror=alert(1)>'
    r = client.post("/api/me/listings", json={"title": payload[:90], "description": payload})
    assert r.status_code == 201 and r.json()["description"] == payload  # se guarda texto; se renderiza escapado
    assert r.headers["content-type"].startswith("application/json")


def test_sql_injection_is_inert(client):
    anon = new_client()
    r = anon.get("/api/listings", params={"q": "'; DROP TABLE app.users; --"})
    assert r.status_code == 200
    register(client)  # la tabla sigue existiendo


def test_x_real_ip_only_trusted_from_proxy():
    from types import SimpleNamespace

    from app.core.middleware import client_ip
    spoof = SimpleNamespace(headers={"x-real-ip": "1.2.3.4"}, client=SimpleNamespace(host="203.0.113.9"))
    assert client_ip(spoof) == "203.0.113.9"  # un cliente directo no puede elegir su IP
    proxied = SimpleNamespace(headers={"x-real-ip": "1.2.3.4"}, client=SimpleNamespace(host="127.0.0.1"))
    assert client_ip(proxied) == "1.2.3.4"


def test_documents_bucket_private_and_signed(monkeypatch):
    import pytest

    from app.core.config import get_settings
    from app.integrations import NotConfigured
    from app.integrations.documents import DocumentStorage
    with pytest.raises(NotConfigured):
        DocumentStorage()  # sin credenciales no hay subida simulada
    for k, v in {"DOCUMENTS_BUCKET": "girando-docs", "DOCUMENTS_ENDPOINT_URL": "https://acc.r2.cloudflarestorage.com",
                 "DOCUMENTS_ACCESS_KEY_ID": "AKID", "DOCUMENTS_SECRET_ACCESS_KEY": "secret"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        url = DocumentStorage().presign("GET", "verifications/abc123/dni.pdf", ttl=99999)
        assert url.startswith("https://acc.r2.cloudflarestorage.com/girando-docs/verifications/abc123/dni.pdf?")
        assert "X-Amz-Expires=600" in url and "X-Amz-Signature=" in url and "secret" not in url
        with pytest.raises(ValueError):
            DocumentStorage().presign("GET", "../otro/archivo.pdf")
    finally:
        get_settings.cache_clear()
