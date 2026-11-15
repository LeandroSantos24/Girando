"""Contraseñas (Argon2id), tokens de acceso (JWT corto), refresh opaco, CSRF."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()  # Argon2id, parámetros por defecto de argon2-cffi (RFC 9106 low-memory)
_DUMMY_HASH = _ph.hash("girando-dummy-password-for-timing")

COMMON_PASSWORDS = {
    "12345678", "123456789", "1234567890", "password", "password1", "qwerty123", "11111111", "00000000",
    "contraseña", "contrasena", "girando123", "iloveyou", "argentina", "mendoza123", "abc12345", "asdfghjk",
}


def validate_password_strength(pw: str) -> str | None:
    if len(pw) < 8:
        return "La contraseña tiene que tener al menos 8 caracteres."
    if len(pw) > 128:
        return "La contraseña es demasiado larga."
    if pw.lower() in COMMON_PASSWORDS:
        return "Esa contraseña es demasiado común."
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", pw) or not re.search(r"\d", pw):
        return "Usá letras y números."
    return None


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, pw) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def create_access_token(user_id: UUID, session_id: UUID) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.access_token_minutes)
    token = jwt.encode({"sub": str(user_id), "sid": str(session_id), "iat": now, "exp": exp, "typ": "access"},
                       s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, exp


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub", "sid"]})
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == "access" else None


def csrf_valid(cookie_value: str | None, header_value: str | None) -> bool:
    return bool(cookie_value) and bool(header_value) and hmac.compare_digest(cookie_value, header_value)
