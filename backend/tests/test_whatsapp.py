"""Contacto por WhatsApp (CONTEXTO §2 y §5): obligatorio para publicar, redirect sin exponer el número,
sin login, con límite por IP y filtro de bots, sin guardar quién hizo clic; aperturas en el resumen diario;
aviso de baja de precio en favoritos y precio vs mercado solo con muestra."""
from urllib.parse import unquote

from sqlalchemy import text

from app import cli
from app.core.db import unit_of_work
from tests.conftest import TEST_WHATSAPP, full_listing_payload, new_client, register
from tests.test_fase4 import TAXI, _post, _publish_post, _published_listing, _staff, _user

BROWSER = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36"}
DIGITS = TEST_WHATSAPP.lstrip("+")


def _aggregate():
    with unit_of_work("worker") as conn:
        cli.job_aggregate_stats(conn)


def test_listing_needs_whatsapp_to_be_submitted(client):
    register(client)
    assert client.patch("/api/me/profile", json={"contact_whatsapp_e164": None}).status_code == 200      # perfil sin WhatsApp
    lid = client.post("/api/me/listings", json=full_listing_payload(client)).json()["id"]
    r = client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WHATSAPP_OBLIGATORIO", r.text
    assert client.patch(f"/api/me/listings/{lid}/contact", json={"whatsapp_e164": "2615550101"}).status_code == 422   # formato internacional
    assert client.patch(f"/api/me/listings/{lid}/contact", json={"whatsapp_e164": TEST_WHATSAPP}).status_code == 200
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "pending"}).status_code == 200


def test_whatsapp_redirect_without_login_and_number_never_in_api(client):
    register(client)
    lid, code = _published_listing(client)
    anon = new_client()
    detail = anon.get(f"/api/listings/{code}")
    assert detail.status_code == 200 and detail.json()["whatsapp_url"] == f"/api/out/wa/{code}"
    for body in (detail.text, anon.get("/api/listings").text, anon.get(f"/api/listings/{code}/similar").text):
        assert DIGITS not in body and "wa.me" not in body                       # el número no viaja en ninguna respuesta pública
    r = anon.get(f"/api/out/wa/{code}", headers=BROWSER, follow_redirects=False)   # sin sesión
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith(f"https://wa.me/{DIGITS}?text=")
    assert unquote(loc.split("?text=", 1)[1]) == f"Hola, vi tu Volkswagen Gol Trend 2015 en Girando ({code})"
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] in ("no-referrer", "strict-origin-when-cross-origin")
    # no se guarda quién hizo clic: ni usuario, ni id anónimo, ni sesión; tampoco con sesión iniciada
    other = _user("Compradora")
    assert other.get(f"/api/out/wa/{code}", headers=BROWSER, follow_redirects=False).status_code == 302
    with unit_of_work("worker") as conn:
        ev = conn.execute(text("""SELECT user_id, anonymous_id, session_id, properties FROM app.analytics_events
                                   WHERE event_name = 'listing_contact' AND listing_id = :l"""), {"l": lid}).mappings().all()
        assert len(ev) == 2 and all(e["user_id"] is None and e["anonymous_id"] is None and e["session_id"] is None for e in ev)
        assert all(e["properties"] == {"channel": "whatsapp"} for e in ev)
        assert conn.execute(text("SELECT count(*) FROM app.audit_logs WHERE ip IS NOT NULL AND entity_id = :l AND action = 'whatsapp'"), {"l": lid}).scalar() == 0
    # las aperturas llegan al dueño por el resumen diario
    _aggregate()
    mine = next(i for i in client.get("/api/me/listings", params={"group": "todas"}).json()["items"] if i["id"] == lid)
    assert mine["stats"]["whatsapp_opens"] == 2
    # código con formato inválido o inexistente
    assert anon.get("/api/out/wa/P-NOEXISTE", headers=BROWSER, follow_redirects=False).status_code == 404
    assert anon.get("/api/out/wa/https:evil.example", headers=BROWSER, follow_redirects=False).status_code in (404, 422)
    # pausada: deja de entregar el número
    assert client.post(f"/api/me/listings/{lid}/transition", json={"to": "paused"}).status_code == 200
    assert anon.get(f"/api/out/wa/{code}", headers=BROWSER, follow_redirects=False).status_code == 404


def test_whatsapp_redirect_blocks_bots_and_rate_limits(client):
    register(client)
    lid, code = _published_listing(client)
    anon = new_client()
    for ua in ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "WhatsApp/2.23.20 A", "curl/8.5.0",
               "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "python-requests/2.32", ""):
        r = anon.get(f"/api/out/wa/{code}", headers={"User-Agent": ua}, follow_redirects=False)
        assert r.status_code == 403 and "location" not in r.headers, ua
    with unit_of_work("worker") as conn:      # un bot no cuenta como apertura
        assert conn.execute(text("SELECT count(*) FROM app.analytics_events WHERE event_name = 'listing_contact' AND listing_id = :l"), {"l": lid}).scalar() == 0
    codes = [anon.get(f"/api/out/wa/{code}", headers=BROWSER, follow_redirects=False).status_code for _ in range(31)]
    assert codes[:24] == [302] * 24 and codes[-1] == 429      # 30 cada 10 minutos por IP (los 6 intentos de bots también contaron)


def test_post_needs_whatsapp_and_redirect_counts_opens(client):
    register(client)
    assert client.patch("/api/me/profile", json={"contact_whatsapp_e164": None}).status_code == 200
    r = _post(client, "taxi", TAXI, price_amount="30000000")
    assert r.status_code == 201 and r.json()["has_whatsapp"] is False, r.text
    pid = r.json()["id"]
    r = client.post(f"/api/me/posts/{pid}/transition", json={"to": "pending"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WHATSAPP_OBLIGATORIO", r.text
    assert client.patch(f"/api/me/posts/{pid}", json={"contact_whatsapp_e164": "+5492615550999"}).json()["has_whatsapp"] is True
    code = _publish_post(client, pid)
    anon = new_client()
    d = anon.get(f"/api/posts/{code}")
    assert d.json()["whatsapp_url"] == f"/api/out/wa/{code}" and "5492615550999" not in d.text and "contact_whatsapp" not in d.text
    assert "5492615550999" not in anon.get("/api/posts", params={"vertical": "taxi"}).text
    r = anon.get(f"/api/out/wa/{code}", headers=BROWSER, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://wa.me/5492615550999?text=")
    assert unquote(r.headers["location"].split("?text=", 1)[1]) == f"Hola, vi tu Publicación de taxi en Girando ({code})"
    _aggregate()
    mine = next(i for i in client.get("/api/me/posts").json()["items"] if i["id"] == pid)
    assert mine["stats"] == {"views": 1, "whatsapp_opens": 1}
    # otro usuario no ve las estadísticas ni el WhatsApp privado de la publicación
    assert all(i["id"] != pid for i in _user("Otro").get("/api/me/posts").json()["items"])


def test_favorite_price_drop_is_reported(client):
    register(client)
    lid, _ = _published_listing(client)
    buyer = _user("Compradora")
    assert buyer.put(f"/api/me/favorites/{lid}").status_code == 201
    fav = buyer.get("/api/me/favorites").json()["items"][0]
    assert float(fav["price_at_save"]) == 9500000 and fav["price_dropped"] is False and fav["price_drop_amount"] is None
    assert client.patch(f"/api/me/listings/{lid}", json={"price_amount": "9000000"}).status_code == 200
    fav = buyer.get("/api/me/favorites").json()["items"][0]
    assert fav["price_dropped"] is True and float(fav["price_drop_amount"]) == 500000 and float(fav["price_amount"]) == 9000000
    assert any(n["type_code"] == "favorite.price_drop" for n in buyer.get("/api/me/notifications").json()["items"])
    # una suba no es una baja
    assert client.patch(f"/api/me/listings/{lid}", json={"price_amount": "9900000"}).status_code == 200
    assert buyer.get("/api/me/favorites").json()["items"][0]["price_dropped"] is False


def test_market_price_only_with_enough_sample(client):
    register(client)
    _, code = _published_listing(client, price_amount="8500000", year=2012)      # año que no usa ningún otro test
    anon = new_client()
    m = anon.get(f"/api/listings/{code}/market").json()
    assert m["sufficient"] is False and m["message"] == "Sin datos suficientes" and "avg_price_ars" not in m and "position" not in m
    assert anon.get("/api/listings/P-NOEXISTE/market").status_code == 404
    _staff("moderator")     # deja registrado un moderador para las aprobaciones de abajo
    for _ in range(5):
        _published_listing(_user("Vendedor"), price_amount="10000000", year=2012)
    m = anon.get(f"/api/listings/{code}/market").json()
    assert m["sufficient"] is True and m["sample"] >= 5 and m["position"] in ("below", "in_market", "above")
    assert float(m["price_ars"]) == 8500000 and m["basis"]
