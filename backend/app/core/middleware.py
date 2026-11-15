"""Middlewares transversales: request id + access log, headers de seguridad, CSRF, límite global."""
from __future__ import annotations

import ipaddress
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import request_id_var, user_id_var
from app.core.security import csrf_valid

access_log = logging.getLogger("girando.access")

CSRF_COOKIE = "gr_csrf"
CSRF_HEADER = "x-csrf-token"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = (re.compile(r"^/api/webhooks/"),)
_RID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'; base-uri 'self'")


_proxy_cache: dict[str, tuple[float, set[str]]] = {}


def _trusted_proxy(peer: str) -> bool:
    """¿La conexión viene de un proxy nuestro? TRUSTED_PROXIES acepta IPs, CIDR o nombres (ej. 'web' en Docker)."""
    import socket
    import time
    for entry in get_settings().trusted_proxies:
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(entry, strict=False):
                return True
            continue
        except ValueError:
            pass
        ts, ips = _proxy_cache.get(entry, (0.0, set()))
        if time.monotonic() - ts > 60:
            try:
                ips = {ai[4][0] for ai in socket.getaddrinfo(entry, None)}
            except OSError:
                ips = set()
            _proxy_cache[entry] = (time.monotonic(), ips)
        if peer in ips:
            return True
    return False


def client_ip(request: Request) -> str:
    """IP del cliente. X-Real-IP solo se acepta si la conexión viene de un proxy de confianza (nginx);
    si no, cualquiera podría falsificarla para esquivar el rate limit. Nunca se usa X-Forwarded-For."""
    peer = request.client.host if request.client else ""
    raw = peer
    xri = request.headers.get("x-real-ip")
    if xri and peer and _trusted_proxy(peer):
        raw = xri
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return "unknown"


def install(app: FastAPI) -> None:
    settings = get_settings()

    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        rid = request.headers.get("x-request-id")
        rid = rid if rid and _RID.match(rid) else uuid.uuid4().hex
        request.state.request_id = rid
        request_id_var.set(rid)
        user_id_var.set(None)
        started = time.perf_counter()
        path = request.url.path
        try:
            if path.startswith("/api/"):
                ratelimit.hit(ratelimit.GLOBAL_IP, client_ip(request))
                if request.method in UNSAFE and not any(p.match(path) for p in CSRF_EXEMPT):
                    if not csrf_valid(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
                        raise AppError(403, "CSRF_INVALIDO", "Sesión de formulario inválida. Recargá la página.")
            response = await call_next(request)
        except AppError as e:
            response = JSONResponse({"error": {"code": e.code, "message": e.message, "request_id": rid}}, status_code=e.status)
            if e.status == 429 and isinstance(e.detail, dict):
                response.headers["Retry-After"] = str(e.detail.get("retry_after", 60))
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        h = response.headers
        h["X-Request-ID"] = rid
        h["X-Content-Type-Options"] = "nosniff"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        h["X-Frame-Options"] = "DENY"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if "content-security-policy" not in h:
            h["Content-Security-Policy"] = DOCS_CSP if path in ("/docs", "/redoc") else API_CSP
        if settings.cookie_secure:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if path.startswith("/api/") and "cache-control" not in h:
            h["Cache-Control"] = "no-store"
        access_log.info("request", extra={"method": request.method, "path": path, "status": response.status_code,
                                          "duration_ms": duration_ms, "ip": client_ip(request)})
        return response
