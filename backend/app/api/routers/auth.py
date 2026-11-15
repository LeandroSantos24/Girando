"""/api/auth — sesión con cookies httpOnly (access corto + refresh rotativo) y CSRF double-submit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import ACCESS_COOKIE, REFRESH_COOKIE, CurrentUser, current_user, request_ctx
from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import rows, unit_of_work
from app.core.errors import err
from app.core.middleware import CSRF_COOKIE, client_ip
from app.core.security import random_token
from app.schemas.common import ChangePasswordIn, EmailIn, LoginIn, RegisterIn, ResetIn, TokenIn
from app.services import auth_service
from app.services.account_service import me_summary

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookies(response: Response, sess: dict) -> None:
    s = get_settings()
    common = {"httponly": True, "secure": s.cookie_secure, "domain": s.cookie_domain}
    response.set_cookie(ACCESS_COOKIE, sess["access"], max_age=s.access_token_minutes * 60, samesite="lax", path="/", **common)
    response.set_cookie(REFRESH_COOKIE, sess["refresh"], max_age=s.refresh_token_days * 86400, samesite="strict", path="/api/auth", **common)


def _clear_session_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=s.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", domain=s.cookie_domain)


@router.get("/csrf", summary="Obtiene/renueva el token CSRF (cookie legible + valor en el cuerpo)")
def csrf(request: Request, response: Response):
    s = get_settings()
    token = request.cookies.get(CSRF_COOKIE) or random_token(24)
    response.set_cookie(CSRF_COOKIE, token, max_age=7 * 86400, samesite="lax", secure=s.cookie_secure, httponly=False, path="/", domain=s.cookie_domain)
    return {"csrf_token": token}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response):
    ctx = request_ctx(request)
    ratelimit.hit(ratelimit.REGISTER_IP, client_ip(request))
    auth_service.register(ctx, body.email, body.password, body.display_name, request.headers.get("x-client-platform", "web"))
    sess = auth_service.login(ctx, body.email, body.password, request.headers.get("x-client-platform", "web"))
    _set_session_cookies(response, sess)
    with unit_of_work("app", sess["user_id"], ctx) as conn:
        return {"user": me_summary(conn, sess["user_id"])}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    ctx = request_ctx(request)
    ratelimit.hit(ratelimit.LOGIN_IP, client_ip(request))
    ratelimit.hit(ratelimit.LOGIN_EMAIL, body.email.lower())
    sess = auth_service.login(ctx, body.email, body.password, request.headers.get("x-client-platform", "web"))
    _set_session_cookies(response, sess)
    with unit_of_work("app", sess["user_id"], ctx) as conn:
        return {"user": me_summary(conn, sess["user_id"])}


@router.post("/refresh")
def refresh(request: Request, response: Response):
    ratelimit.hit(ratelimit.REFRESH_IP, client_ip(request))
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise err(401, "SESION_EXPIRADA", "Tu sesión expiró. Volvé a ingresar.")
    try:
        sess = auth_service.refresh(request_ctx(request), token)
    except Exception:
        _clear_session_cookies(response)
        raise
    _set_session_cookies(response, sess)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    try:
        user = current_user(request)
        auth_service.end_session(user.ctx, user.id, user.session_id, "logout")
    except Exception:  # noqa: BLE001 - logout siempre limpia cookies
        pass
    _clear_session_cookies(response)
    return {"ok": True}


@router.post("/logout-others")
def logout_others(user: CurrentUser = Depends(current_user)):
    return {"closed": auth_service.end_other_sessions(user.ctx, user.id, user.session_id)}


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        return {"user": me_summary(conn, user.id)}


@router.get("/sessions")
def sessions(user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        items = rows(conn, """SELECT id, device_label, platform::text AS platform, host(ip) AS ip, created_at, last_seen_at
                                FROM app.sessions WHERE user_id = :u AND ended_at IS NULL AND expires_at > now()
                               ORDER BY last_seen_at DESC""", {"u": user.id})
    for i in items:
        i["current"] = i["id"] == user.session_id
    return {"items": items}


@router.delete("/sessions/{session_id}")
def close_session(session_id: str, user: CurrentUser = Depends(current_user)):
    auth_service.end_session(user.ctx, user.id, session_id, "logout")
    return {"ok": True}


@router.post("/password/forgot", status_code=202)
def forgot(body: EmailIn, request: Request):
    ratelimit.hit(ratelimit.PASSWORD_IP, client_ip(request))
    auth_service.request_password_reset(request_ctx(request), body.email)
    return {"ok": True, "message": "Si el email está registrado, te enviamos un enlace para crear una contraseña nueva."}


@router.post("/password/reset")
def reset(body: ResetIn, request: Request, response: Response):
    ratelimit.hit(ratelimit.PASSWORD_IP, client_ip(request))
    auth_service.reset_password(request_ctx(request), body.token, body.password)
    _clear_session_cookies(response)
    return {"ok": True}


@router.post("/password/change")
def change(body: ChangePasswordIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.PASSWORD_IP, str(user.id))
    auth_service.change_password(user.ctx, user.id, user.session_id, body.current_password, body.new_password)
    return {"ok": True}


@router.post("/email/verify")
def verify(body: TokenIn, request: Request):
    ratelimit.hit(ratelimit.VERIFY_IP, client_ip(request))
    auth_service.verify_email(request_ctx(request), body.token)
    return {"ok": True}


@router.post("/email/resend")
def resend(user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.VERIFY_IP, str(user.id))
    auth_service.resend_verification(user.ctx, user.id)
    return {"ok": True}
