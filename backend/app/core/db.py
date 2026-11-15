"""Acceso a PostgreSQL.

La API se conecta con el rol de login `girando_api` (NOINHERIT: sin privilegios
propios). Cada unidad de trabajo abre una transacción y fija:

  SET LOCAL ROLE girando_anon | girando_app | girando_worker
  app.user_id, app.ip, app.user_agent, app.request_id, app.reason

Así las políticas RLS y los triggers de la base (fuente de verdad) saben quién
actúa. Todas las consultas usan parámetros ligados: nunca se concatena SQL con
datos del usuario.
"""
from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import get_settings

DbRole = Literal["anon", "app", "worker"]
_ROLE_SQL = {  # literales fijos: el rol nunca viene de la request
    "anon": "SET LOCAL ROLE girando_anon",
    "app": "SET LOCAL ROLE girando_app",
    "worker": "SET LOCAL ROLE girando_worker",
}

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(s.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10, future=True,
                                connect_args={"options": "-c timezone=UTC", "application_name": "girando-api"})
    return _engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@dataclass(frozen=True)
class RequestContext:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


@contextlib.contextmanager
def unit_of_work(role: DbRole, user_id: UUID | str | None = None, ctx: RequestContext | None = None,
                 reason: str | None = None) -> Iterator[Connection]:
    """Transacción con rol y contexto. Commit al salir sin error; rollback si hay excepción."""
    ctx = ctx or RequestContext()
    with get_engine().begin() as conn:
        conn.exec_driver_sql(_ROLE_SQL[role])
        conn.execute(
            text("SELECT set_config('app.user_id', :uid, true), set_config('app.ip', :ip, true),"
                 " set_config('app.user_agent', :ua, true), set_config('app.request_id', :rid, true),"
                 " set_config('app.reason', :reason, true)"),
            {"uid": str(user_id) if user_id else "", "ip": ctx.ip or "", "ua": (ctx.user_agent or "")[:300],
             "rid": ctx.request_id or "", "reason": (reason or "")[:500]},
        )
        yield conn


def set_reason(conn: Connection, reason: str | None) -> None:
    conn.execute(text("SELECT set_config('app.reason', :r, true)"), {"r": (reason or "")[:500]})


def rows(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]


def row(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    r = conn.execute(text(sql), params or {}).first()
    return dict(r._mapping) if r else None


def scalar(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> Any:
    return conn.execute(text(sql), params or {}).scalar()
