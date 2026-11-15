"""Rate limiting por ventana fija.

Backend Redis (compartido entre instancias). Si Redis no está disponible se usa un
contador en memoria del proceso (degradado pero nunca "sin límite") y se loguea.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import err

log = logging.getLogger("girando.ratelimit")


@dataclass(frozen=True)
class Limit:
    bucket: str
    limit: int
    window_s: int


# Límites por endpoint sensible (ajustables sin tocar la lógica)
LOGIN_IP = Limit("login_ip", 20, 900)
LOGIN_EMAIL = Limit("login_email", 8, 900)
REGISTER_IP = Limit("register_ip", 5, 3600)
PASSWORD_IP = Limit("password_ip", 5, 3600)
VERIFY_IP = Limit("verify_ip", 20, 3600)
REFRESH_IP = Limit("refresh_ip", 60, 60)
SEARCH_IP = Limit("search_ip", 120, 60)
LISTING_CREATE_USER = Limit("listing_create", 20, 3600)
LISTING_WRITE_USER = Limit("listing_write", 120, 60)
IMAGE_UPLOAD_USER = Limit("image_upload", 60, 3600)
FAVORITE_USER = Limit("favorite", 120, 60)
REPORT_USER = Limit("report", 10, 3600)
MESSAGE_USER = Limit("message", 30, 60)
CONTACT_REVEAL_USER = Limit("contact_reveal", 60, 3600)
ADMIN_USER = Limit("admin", 300, 60)
GLOBAL_IP = Limit("global_ip", 600, 60)
OUTBOUND_IP = Limit("outbound_ip", 60, 60)


class _Memory:
    def __init__(self):
        self._d: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            count, exp = self._d.get(key, (0, now + window))
            if exp <= now:
                count, exp = 0, now + window
            count += 1
            self._d[key] = (count, exp)
            if len(self._d) > 50000:
                self._d = {k: v for k, v in self._d.items() if v[1] > now}
            return count

    def reset(self):
        with self._lock:
            self._d.clear()


_memory = _Memory()
_redis = None
_redis_failed_at = 0.0


def _get_redis():
    global _redis, _redis_failed_at
    url = get_settings().redis_url
    if not url or time.time() - _redis_failed_at < 30:
        return None
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(url, socket_timeout=0.3, socket_connect_timeout=0.3)
    return _redis


def hit(limit: Limit, ident: str) -> None:
    """Cuenta un intento; lanza 429 si se supera el límite."""
    if not get_settings().rate_limit_enabled:
        return
    window = int(time.time() // limit.window_s)
    key = f"rl:{limit.bucket}:{ident}:{window}"
    count = None
    r = _get_redis()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, limit.window_s + 5)
            count = pipe.execute()[0]
        except Exception:  # noqa: BLE001 - Redis caído: degradar a memoria
            global _redis_failed_at
            _redis_failed_at = time.time()
            log.warning("ratelimit_redis_unavailable_fallback_memory")
    if count is None:
        count = _memory.hit(key, limit.window_s)
    if count > limit.limit:
        retry = limit.window_s - int(time.time() % limit.window_s)
        raise err(429, "DEMASIADOS_INTENTOS", "Demasiados intentos. Probá de nuevo en unos minutos.", {"retry_after": retry})


def reset_memory() -> None:
    _memory.reset()
