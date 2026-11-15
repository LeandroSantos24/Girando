"""DTOs compartidos. Validación estricta: todo lo que entra se valida en el backend."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

# Las cuentas de desarrollo/test usan el TLD reservado .test (RFC 2606), claramente ficticio.
# email-validator lo rechaza por defecto; se habilita SOLO fuera de producción.
try:
    import email_validator as _ev

    from app.core.config import get_settings as _gs
    if _gs().env != "production" and "test" in _ev.SPECIAL_USE_DOMAIN_NAMES:
        _ev.SPECIAL_USE_DOMAIN_NAMES.remove("test")
except Exception:  # noqa: BLE001
    pass

CLEAN_TEXT_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def clean_text(v: str | None) -> str | None:
    """Quita caracteres de control. El HTML NO se elimina acá: se guarda el texto tal cual y
    el frontend lo renderiza siempre como texto (React escapa por defecto; nunca innerHTML)."""
    if v is None:
        return None
    return CLEAN_TEXT_RE.sub("", v).strip()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Email = Annotated[EmailStr, StringConstraints(max_length=254)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Currency = Literal["ARS", "USD"]
PhoneE164 = Annotated[str, StringConstraints(pattern=r"^\+[1-9][0-9]{7,14}$")]


class RegisterIn(StrictModel):
    email: Email
    password: Password
    display_name: Annotated[str, StringConstraints(min_length=2, max_length=60)]
    accept_terms: Literal[True]

    _clean = field_validator("display_name")(lambda cls, v: clean_text(v))


class LoginIn(StrictModel):
    email: Email
    password: Password


class EmailIn(StrictModel):
    email: Email


class TokenIn(StrictModel):
    token: Annotated[str, StringConstraints(min_length=20, max_length=200)]


class ResetIn(TokenIn):
    password: Password


class ChangePasswordIn(StrictModel):
    current_password: Password
    new_password: Password


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class ReasonIn(StrictModel):
    reason: Annotated[str, StringConstraints(min_length=3, max_length=500)] | None = None

    _clean = field_validator("reason")(lambda cls, v: clean_text(v))


__all__ = ["UUID", "Decimal", "date", "Field"]
