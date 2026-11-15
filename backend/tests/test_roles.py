"""Matriz de roles probada por API directa (sin depender de lo que muestra el panel).

Super Admin: todo. Admin: operación (usuarios, agencias, publicaciones, moderación, reportes, verificaciones, catálogo).
Moderador: moderar publicaciones, reportes y revisar verificaciones; nada comercial ni de usuarios.
Particular y agencia: solo sus recursos; ningún endpoint del panel.
"""
import pytest

from tests.conftest import full_listing_payload, make_agency, make_staff, new_client, register


def _staff(role: str):
    c = new_client()
    email, _ = register(c, name=f"Staff {role}")
    make_staff(email, role)
    return c


# endpoints de solo lectura del panel → quién entra (200) y quién no (403)
OPS = ["/api/admin/dashboard", "/api/admin/listings", "/api/admin/reports", "/api/admin/verifications", "/api/admin/agencies"]
USERS = ["/api/admin/users"]
COMMERCIAL = ["/api/admin/plans", "/api/admin/subscriptions", "/api/admin/payments", "/api/admin/sales-stats", "/api/admin/business",
              "/api/admin/finance/summary", "/api/admin/promotions", "/api/admin/home-blocks", "/api/admin/emails", "/api/admin/audit",
              "/api/admin/retention", "/api/admin/media-queue", "/api/integrations/status"]

MATRIX = {
    "superadmin": {"ops": 200, "users": 200, "commercial": 200},
    "admin": {"ops": 200, "users": 200, "commercial": 403},
    "moderator": {"ops": 200, "users": 403, "commercial": 403},
}


@pytest.mark.parametrize("role", list(MATRIX))
def test_staff_matrix(role):
    c = _staff(role)
    exp = MATRIX[role]
    for group, paths in (("ops", OPS), ("users", USERS), ("commercial", COMMERCIAL)):
        for p in paths:
            assert c.get(p).status_code == exp[group], f"{role} {p}"


def test_non_staff_cannot_reach_any_admin_endpoint(client):
    register(client)
    for p in OPS + USERS + COMMERCIAL:
        assert client.get(p).status_code in (401, 403), p
    anon = new_client()
    for p in OPS + COMMERCIAL:
        assert anon.get(p).status_code in (401, 403), p


def test_admin_cannot_change_commercial_config(client):
    adm, sup = _staff("admin"), _staff("superadmin")
    plans = sup.get("/api/admin/plans").json()["items"]
    p30 = next(p for p in plans if p["code"] == "agencia-30")
    # Admin: ni planes, ni promociones, ni Home, ni roles
    assert adm.patch(f"/api/admin/plans/{p30['id']}", json={"max_active_listings": 999}).status_code == 403
    assert adm.post("/api/admin/home-blocks", json={"kind": "announcement", "title": "Hola"}).status_code == 403
    assert adm.post("/api/admin/promotions", json={"type": "banner_campaign", "placement": "home_banner", "advertiser_name": "X",
                                                     "link_url": "https://x.com", "starts_at": "2026-01-01T00:00:00Z",
                                                     "ends_at": "2030-01-01T00:00:00Z"}).status_code == 403
    _, u = register(new_client())
    assert adm.post(f"/api/admin/users/{u['id']}/roles", json={"role": "admin"}).status_code == 403
    # Super Admin sí, y el valor sale de PostgreSQL (lo lee la App)
    assert sup.patch(f"/api/admin/plans/{p30['id']}", json={"max_active_listings": 31}).status_code == 200
    pub = next(p for p in new_client().get("/api/plans").json()["items"] if p["code"] == "agencia-30")
    assert pub["max_active_listings"] == 31
    assert sup.patch(f"/api/admin/plans/{p30['id']}", json={"max_active_listings": 30}).status_code == 200


def test_moderator_moderates_but_no_users_or_commerce(client):
    mod = _staff("moderator")
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200
    assert mod.post(f"/api/admin/listings/{lid}/approve", json={}).status_code == 200
    _, u = register(new_client())
    assert mod.post(f"/api/admin/users/{u['id']}/suspend", json={"reason": "probando permisos"}).status_code == 403


def test_particular_and_agency_only_see_their_resources(client):
    # Particular A con publicación; B no la puede ver ni editar por API directa
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    other = new_client()
    register(other)
    assert other.get(f"/api/me/listings/{lid}").status_code in (403, 404)
    assert other.patch(f"/api/me/listings/{lid}", json={"title": "Me la apropio"}).status_code in (403, 404)
    # Agencia: otro usuario no ve ni edita su perfil, estadísticas ni facturación
    owner = new_client()
    register(owner)
    ag = make_agency(owner, "Roles Autos")
    for path in (f"/api/me/agencies/{ag['id']}", f"/api/me/agencies/{ag['id']}/stats", f"/api/me/agencies/{ag['id']}/billing"):
        assert other.get(path).status_code in (403, 404), path
        assert owner.get(path).status_code == 200, path
    assert other.patch(f"/api/me/agencies/{ag['id']}", json={"website_url": "https://phishing.example"}).status_code == 403
    assert other.post(f"/api/me/agencies/{ag['id']}/verification").status_code in (403, 404)
