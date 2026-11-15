"""Girando API."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.api.deps import require_roles
from app.api.routers import admin, auth, billing, business, marketplace, me, messaging, payments, public, verticals
from app.core import middleware
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import (
    AppError,
    app_error_handler,
    db_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    s = get_settings()
    setup_logging(s.log_level)
    app = FastAPI(title="Girando API", version="0.1.0",
                  description="API de Girando. Única fuente de verdad para la App y el Admin.",
                  docs_url="/docs", redoc_url=None, openapi_url="/openapi.json")

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DBAPIError, db_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    middleware.install(app)
    # CORS con orígenes explícitos (la App se sirve en el mismo origen vía nginx; CORS aplica a otros clientes)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "X-Client-Platform"], max_age=600)

    # business antes que admin: sus rutas específicas (/agencies/{id}/plan) no deben caer en /agencies/{id}/{action}
    # fase 4 antes que public/admin: /listings/{code}/financing y /admin/posts/... no deben caer en rutas genéricas
    for r in (auth.router, marketplace.router, verticals.router, messaging.router, payments.router,
              public.router, me.router, billing.router, business.router, admin.router):
        app.include_router(r)

    @app.get("/api/health", tags=["sistema"])
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "env": s.env}

    @app.get("/api/integrations/status", tags=["sistema"])
    def integrations_status(_user=Depends(require_roles("superadmin"))):
        """Estado real de las integraciones (sin secretos). Solo Super Admin."""
        return {
            "images": s.image_storage if s.image_storage == "local_dev" else ("cloudinary" if s.cloudinary_api_secret else "cloudinary_not_configured"),
            "mercadopago": "configured" if s.mercadopago_access_token else ("simulator" if s.payments_simulator else "not_configured"),
            "email": s.email_provider if s.email_api_key else "not_configured",
            "google_places": "configured" if s.google_places_api_key else "not_configured",
            "documents_bucket": "configured" if s.documents_bucket else "not_configured",
            "exchange_rate": s.exchange_rate_provider,
            "email_senders": {"transactional": s.email_from_transactional, "official": s.email_from_official, "contact": s.email_contact_address,
                              "marketing": s.email_from_marketing or "not_configured"},
        }

    if s.image_storage == "local_dev" and s.env != "production":
        root = Path(s.media_root)
        root.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=root), name="media-dev")
    return app


app = create_app()
