"""Dependencias: contexto de request, usuario actual (desde cookie httpOnly) y permisos.

El backend determina quién es el usuario, su rol de staff, sus agencias y su plan
consultando PostgreSQL. Nada de eso se acepta desde el navegador.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, Request

from app.core.db import RequestContext, row, rows, unit_of_work
from app.core.errors import err
from app.core.logging import user_id_var
from app.core.middleware import client_ip
from app.core.security import decode_access_token

ACCESS_COOKIE = "gr_at"
REFRESH_COOKIE = "gr_rt"


def request_ctx(request: Request) -> RequestContext:
    ip = client_ip(request)
    return RequestContext(request_id=getattr(request.state, "request_id", None), ip=None if ip == "unknown" else ip,
                          user_agent=request.headers.get("user-agent"))


@dataclass
class CurrentUser:
    id: UUID
    session_id: UUID
    email: str
    status: str
    staff_roles: list[str] = field(default_factory=list)
    ctx: RequestContext = field(default_factory=RequestContext)

    @property
    def is_staff(self) -> bool:
        return bool(self.staff_roles)

    def has_role(self, *roles: str) -> bool:
        return "superadmin" in self.staff_roles or any(r in self.staff_roles for r in roles)


def _load_user(request: Request) -> CurrentUser | None:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    claims = decode_access_token(token)
    if not claims:
        return None
    ctx = request_ctx(request)
    uid = claims["sub"]
    with unit_of_work("app", uid, ctx) as conn:
        u = row(conn, """
            SELECT u.id, u.email::text AS email, u.status::text AS status
              FROM app.users u
              JOIN app.sessions s ON s.user_id = u.id AND s.id = :sid AND s.ended_at IS NULL AND s.expires_at > now()
             WHERE u.id = :uid""", {"uid": uid, "sid": claims["sid"]})
        if not u:
            return None
        roles = [r["role"] for r in rows(conn, "SELECT role::text FROM app.staff_roles WHERE user_id = :uid AND revoked_at IS NULL", {"uid": uid})]
    if u["status"] in ("suspended", "blocked", "deleted"):
        raise err(403, "CUENTA_SUSPENDIDA", "Tu cuenta no está habilitada. Escribinos a soporte.")
    user_id_var.set(str(u["id"]))
    return CurrentUser(id=u["id"], session_id=UUID(claims["sid"]), email=u["email"], status=u["status"], staff_roles=roles, ctx=ctx)


def optional_user(request: Request) -> CurrentUser | None:
    return _load_user(request)


def current_user(request: Request) -> CurrentUser:
    u = _load_user(request)
    if not u:
        raise err(401, "NO_AUTENTICADO", "Iniciá sesión para continuar.")
    return u


def staff_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_staff:
        raise err(403, "SOLO_STAFF", "No tenés acceso al panel de administración.")
    return user


def require_roles(*roles: str):
    def dep(user: CurrentUser = Depends(staff_user)) -> CurrentUser:
        if not user.has_role(*roles):
            raise err(403, "ROL_INSUFICIENTE", "Tu rol no permite esta acción.")
        return user
    return dep
