"""Configuración por variables de entorno (nunca secretos en el código)."""
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "Girando API"
    public_base_url: str = "http://localhost:3000"

    # Base de datos: la API se conecta con un rol SIN privilegios propios (NOINHERIT)
    # y en cada transacción hace SET LOCAL ROLE girando_anon | girando_app | girando_worker.
    database_url: str = "postgresql+psycopg://girando_api:change-me@localhost:5432/girando"
    # Dueño del esquema: solo para migraciones y bootstrap (nunca lo usa la API en runtime).
    database_owner_url: str = "postgresql+psycopg://girando:change-me@localhost:5432/girando"
    db_api_password: str = Field(default="change-me", repr=False)

    redis_url: str | None = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = Field(default="dev-insecure-change-me", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    cookie_secure: bool = False  # True obligatorio en producción (HTTPS)
    cookie_domain: str | None = None
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    # CORS: lista explícita. En producción nunca "*".
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Rate limit (se puede desactivar solo en tests)
    rate_limit_enabled: bool = True

    # Almacenamiento de imágenes
    image_storage: Literal["local_dev", "cloudinary"] = "local_dev"
    media_root: str = "/data/media"
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = Field(default=None, repr=False)

    # Documentos privados (bucket S3-compatible, Cloudflare R2 recomendado)
    documents_bucket: str | None = None
    documents_endpoint_url: str | None = None
    documents_access_key_id: str | None = Field(default=None, repr=False)
    documents_secret_access_key: str | None = Field(default=None, repr=False)

    # Integraciones (sin configurar = NotConfigured, nunca respuestas simuladas)
    mercadopago_access_token: str | None = Field(default=None, repr=False)
    mercadopago_webhook_secret: str | None = Field(default=None, repr=False)
    # Simulador local del proveedor de pagos: SOLO desarrollo/tests y solo si no hay token de Mercado Pago.
    # No aprueba nada solo: permite disparar a mano el aviso que mandaría el proveedor (ver docs/18).
    payments_simulator: bool = False
    email_provider: Literal["none", "resend"] = "none"
    email_api_key: str | None = Field(default=None, repr=False)
    email_from: str = "Girando <no-reply@girando.app>"   # compatibilidad: si no se definen los remitentes de abajo
    # Remitentes separados por propósito (docs/07-email.md):
    #   transaccional (avisos de cuenta, publicaciones, pagos): contacto.avisos@
    #   comunicaciones oficiales de Girando (cambios de términos, avisos importantes): contacto.oficial@
    #   dirección de contacto / reply-to para consultas de personas: contacto@
    #   marketing: separado, solo con consentimiento explícito (vacío = no se envía marketing)
    email_from_transactional: str = "Girando <contacto.avisos@girando.app>"
    email_from_official: str = "Girando <contacto.oficial@girando.app>"
    email_contact_address: str = "contacto@girando.app"
    email_from_marketing: str | None = None
    google_places_api_key: str | None = Field(default=None, repr=False)
    exchange_rate_provider: Literal["none", "bcra"] = "bcra"

    log_level: str = "INFO"
    # Proxies cuya cabecera X-Real-IP se acepta (IP, CIDR o nombre de host). En Docker: "web".
    trusted_proxies: Annotated[list[str], NoDecode] = ["127.0.0.1"]

    @field_validator("cors_origins", "trusted_proxies", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _production_guards(self):
        if self.env == "production":
            problems = []
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS no puede ser * en producción")
            if len(self.jwt_secret) < 32 or "change-me" in self.jwt_secret or "insecure" in self.jwt_secret:
                problems.append("JWT_SECRET débil o por defecto")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE debe ser true en producción")
            if self.image_storage == "local_dev":
                problems.append("IMAGE_STORAGE=local_dev no se permite en producción")
            if self.payments_simulator:
                problems.append("PAYMENTS_SIMULATOR no se permite en producción")
            if "change-me" in self.database_url or "change-me" in self.db_api_password:
                problems.append("Credenciales de base por defecto")
            if problems:
                raise ValueError("; ".join(problems))
        return self

    @property
    def is_dev(self) -> bool:
        return self.env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
