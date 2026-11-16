"""Ubicaciones de todo el país: paginado, tope por página y búsqueda por nombre (bloque A)."""
from tests.conftest import geo_id


def test_geo_provinces_complete_and_backward_compatible(client):
    r = client.get("/api/geo?level=province").json()
    assert r["total"] == len(r["items"]) >= 3 and not r["has_more"]
    assert all(i["level"] == "province" for i in r["items"])
    mza = next(p for p in r["items"] if p["name"] == "Mendoza")
    deps = client.get(f"/api/geo?parent_id={mza['id']}").json()
    assert any(d["name"] == "Godoy Cruz" and d["province"] == "Mendoza" and d["province_id"] == mza["id"] for d in deps["items"])


def test_geo_localities_never_unbounded(client):
    r = client.get("/api/geo?level=locality").json()
    assert len(r["items"]) <= 20 and r["limit"] == 20
    assert r["has_more"] == (r["total"] > len(r["items"]))
    big = client.get("/api/geo?level=locality&limit=500").json()
    assert big["limit"] == 50 and len(big["items"]) <= 50          # el tope lo pone el servidor
    page2 = client.get("/api/geo?level=locality&limit=10&offset=10").json()
    first = client.get("/api/geo?level=locality&limit=10").json()
    if first["total"] > 10:
        assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    assert client.get("/api/geo?level=locality&limit=0").status_code == 422
    assert client.get("/api/geo?level=locality&limit=501").status_code == 422


def test_geo_search_by_name_ignores_accents_and_case(client):
    r = client.get("/api/geo", params={"q": "GODOY cr"}).json()
    hit = next(i for i in r["items"] if i["name"] == "Godoy Cruz")
    assert hit["province"] == "Mendoza" and hit["level"] in ("department", "locality")
    r = client.get("/api/geo", params={"q": "maipu", "level": "department"}).json()      # sin tilde encuentra "Maipú"
    assert any(i["name"] == "Maipú" for i in r["items"]) and all(i["level"] == "department" for i in r["items"])
    assert client.get("/api/geo", params={"q": "zzzzqqq"}).json() == {"items": [], "total": 0, "limit": 20, "offset": 0, "has_more": False}
    assert client.get("/api/geo", params={"q": "a"}).status_code == 422                   # mínimo 2 letras
    # comodines de LIKE no se interpretan como patrón del usuario para saltear el tope
    assert len(client.get("/api/geo", params={"q": "%%"}).json()["items"]) <= 20


def test_geo_one_returns_path(client):
    gid = geo_id(client)
    g = client.get(f"/api/geo/{gid}").json()
    assert g["name"] == "Godoy Cruz" and g["province"] == "Mendoza" and g["province_id"]
    assert client.get("/api/geo/00000000-0000-0000-0000-000000000000").status_code == 404
