"""Tests de integración contra PostgreSQL real (base efímera girando_test).

Variables: TEST_DATABASE_ADMIN_URL (superusuario, default local :5433). La base se recrea
en cada corrida con las migraciones reales, el bootstrap de roles y seed-base.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "postgresql+psycopg://girando:devowner@127.0.0.1:5433/postgres")
HOST = ADMIN_URL.split("@", 1)[1].rsplit("/", 1)[0]
CREDS = ADMIN_URL.split("://", 1)[1].split("@", 1)[0]
os.environ.update({
    "ENV": "test",
    "DATABASE_OWNER_URL": f"postgresql+psycopg://{CREDS}@{HOST}/girando_test",
    "DATABASE_URL": f"postgresql+psycopg://girando_api:testapi@{HOST}/girando_test",
    "DB_API_PASSWORD": "testapi",
    "REDIS_URL": "",
    "JWT_SECRET": "test-secret-0123456789-0123456789-abcdef",
    "MEDIA_ROOT": "/tmp/girando-test-media",
    "RATE_LIMIT_ENABLED": "true",
    "IMAGE_STORAGE": "local_dev",
    # Fijo para los tests: en Docker el .env trae el origen del entorno local (3100) y pisaba el valor por defecto
    "CORS_ORIGINS": "http://localhost:3000",
})

from sqlalchemy import create_engine, text  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    get_settings.cache_clear()
    eng = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'girando_test' AND pid <> pg_backend_pid()"))
        c.execute(text("DROP DATABASE IF EXISTS girando_test"))
        c.execute(text("CREATE DATABASE girando_test"))
    eng.dispose()
    from types import SimpleNamespace

    from app import cli
    cli.cmd_migrate(SimpleNamespace())
    cli.cmd_bootstrap_db(SimpleNamespace())
    cli.cmd_seed_base(SimpleNamespace())
    yield
    from app.core.db import reset_engine
    reset_engine()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    ratelimit.reset_memory()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app
    c = TestClient(create_app(), base_url="http://testserver")
    csrf(c)
    return c


def csrf(c):
    tok = c.get("/api/auth/csrf").json()["csrf_token"]
    c.headers["X-CSRF-Token"] = tok
    return tok


def new_client():
    from fastapi.testclient import TestClient

    from app.main import create_app
    c = TestClient(create_app(), base_url="http://testserver")
    csrf(c)
    return c


TEST_WHATSAPP = "+5492615550101"


def register(c, email=None, password="Clave-segura-123", name="Tester"):
    email = email or f"u{uuid.uuid4().hex[:10]}@girando.test"
    # Los tests largos registran más de 5 usuarios desde la misma IP: el límite de registro (5/hora por IP)
    # se reinicia acá. Solo ese bucket; los demás límites siguen contando dentro del test.
    ratelimit.reset_memory(ratelimit.REGISTER_IP.bucket)
    r = c.post("/api/auth/register", json={"email": email, "password": password, "display_name": name, "accept_terms": True})
    assert r.status_code == 201, r.text
    # WhatsApp es obligatorio para publicar (CONTEXTO §2): los tests parten de un perfil que ya lo tiene cargado.
    assert c.patch("/api/me/profile", json={"contact_whatsapp_e164": TEST_WHATSAPP}).status_code == 200
    return email, r.json()["user"]


def make_staff(email: str, role: str):
    from app.core.db import unit_of_work
    with unit_of_work("worker") as conn:
        conn.execute(text("INSERT INTO app.staff_roles (user_id, role) SELECT id, CAST(:r AS app.staff_role) FROM app.users WHERE email = :e"),
                     {"r": role, "e": email})


def catalog_ids(c):
    brands = c.get("/api/catalog/brands").json()["items"]
    vw = next(b for b in brands if b["name"] == "Volkswagen")
    gol = next(m for m in c.get(f"/api/catalog/brands/{vw['id']}/models").json()["items"] if m["name"] == "Gol Trend")
    gen = c.get(f"/api/catalog/models/{gol['id']}/generations").json()["items"][0]
    ver = c.get(f"/api/catalog/generations/{gen['id']}/versions").json()["items"][0]
    return {"brand_id": vw["id"], "model_id": gol["id"], "generation_id": gen["id"], "version_id": ver["id"]}


def geo_id(c, name="Godoy Cruz"):
    provs = c.get("/api/geo?level=province").json()["items"]
    mza = next(p for p in provs if p["name"] == "Mendoza")
    return next(d for d in c.get(f"/api/geo?parent_id={mza['id']}").json()["items"] if d["name"] == name)["id"]


def full_listing_payload(c, **over):
    ids = catalog_ids(c)
    p = {"version_id": ids["version_id"], "year": 2015, "km": 98000, "price_amount": "9500000", "currency": "ARS",
         "geo_area_id": geo_id(c), "title": "Gol Trend muy cuidado", "description": "Service al día."}
    p.update(over)
    return p


def jpeg_bytes(w=800, h=600, color=(20, 90, 200)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


def make_cuit(prefix: str = "30") -> str:
    """CUIT válido (dígito verificador correcto) y distinto en cada llamada."""
    import random
    body = prefix + "".join(str(random.randint(0, 9)) for _ in range(8))  # noqa: S311
    w = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    r = 11 - sum(int(c) * k for c, k in zip(body, w, strict=True)) % 11
    dv = 0 if r == 11 else (9 if r == 10 else r)
    return f"{body[:2]}-{body[2:]}-{dv}"


def make_agency(c, name="Autos Fase 3", **extra):
    geo = c.get("/api/geo?level=province").json()["items"]
    mza = next(p for p in geo if p["name"] == "Mendoza")["id"]
    gc = next(d for d in c.get(f"/api/geo?parent_id={mza}").json()["items"] if d["name"] == "Godoy Cruz")["id"]
    r = c.post("/api/me/agencies", json={"legal_name": f"{name} SRL", "trade_name": name, "cuit": make_cuit(), "geo_area_id": gc,
                                         "whatsapp_e164": TEST_WHATSAPP, **extra})
    assert r.status_code == 201, r.text
    return r.json()
