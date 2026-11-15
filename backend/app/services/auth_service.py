"""Autenticación: registro, login con bloqueo, sesiones con refresh rotativo, recuperación y verificación.

Estas operaciones de sistema corren con rol `worker` porque ocurren antes de que exista
un usuario autenticado (o modifican columnas que el usuario no puede tocar).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import RequestContext, row, scalar, unit_of_work
from app.core.errors import err
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    random_token,
    sha256,
    validate_password_strength,
    verify_password,
)
from app.integrations.email import queue_email


def _norm_email(email: str) -> str:
    return email.strip().lower()


def register(ctx: RequestContext, email: str, password: str, display_name: str, platform: str = "web") -> UUID:
    problem = validate_password_strength(password)
    if problem:
        raise err(422, "CONTRASENA_DEBIL", problem)
    email = _norm_email(email)
    s = get_settings()
    with unit_of_work("worker", None, ctx) as conn:
        if scalar(conn, "SELECT 1 FROM app.users WHERE email = :e", {"e": email}):
            raise err(409, "EMAIL_EN_USO", "Ya existe una cuenta con este email. Iniciá sesión o recuperá tu contraseña.")
        uid = scalar(conn, """INSERT INTO app.users (email, password_hash, status, password_changed_at)
                              VALUES (:e, :h, 'active', now()) RETURNING id""", {"e": email, "h": hash_password(password)})
        conn.execute(text("INSERT INTO app.user_profiles (user_id, display_name) VALUES (:u, :d)"), {"u": uid, "d": display_name.strip()})
        conn.execute(text("INSERT INTO app.user_personal_data (user_id) VALUES (:u)"), {"u": uid})
        # Consentimientos obligatorios con la versión vigente de cada documento
        for ctype, dtype in (("terms", "terms"), ("privacy_policy", "privacy_policy")):
            pv = scalar(conn, "SELECT id FROM app.policy_versions WHERE doc_type = :d ORDER BY published_at DESC LIMIT 1", {"d": dtype})
            if pv:
                conn.execute(text("""INSERT INTO app.consents (user_id, consent_type, policy_version_id, state, channel, user_agent)
                                        VALUES (:u, :t, :pv, 'granted', :ch, :ua)"""),
                             {"u": uid, "t": ctype, "pv": pv, "ch": platform, "ua": (ctx.user_agent or "")[:300]})
        token = _issue_token(conn, uid, "email_verification", hours=48)
        link = f"{s.public_base_url}/#verificar-email?token={token}"
        queue_email(conn, "auth.verify_email", email, uid, "account_created", {"link": "[token]"}, dev_link=link)
    return uid


def _issue_token(conn, user_id, purpose: str, hours: int, new_value: str | None = None) -> str:
    token = random_token(32)
    conn.execute(text("""INSERT INTO app.auth_tokens (user_id, purpose, token_hash, new_value, expires_at)
                           VALUES (:u, :p, :h, :nv, now() + make_interval(hours => :hrs))"""),
                 {"u": user_id, "p": purpose, "h": sha256(token), "nv": new_value, "hrs": hours})
    return token


def login(ctx: RequestContext, email: str, password: str, platform: str = "web") -> dict:
    """Los fallos se registran y se COMMITEAN antes de responder (contador de bloqueo e intentos)."""
    s = get_settings()
    email = _norm_email(email)
    failure = None
    with unit_of_work("worker", None, ctx) as conn:
        u = row(conn, "SELECT id, password_hash, status::text AS status, locked_until FROM app.users WHERE email = :e FOR UPDATE", {"e": email})
        now = datetime.now(UTC)
        if u and u["locked_until"] and u["locked_until"] > now:
            _attempt(conn, email, u["id"], ctx, False, "locked")
            minutes = max(1, int((u["locked_until"] - now).total_seconds() // 60) + 1)
            failure = err(423, "CUENTA_BLOQUEADA_TEMPORALMENTE", f"Demasiados intentos fallidos. Probá de nuevo en {minutes} minutos.")
        elif not verify_password(password, u["password_hash"] if u else None):
            if u:
                conn.execute(text("""UPDATE app.users SET failed_login_count = failed_login_count + 1,
                        locked_until = CASE WHEN failed_login_count + 1 >= :max THEN now() + make_interval(mins => :lock) ELSE locked_until END
                        WHERE id = :id"""), {"id": u["id"], "max": s.login_max_failures, "lock": s.login_lock_minutes})
            _attempt(conn, email, u["id"] if u else None, ctx, False, "bad_credentials")
            failure = err(401, "CREDENCIALES_INVALIDAS", "Email o contraseña incorrectos.")
        elif u["status"] in ("suspended", "blocked", "deleted"):
            _attempt(conn, email, u["id"], ctx, False, f"status_{u['status']}")
            failure = err(403, "CUENTA_SUSPENDIDA", "Tu cuenta no está habilitada. Escribinos a soporte.")
        else:
            new_hash = hash_password(password) if needs_rehash(u["password_hash"]) else u["password_hash"]
            conn.execute(text("""UPDATE app.users SET failed_login_count = 0, locked_until = NULL, last_login_at = now(), password_hash = :h
                                   WHERE id = :id"""), {"id": u["id"], "h": new_hash})
            _attempt(conn, email, u["id"], ctx, True, None)
            session = _new_session(conn, u["id"], ctx, platform, s.refresh_token_days)
    if failure:
        raise failure
    return session


def _attempt(conn, email, user_id, ctx: RequestContext, success: bool, reason: str | None):
    conn.execute(text("""INSERT INTO app.login_attempts (email, user_id, ip, user_agent, success, failure_reason)
                           VALUES (:e, :u, CAST(NULLIF(:ip, 'unknown') AS inet), :ua, :s, :r)"""),
                 {"e": email, "u": user_id, "ip": ctx.ip or "unknown", "ua": (ctx.user_agent or "")[:300], "s": success, "r": reason})


def _platform(p: str) -> str:
    return p if p in ("web", "ios", "android", "admin", "api") else "web"


def _new_session(conn, user_id, ctx: RequestContext, platform: str, days: int) -> dict:
    refresh = random_token(48)
    sid = scalar(conn, """INSERT INTO app.sessions (user_id, refresh_token_hash, platform, device_label, user_agent, ip, expires_at)
                          VALUES (:u, :h, CAST(:p AS app.client_platform), :dl, :ua, CAST(NULLIF(:ip, 'unknown') AS inet), now() + make_interval(days => :d))
                          RETURNING id""",
                 {"u": user_id, "h": sha256(refresh), "p": _platform(platform), "dl": _device_label(ctx.user_agent),
                  "ua": (ctx.user_agent or "")[:300], "ip": ctx.ip or "unknown", "d": days})
    access, access_exp = create_access_token(user_id, sid)
    return {"user_id": user_id, "session_id": sid, "access": access, "access_exp": access_exp, "refresh": refresh}


def _device_label(ua: str | None) -> str:
    ua = (ua or "").lower()
    browser = next((b for k, b in (("edg", "Edge"), ("chrome", "Chrome"), ("firefox", "Firefox"), ("safari", "Safari")) if k in ua), "Navegador")
    osn = next((o for k, o in (("android", "Android"), ("iphone", "iPhone"), ("windows", "Windows"), ("mac os", "Mac"), ("linux", "Linux")) if k in ua), "")
    return f"{browser} en {osn}".strip() if osn else browser


def refresh(ctx: RequestContext, refresh_token: str) -> dict:
    s = get_settings()
    with unit_of_work("worker", None, ctx) as conn:
        sess = row(conn, """SELECT s.id, s.user_id, u.status::text AS status FROM app.sessions s JOIN app.users u ON u.id = s.user_id
                            WHERE s.refresh_token_hash = :h AND s.ended_at IS NULL AND s.expires_at > now() FOR UPDATE OF s""",
                   {"h": sha256(refresh_token)})
        if not sess or sess["status"] not in ("active", "pending"):
            raise err(401, "SESION_EXPIRADA", "Tu sesión expiró. Volvé a ingresar.")
        new_refresh = random_token(48)
        conn.execute(text("""UPDATE app.sessions SET refresh_token_hash = :h, last_seen_at = now(),
                               expires_at = now() + make_interval(days => :d) WHERE id = :id"""),
                     {"h": sha256(new_refresh), "d": s.refresh_token_days, "id": sess["id"]})
        access, exp = create_access_token(sess["user_id"], sess["id"])
        return {"user_id": sess["user_id"], "session_id": sess["id"], "access": access, "access_exp": exp, "refresh": new_refresh}


def end_session(ctx: RequestContext, user_id: UUID, session_id: UUID, reason: str = "logout") -> None:
    with unit_of_work("app", user_id, ctx) as conn:
        conn.execute(text("""UPDATE app.sessions SET ended_at = now(), end_reason = CAST(:r AS app.session_end_reason)
                               WHERE id = :id AND user_id = :u AND ended_at IS NULL"""), {"id": session_id, "u": user_id, "r": reason})


def end_other_sessions(ctx: RequestContext, user_id: UUID, keep_session: UUID) -> int:
    with unit_of_work("app", user_id, ctx) as conn:
        res = conn.execute(text("""UPDATE app.sessions SET ended_at = now(), end_reason = 'logout_others'
                                     WHERE user_id = :u AND id <> :keep AND ended_at IS NULL"""), {"u": user_id, "keep": keep_session})
        return res.rowcount


def request_password_reset(ctx: RequestContext, email: str) -> None:
    """Respuesta idéntica exista o no la cuenta (no revela emails registrados)."""
    s = get_settings()
    email = _norm_email(email)
    with unit_of_work("worker", None, ctx) as conn:
        uid = scalar(conn, "SELECT id FROM app.users WHERE email = :e AND status IN ('active','pending')", {"e": email})
        if not uid:
            return
        token = _issue_token(conn, uid, "password_reset", hours=1)
        queue_email(conn, "auth.password_reset", email, uid, "password_reset_requested", {"link": "[token]"},
                    dev_link=f"{s.public_base_url}/#recuperar?token={token}")


def reset_password(ctx: RequestContext, token: str, new_password: str) -> None:
    problem = validate_password_strength(new_password)
    if problem:
        raise err(422, "CONTRASENA_DEBIL", problem)
    with unit_of_work("worker", None, ctx) as conn:
        t = row(conn, """SELECT id, user_id FROM app.auth_tokens WHERE token_hash = :h AND purpose = 'password_reset'
                         AND used_at IS NULL AND expires_at > now() FOR UPDATE""", {"h": sha256(token)})
        if not t:
            raise err(400, "TOKEN_INVALIDO", "El enlace no es válido o expiró. Pedí uno nuevo.")
        conn.execute(text("UPDATE app.auth_tokens SET used_at = now() WHERE id = :id"), {"id": t["id"]})
        conn.execute(text("""UPDATE app.users SET password_hash = :h, password_changed_at = now(), failed_login_count = 0, locked_until = NULL
                               WHERE id = :u"""), {"h": hash_password(new_password), "u": t["user_id"]})
        conn.execute(text("""UPDATE app.sessions SET ended_at = now(), end_reason = 'password_change'
                               WHERE user_id = :u AND ended_at IS NULL"""), {"u": t["user_id"]})


def verify_email(ctx: RequestContext, token: str) -> None:
    with unit_of_work("worker", None, ctx) as conn:
        t = row(conn, """SELECT id, user_id FROM app.auth_tokens WHERE token_hash = :h AND purpose = 'email_verification'
                         AND used_at IS NULL AND expires_at > now() FOR UPDATE""", {"h": sha256(token)})
        if not t:
            raise err(400, "TOKEN_INVALIDO", "El enlace no es válido o expiró.")
        conn.execute(text("UPDATE app.auth_tokens SET used_at = now() WHERE id = :id"), {"id": t["id"]})
        conn.execute(text("UPDATE app.users SET email_verified_at = coalesce(email_verified_at, now()) WHERE id = :u"), {"u": t["user_id"]})


def resend_verification(ctx: RequestContext, user_id: UUID) -> None:
    s = get_settings()
    with unit_of_work("worker", None, ctx) as conn:
        u = row(conn, "SELECT email::text AS email, email_verified_at FROM app.users WHERE id = :u", {"u": user_id})
        if not u or u["email_verified_at"]:
            return
        token = _issue_token(conn, user_id, "email_verification", hours=48)
        queue_email(conn, "auth.verify_email", u["email"], user_id, "verification_resent", {"link": "[token]"},
                    dev_link=f"{s.public_base_url}/#verificar-email?token={token}")


def change_password(ctx: RequestContext, user_id: UUID, session_id: UUID, current: str, new: str) -> None:
    problem = validate_password_strength(new)
    if problem:
        raise err(422, "CONTRASENA_DEBIL", problem)
    with unit_of_work("worker", None, ctx) as conn:
        h = scalar(conn, "SELECT password_hash FROM app.users WHERE id = :u", {"u": user_id})
        if not verify_password(current, h):
            raise err(401, "CREDENCIALES_INVALIDAS", "La contraseña actual no es correcta.")
        conn.execute(text("UPDATE app.users SET password_hash = :h, password_changed_at = now() WHERE id = :u"),
                     {"h": hash_password(new), "u": user_id})
        conn.execute(text("""UPDATE app.sessions SET ended_at = now(), end_reason = 'password_change'
                               WHERE user_id = :u AND id <> :sid AND ended_at IS NULL"""), {"u": user_id, "sid": session_id})


def session_expiry(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)
