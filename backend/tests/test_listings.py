from tests.conftest import full_listing_payload, jpeg_bytes, make_staff, new_client, register


def _mod_client():
    c = new_client()
    email, _ = register(c, name="Moderador")
    make_staff(email, "moderator")
    return c


def test_full_listing_lifecycle(client):
    register(client, name="Vendedor")
    # 1. borrador parcial
    r = client.post("/api/me/listings", json={"title": "Borrador"})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert r.json()["status"] == "draft"
    # 2. enviar incompleto → 422 (la base exige catálogo)
    r = client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    assert r.status_code == 422 and r.json()["error"]["code"] in ("VEHICULO_INCOMPLETO", "DATO_INVALIDO")
    # 3. completar y enviar
    r = client.patch(f"/api/me/listings/{lid}", json=full_listing_payload(client))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["brand"] == "Volkswagen" and d["engine"] == "1.6 Nafta"  # motor por defecto de la versión
    r = client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    # 4. no aparece en búsqueda mientras está pendiente
    anon = new_client()
    assert all(i["id"] != lid for i in anon.get("/api/listings").json()["items"])
    # 5. el dueño NO puede aprobarse (no existe transición de usuario a published)
    r = client.post(f"/api/me/listings/{lid}/transition", json={"to": "published"})
    assert r.status_code == 422
    # 6. moderación aprueba
    mod = _mod_client()
    r = mod.post(f"/api/admin/listings/{lid}/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "published"
    # 7. aparece en búsqueda con ubicación pública aproximada
    res = anon.get("/api/listings", params={"q": "gol 2015"}).json()
    mine = next(i for i in res["items"] if i["id"] == lid)
    assert mine["locality"] == "Godoy Cruz" and res["interpretation"]["year"] == 2015
    code = mine["public_code"]
    det = anon.get(f"/api/listings/{code}").json()
    assert det["title"] == "Gol Trend muy cuidado" and det["seller"]["display_name"] == "Vendedor"
    assert det["agency_verified"] is False and det["seller_identity_verified"] is False  # nunca verificado por defecto
    for k in ("owner_user_id", "plate", "vin", "email"):
        assert k not in det
    # 8. notificación al vendedor
    notifs = client.get("/api/me/notifications").json()["items"]
    assert any(n["type_code"] == "listing.approved" for n in notifs)
    # 9. editar precio publicado → sigue publicado + historial de precio
    r = client.patch(f"/api/me/listings/{lid}", json={"price_amount": "9200000"})
    assert r.status_code == 200 and r.json()["status"] == "published"
    # 10. no se puede cambiar la versión estando publicada
    r = client.patch(f"/api/me/listings/{lid}", json={"year": 2016})
    assert r.status_code == 409
    # 11. vender
    r = client.post(f"/api/me/listings/{lid}/sale", json={"sold_on": __import__("datetime").date.today().isoformat(), "final_price": "9000000", "currency": "ARS",
                                                          "channel": "girando", "plate": "AB123CD"})
    assert r.status_code == 201, r.text
    assert r.json()["attributed_to_girando"] is True
    d = client.get(f"/api/me/listings/{lid}").json()
    assert d["status"] == "sold" and d["sale_id"]
    assert anon.get(f"/api/listings/{code}").status_code == 404
    sales = client.get("/api/me/sales").json()
    assert sales["summary"]["count"] == 1 and sales["summary"]["avg_price_ars"] is None  # n < 3: sin promedio
    # 12. publicación vendida no se edita
    assert client.patch(f"/api/me/listings/{lid}", json={"title": "cambio"}).status_code == 409


def test_particular_limit_409(client):
    register(client)
    mod = _mod_client()
    ids = []
    for _ in range(2):
        r = client.post("/api/me/listings", json=full_listing_payload(client))
        ids.append(r.json()["id"])
    assert client.post(f"/api/me/listings/{ids[0]}/transition", json={"to": "pending"}).status_code == 200
    r = client.post(f"/api/me/listings/{ids[1]}/transition", json={"to": "pending"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LIMITE_ALCANZADO"
    # pausar la primera libera el cupo
    mod.post(f"/api/admin/listings/{ids[0]}/approve", json={})
    assert client.post(f"/api/me/listings/{ids[0]}/transition", json={"to": "paused"}).status_code == 200
    assert client.post(f"/api/me/listings/{ids[1]}/transition", json={"to": "pending"}).status_code == 200


def test_moderation_reject_requires_reason_and_notifies(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    mod = _mod_client()
    assert mod.post(f"/api/admin/listings/{lid}/reject", json={}).status_code == 422
    r = mod.post(f"/api/admin/listings/{lid}/reject", json={"reason": "Las fotos no muestran el vehículo"})
    assert r.status_code == 200
    d = client.get(f"/api/me/listings/{lid}").json()
    assert d["status"] == "rejected" and d["status_reason"] == "Las fotos no muestran el vehículo"
    # corregir y reenviar
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200
    r = mod.post(f"/api/admin/listings/{lid}/request_changes", json={"reason": "Agregá el kilometraje real"})
    assert r.json()["status"] == "requires_changes"


def test_images_validation_cover_reorder(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    ids = []
    for i in range(6):
        r = client.post(f"/api/me/listings/{lid}/images", files={"file": (f"f{i}.jpg", jpeg_bytes(color=(i * 30, 50, 90)), "image/jpeg")})
        assert r.status_code == 201, r.text
        ids.append(r.json()["image_id"])
    d = client.get(f"/api/me/listings/{lid}").json()
    assert len(d["images"]) == 6 and sum(1 for i in d["images"] if i["is_cover"]) == 1 and d["images"][0]["is_cover"]
    r = client.post(f"/api/me/listings/{lid}/images", files={"file": ("f7.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MAXIMO_FOTOS"
    # contenido falso con extensión .jpg
    rd = client.delete(f"/api/me/listings/{lid}/images/{ids[5]}")
    assert rd.status_code == 200, rd.text
    r = client.post(f"/api/me/listings/{lid}/images", files={"file": ("virus.jpg", b"MZ" + b"\0" * 500, "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FORMATO_INVALIDO", r.text
    r = client.post(f"/api/me/listings/{lid}/images", files={"file": ("chica.jpg", jpeg_bytes(100, 100), "image/jpeg")})
    assert r.status_code == 422
    # portada y reorden
    r = client.patch(f"/api/me/listings/{lid}/images/{ids[3]}", json={"is_cover": True})
    assert [i["id"] for i in r.json()["images"] if i["is_cover"]] == [ids[3]]
    new_order = list(reversed(ids[:5]))
    r = client.post(f"/api/me/listings/{lid}/images/reorder", json={"image_ids": new_order})
    assert r.status_code == 200 and [i["id"] for i in r.json()["images"]] == new_order


def test_favorites(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    _mod_client().post(f"/api/admin/listings/{lid}/approve", json={})
    buyer = new_client()
    register(buyer, name="Comprador")
    assert buyer.put(f"/api/me/favorites/{lid}").status_code == 201
    favs = buyer.get("/api/me/favorites").json()["items"]
    assert len(favs) == 1 and favs[0]["available"]
    assert client.get(f"/api/me/listings/{lid}").json()["favorites"] == 1  # el vendedor ve el conteo, no quién
    assert buyer.delete(f"/api/me/favorites/{lid}").status_code == 200
    assert buyer.get("/api/me/favorites").json()["items"] == []


def test_facets_and_filters(client):
    register(client)
    lid = client.post("/api/me/listings", json=full_listing_payload(client, currency="USD", price_amount="8000")).json()["id"]
    client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    _mod_client().post(f"/api/admin/listings/{lid}/approve", json={})
    anon = new_client()
    f = anon.get("/api/listings/facets").json()
    assert any(b["label"] == "Volkswagen" for b in f["brand"])
    r = anon.get("/api/listings", params={"price_max": "10000", "currency": "USD"}).json()
    assert any(i["id"] == lid for i in r["items"])
    r = anon.get("/api/listings", params={"verified": "true"}).json()
    assert all(i["id"] != lid for i in r["items"])  # particular sin identidad verificada
    assert anon.get("/api/listings", params={"year_min": "1800"}).status_code == 422
