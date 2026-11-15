from sqlalchemy import text

from tests.conftest import new_client, register


def test_register_login_me_logout(client):
    email, user = register(client, name="Ana P.")
    assert user["email"] == email and user["role"] == "user" and user["display_name"] == "Ana P."
    assert user["particular_usage"]["limit"] == 1
    assert "gr_at" in client.cookies and "gr_rt" in client.cookies
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == email
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    c2 = new_client()
    r = c2.post("/api/auth/login", json={"email": email.upper(), "password": "Clave-segura-123"})
    assert r.status_code == 200 and r.json()["user"]["email"] == email


def test_password_never_stored_plain(client):
    email, _ = register(client, password="Otra-clave-456")
    from app.core.db import unit_of_work
    with unit_of_work("worker") as conn:
        h = conn.execute(text("SELECT password_hash FROM app.users WHERE email = :e"), {"e": email}).scalar()
    assert h.startswith("$argon2id$") and "Otra-clave-456" not in h


def test_duplicate_email_and_weak_password(client):
    email, _ = register(client)
    c = new_client()
    r = c.post("/api/auth/register", json={"email": email, "password": "Clave-segura-123", "display_name": "X y", "accept_terms": True})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EN_USO"
    r = c.post("/api/auth/register", json={"email": "debil@girando.test", "password": "12345678", "display_name": "X y", "accept_terms": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CONTRASENA_DEBIL"
    r = c.post("/api/auth/register", json={"email": "sin-terminos@girando.test", "password": "Clave-segura-123", "display_name": "X y", "accept_terms": False})
    assert r.status_code == 422


def test_register_records_consents(client):
    email, _ = register(client)
    from app.core.db import unit_of_work
    with unit_of_work("worker") as conn:
        n = conn.execute(text("""SELECT count(*) FROM app.consents c JOIN app.users u ON u.id = c.user_id
                                 WHERE u.email = :e AND c.state = 'granted' AND c.superseded_at IS NULL"""), {"e": email}).scalar()
    assert n == 2  # términos + privacidad con versión


def test_lockout_after_failed_attempts(client):
    email, _ = register(client)
    c = new_client()
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": email, "password": "incorrecta-1"}).status_code == 401
    r = c.post("/api/auth/login", json={"email": email, "password": "Clave-segura-123"})
    assert r.status_code == 423 and r.json()["error"]["code"] == "CUENTA_BLOQUEADA_TEMPORALMENTE"


def test_unknown_email_same_error(client):
    r = client.post("/api/auth/login", json={"email": "nadie@girando.test", "password": "Clave-segura-123"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "CREDENCIALES_INVALIDAS"


def test_refresh_rotates_and_old_refresh_is_invalid(client):
    register(client)
    old = client.cookies.get("gr_rt")
    assert client.post("/api/auth/refresh").status_code == 200
    new = client.cookies.get("gr_rt")
    assert new and new != old
    c2 = new_client()
    c2.cookies.set("gr_rt", old, path="/api/auth")
    assert c2.post("/api/auth/refresh").status_code == 401


def test_csrf_required_on_mutations(client):
    register(client)
    client.headers.pop("X-CSRF-Token")
    r = client.post("/api/auth/logout-others")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_INVALIDO"


def test_password_reset_flow(client):
    email, _ = register(client)
    assert client.post("/api/auth/password/forgot", json={"email": email}).status_code == 202
    assert client.post("/api/auth/password/forgot", json={"email": "no-existe@girando.test"}).status_code == 202
    from app.core.db import unit_of_work
    from app.core.security import sha256
    token = "tok-" + "x" * 40
    with unit_of_work("worker") as conn:
        conn.execute(text("""UPDATE app.auth_tokens SET token_hash = :h WHERE purpose = 'password_reset'
                             AND user_id = (SELECT id FROM app.users WHERE email = :e)"""), {"h": sha256(token), "e": email})
        pend = conn.execute(text("""SELECT status::text, last_error FROM app.email_events WHERE to_email = :e AND event_code = 'password_reset_requested'"""), {"e": email}).first()
    assert pend == ("pending", "provider_not_configured")  # nunca "sent" sin proveedor
    assert client.post("/api/auth/password/reset", json={"token": token, "password": "Nueva-clave-789"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401  # todas las sesiones cerradas
    c = new_client()
    assert c.post("/api/auth/login", json={"email": email, "password": "Nueva-clave-789"}).status_code == 200
    assert c.post("/api/auth/password/reset", json={"token": token, "password": "Otra-clave-000"}).status_code == 400


def test_rate_limit_login(client):
    for i in range(8):
        client.post("/api/auth/login", json={"email": "rl@girando.test", "password": f"x-{i}-abcdef"})
    r = client.post("/api/auth/login", json={"email": "rl@girando.test", "password": "x-9-abcdef"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_suspended_user_loses_access(client):
    email, _ = register(client)
    from app.core.db import unit_of_work
    with unit_of_work("worker") as conn:
        conn.execute(text("UPDATE app.users SET status = 'suspended' WHERE email = :e"), {"e": email})
    r = client.get("/api/auth/me")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CUENTA_SUSPENDIDA"
