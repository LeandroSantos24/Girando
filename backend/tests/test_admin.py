from sqlalchemy import text

from tests.conftest import full_listing_payload, make_staff, new_client, register


def _staff(role: str):
    c = new_client()
    email, _ = register(c, name=f"Staff {role}")
    make_staff(email, role)
    return c


def test_catalog_admin_reflects_in_app():
    admin = _staff("catalog_editor")
    r = admin.post("/api/admin/catalog/brands", json={"name": "Renault"})
    assert r.status_code == 201
    bid = r.json()["id"]
    mid = admin.post("/api/admin/catalog/models", json={"brand_id": bid, "name": "Kangoo", "vehicle_type": "van", "default_body_type": "van"}).json()["id"]
    gid = admin.post("/api/admin/catalog/generations", json={"model_id": mid, "name": "Segunda generación", "year_from": 2008, "year_to": 2018}).json()["id"]
    eid = admin.post("/api/admin/catalog/engines", json={"name": "1.6 Nafta 16v", "fuel": "gasoline"}).json()["id"]
    vid = admin.post("/api/admin/catalog/versions", json={"generation_id": gid, "name": "Express 1.6", "transmission": "manual",
                                                          "traction": "front", "engine_ids": [eid]}).json()["id"]
    app = new_client()
    assert any(b["name"] == "Renault" for b in app.get("/api/catalog/brands").json()["items"])
    vers = app.get(f"/api/catalog/generations/{gid}/versions").json()["items"]
    assert vers[0]["id"] == vid and vers[0]["engines"][0]["name"] == "1.6 Nafta 16v"
    # desactivar → desaparece de la App, no se borra
    assert admin.patch(f"/api/admin/catalog/versions/{vid}", json={"status": "inactive"}).status_code == 200
    assert app.get(f"/api/catalog/generations/{gid}/versions").json()["items"] == []
    assert admin.get(f"/api/admin/catalog/versions?parent_id={gid}").json()["items"][0]["status"] == "inactive"
    # moderador no puede editar catálogo
    assert _staff("moderator").post("/api/admin/catalog/brands", json={"name": "X"}).status_code == 403


def test_agency_verification_flow(client):
    register(client, name="Dueño")
    geo = client.get("/api/geo?level=province").json()["items"]
    mza = next(p for p in geo if p["name"] == "Mendoza")["id"]
    gc = next(d for d in client.get(f"/api/geo?parent_id={mza}").json()["items"] if d["name"] == "Godoy Cruz")["id"]
    r = client.post("/api/me/agencies", json={"legal_name": "Autos Test SRL", "trade_name": "Autos Test", "cuit": "30-50001091-2", "geo_area_id": gc})
    assert r.status_code == 201, r.text
    ag = r.json()
    assert ag["status"] == "pending"
    anon = new_client()
    assert anon.get(f"/api/agencies/{ag['slug']}").json()["is_verified"] is False
    mod = _staff("moderator")
    r = mod.post(f"/api/admin/agencies/{ag['id']}/verify", json={})
    assert r.status_code == 409  # sin solicitud no se verifica
    assert client.post(f"/api/me/agencies/{ag['id']}/verification").status_code == 201
    r = mod.post(f"/api/admin/agencies/{ag['id']}/verify", json={})
    assert r.status_code == 200 and r.json()["status"] == "verified"
    assert anon.get(f"/api/agencies/{ag['slug']}").json()["is_verified"] is True
    # suspender es del Admin (no del moderador) y oculta la agencia y sus publicaciones
    assert mod.post(f"/api/admin/agencies/{ag['id']}/suspend", json={"reason": "Documentación adulterada"}).status_code == 403
    adm = _staff("admin")
    assert adm.post(f"/api/admin/agencies/{ag['id']}/suspend", json={"reason": "Documentación adulterada"}).status_code == 200
    assert anon.get(f"/api/agencies/{ag['slug']}").status_code == 404
    assert adm.post(f"/api/admin/agencies/{ag['id']}/reactivate", json={}).json()["status"] == "verified"


def test_user_suspension_by_admin_and_audit(client):
    email, user = register(client)
    admin = _staff("admin")
    assert admin.post(f"/api/admin/users/{user['id']}/suspend", json={}).status_code == 422
    assert admin.post(f"/api/admin/users/{user['id']}/suspend", json={"reason": "Publicaciones fraudulentas"}).status_code == 200
    assert client.get("/api/auth/me").status_code in (401, 403)
    assert admin.get("/api/admin/audit").status_code == 403   # la auditoría la consulta el Super Admin
    audit = _staff("superadmin").get("/api/admin/audit", params={"entity_type": "users"}).json()["items"]
    entry = next(a for a in audit if a["entity_id"] == user["id"] and (a["after_data"] or {}).get("status") == "suspended")
    assert entry["reason"] == "Publicaciones fraudulentas" and entry["actor_role"] == "admin"
    from app.core.db import unit_of_work
    try:
        with unit_of_work("worker") as conn:
            conn.execute(text("UPDATE app.audit_logs SET reason = 'x'"))
        raise AssertionError("auditoría modificable")
    except Exception as e:  # noqa: BLE001
        assert "append-only" in str(e)


def test_dashboard_is_real(client):
    admin = _staff("admin")
    before = admin.get("/api/admin/dashboard").json()
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    after = admin.get("/api/admin/dashboard").json()
    assert after["listings"].get("pending", 0) == before["listings"].get("pending", 0) + 1
    assert any(q["id"] == lid for q in after["moderation_queue"])


def test_dashboard_and_stats_are_real_and_empty_safe(client):
    admin = _staff("admin")
    d = admin.get("/api/admin/dashboard").json()
    assert len(d["weekly_published"]) == 8 and all(int(w["n"]) >= 0 for w in d["weekly_published"])
    s = _staff("superadmin").get("/api/admin/sales-stats?days=30").json()
    # con menos de 3 ventas no hay promedio: nunca se inventa un número
    assert s["min_sample"] == 3 and (s["kpis"]["sold"] >= 3 or s["kpis"]["avg_ars"] is None)
    # lo comercial y la auditoría son del Super Admin: el Admin de operación recibe 403
    for path in ("/api/admin/media-queue", "/api/admin/emails", "/api/admin/subscriptions", "/api/admin/payments", "/api/admin/audit"):
        assert admin.get(path).status_code == 403, path
    sup = _staff("superadmin")
    for path in ("/api/admin/media-queue", "/api/admin/emails", "/api/admin/subscriptions", "/api/admin/payments", "/api/admin/audit"):
        assert sup.get(path).status_code == 200, path
    # un usuario común no ve nada del panel
    register(client)
    for path in ("/api/admin/dashboard", "/api/admin/sales-stats", "/api/admin/emails", "/api/admin/users"):
        assert client.get(path).status_code == 403, path


def test_search_understands_multiword_models(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client, title="Impecable")).json()["id"]
    client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    _staff("moderator").post(f"/api/admin/listings/{lid}/approve", json={})
    anon = new_client()
    r = anon.get("/api/listings", params={"q": "gol 2015"}).json()
    assert any(i["id"] == lid for i in r["items"]) and r["interpretation"]["model"] == "Gol Trend"
    r = anon.get("/api/listings", params={"q": "volkswagen gol trend"}).json()
    assert any(i["id"] == lid for i in r["items"]) and r["interpretation"]["brand"] == "Volkswagen"
