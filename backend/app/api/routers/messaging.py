"""Fase 4 · Mensajería interna (vehículos, taxis, servicios, repuestos y empleos).

  · Una conversación por publicación y por interesado. En empleos es la postulación: sin CVs ni adjuntos.
  · Nunca se exponen emails ni teléfonos: solo el nombre visible. Lo que la gente escriba es decisión suya.
  · Anti-spam y bloqueos en la base (triggers) + rate limit en la API.
  · Moderación solo ve mensajes de conversaciones que tienen un reporte (RLS).
"""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import StringConstraints, field_validator, model_validator
from sqlalchemy import text

from app.api.deps import CurrentUser, current_user, require_roles
from app.core import ratelimit
from app.core.db import row, rows, scalar, unit_of_work
from app.core.errors import err
from app.schemas.common import StrictModel, clean_text
from app.services.analytics import track

router = APIRouter(prefix="/api", tags=["mensajes · fase 4"])
MOD = require_roles("moderator", "admin")
Body = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class StartIn(StrictModel):
    listing_code: Annotated[str, StringConstraints(max_length=16)] | None = None
    post_code: Annotated[str, StringConstraints(max_length=16)] | None = None
    message: Body

    @field_validator("message")
    @classmethod
    def _c(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def _one(self):
        if (self.listing_code is None) == (self.post_code is None):
            raise ValueError("Indicá una publicación")
        return self


class MessageIn(StrictModel):
    body: Body

    @field_validator("body")
    @classmethod
    def _c(cls, v):
        return clean_text(v)


CONV_SQL = """SELECT c.id, c.status::text AS status, c.listing_id, c.post_id, c.last_message_at, c.created_at,
       (c.buyer_user_id = app.me()) AS i_am_buyer, c.buyer_user_id, c.seller_user_id, c.seller_agency_id, a.trade_name AS agency_name,
       coalesce(l.title, p.title) AS subject_title, coalesce(l.public_code, p.public_code) AS subject_code,
       coalesce(p.vertical::text, 'vehicle') AS vertical, coalesce(l.status::text, p.status::text) AS subject_status,
       (SELECT count(*) FROM app.messages m WHERE m.conversation_id = c.id AND m.read_at IS NULL AND m.deleted_at IS NULL
           AND m.visibility = 'visible'
           AND m.sender_side::text <> (CASE WHEN c.buyer_user_id = app.me() THEN 'buyer' ELSE 'seller' END)) AS unread,
       (SELECT left(m.body, 120) FROM app.messages m WHERE m.conversation_id = c.id AND m.deleted_at IS NULL AND m.visibility = 'visible'
         ORDER BY m.created_at DESC LIMIT 1) AS last_message
  FROM app.conversations c
  LEFT JOIN app.listings l ON l.id = c.listing_id LEFT JOIN app.posts p ON p.id = c.post_id
  LEFT JOIN app.agencies a ON a.id = c.seller_agency_id"""


def _names(ctx, convs: list[dict]) -> None:
    """Nombre visible de la otra parte. Se resuelve con rol de sistema SOLO para conversaciones que RLS ya dejó ver."""
    ids = {c["seller_user_id"] if c["i_am_buyer"] else c["buyer_user_id"] for c in convs}
    names = {}
    if ids:
        with unit_of_work("worker", None, ctx) as w:
            names = {r["user_id"]: r["display_name"] for r in rows(
                w, "SELECT user_id, display_name FROM app.user_profiles WHERE user_id = ANY(CAST(:i AS uuid[]))", {"i": [str(i) for i in ids]})}
    for c in convs:
        other = c.pop("seller_user_id") if c["i_am_buyer"] else c.pop("buyer_user_id")
        c.pop("seller_user_id", None)
        c.pop("buyer_user_id", None)
        c["counterpart"] = (c["agency_name"] if c["i_am_buyer"] and c["agency_name"] else names.get(other)) or "Usuario de Girando"


def _conv(conn, user, conv_id) -> dict:
    c = row(conn, CONV_SQL + """ WHERE c.id = :c AND (c.buyer_user_id = app.me() OR c.seller_user_id = app.me()
                                   OR (c.seller_agency_id IS NOT NULL AND app.app_is_agency_member(c.seller_agency_id)))""", {"c": conv_id})
    if not c:
        raise err(404, "NO_ENCONTRADA", "La conversación no existe o no participás en ella.")
    return c


@router.post("/me/conversations", status_code=201)
def start_conversation(body: StartIn, user: CurrentUser = Depends(current_user)):
    """Contactar por una publicación. Si ya existe la conversación, agrega el mensaje ahí."""
    ratelimit.hit(ratelimit.MESSAGE_USER, str(user.id))
    with unit_of_work("anon", None, user.ctx) as conn:
        if body.listing_code:
            sid = scalar(conn, "SELECT id FROM api_public.listings WHERE public_code = :c", {"c": body.listing_code})
        else:
            sid = scalar(conn, "SELECT id FROM api_public.posts WHERE public_code = :c", {"c": body.post_code})
    if not sid:
        raise err(404, "PUBLICACION_NO_DISPONIBLE")
    col = "listing_id" if body.listing_code else "post_id"
    with unit_of_work("app", user.id, user.ctx) as conn:
        cid = scalar(conn, f"SELECT id FROM app.conversations WHERE {col} = :s AND buyer_user_id = :u", {"s": sid, "u": user.id})
        if not cid:
            # buyer/seller reales los fija el trigger a partir de la sesión y de la publicación
            cid = scalar(conn, f"INSERT INTO app.conversations ({col}, buyer_user_id, seller_user_id) VALUES (:s, :u, :u) RETURNING id",
                         {"s": sid, "u": user.id})
        conn.execute(text("INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body) VALUES (:c, :u, 'buyer', :b)"),
                     {"c": cid, "u": user.id, "b": body.message})
        c = _conv(conn, user, cid)
    track("message_sent", user.ctx, None, listing_id=c["listing_id"], agency_id=c["seller_agency_id"], properties={"vertical": c["vertical"], "first": True})
    if c["listing_id"]:
        track("listing_contact", user.ctx, None, listing_id=c["listing_id"], agency_id=c["seller_agency_id"], properties={"channel": "mensaje"})
    _names(user.ctx, [c])
    return c


@router.get("/me/conversations")
def conversations(archived: bool = False, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        items = rows(conn, CONV_SQL + """ WHERE (c.buyer_user_id = app.me() OR c.seller_user_id = app.me()
                                              OR (c.seller_agency_id IS NOT NULL AND app.app_is_agency_member(c.seller_agency_id)))
                                            AND ((CASE WHEN c.buyer_user_id = app.me() THEN c.buyer_archived_at ELSE c.seller_archived_at END) IS NOT NULL) = :ar
                                          ORDER BY c.last_message_at DESC NULLS LAST LIMIT 200""", {"ar": archived})
    _names(user.ctx, items)
    return {"items": items, "unread_total": sum(i["unread"] for i in items)}


@router.get("/me/conversations/{conv_id}")
def conversation(conv_id: UUID, user: CurrentUser = Depends(current_user)):
    """Mensajes de la conversación. Al abrirla se marcan como leídos los que recibí."""
    with unit_of_work("app", user.id, user.ctx) as conn:
        c = _conv(conn, user, conv_id)
        mine = "buyer" if c["i_am_buyer"] else "seller"
        conn.execute(text("""UPDATE app.messages SET read_at = now() WHERE conversation_id = :c AND read_at IS NULL
                              AND sender_user_id <> :u AND sender_side <> CAST(:m AS app.participant_side)"""), {"c": conv_id, "u": user.id, "m": mine})
        msgs = rows(conn, """SELECT m.id, (m.sender_side = CAST(:m AS app.participant_side)) AS mine, m.created_at, m.read_at,
                                    CASE WHEN m.deleted_at IS NOT NULL THEN NULL WHEN m.visibility <> 'visible' THEN NULL ELSE m.body END AS body,
                                    (m.deleted_at IS NOT NULL) AS deleted, (m.visibility <> 'visible') AS hidden
                               FROM app.messages m WHERE m.conversation_id = :c ORDER BY m.created_at LIMIT 500""", {"c": conv_id, "m": mine})
    _names(user.ctx, [c])
    return {"conversation": c, "messages": msgs}


@router.post("/me/conversations/{conv_id}/messages", status_code=201)
def send_message(conv_id: UUID, body: MessageIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.MESSAGE_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        c = _conv(conn, user, conv_id)
        mid = scalar(conn, """INSERT INTO app.messages (conversation_id, sender_user_id, sender_side, body)
                              VALUES (:c, :u, 'buyer', :b) RETURNING id""", {"c": conv_id, "u": user.id, "b": body.body})   # el lado lo fija el trigger
    track("message_sent", user.ctx, None, listing_id=c["listing_id"], agency_id=c["seller_agency_id"], properties={"vertical": c["vertical"]})
    return {"id": mid}


@router.post("/me/conversations/{conv_id}/{action}")
def conversation_action(conv_id: UUID, action: Literal["block", "archive", "unarchive"], user: CurrentUser = Depends(current_user)):
    """block: bloquea a la otra persona (no puede volver a escribirte en ninguna publicación). archive: la saca de tu bandeja."""
    with unit_of_work("app", user.id, user.ctx, reason=f"Conversación: {action}") as conn:
        c = _conv(conn, user, conv_id)
        if action == "block":
            other = scalar(conn, "SELECT CASE WHEN buyer_user_id = :u THEN seller_user_id ELSE buyer_user_id END FROM app.conversations WHERE id = :c",
                           {"u": user.id, "c": conv_id})
            conn.execute(text("INSERT INTO app.user_blocks (blocker_user_id, blocked_user_id) VALUES (:u, :o) ON CONFLICT DO NOTHING"), {"u": user.id, "o": other})
            conn.execute(text("UPDATE app.conversations SET status = 'blocked', blocked_by_user_id = :u, blocked_at = now() WHERE id = :c AND status <> 'blocked'"),
                         {"u": user.id, "c": conv_id})
        else:
            col = "buyer_archived_at" if c["i_am_buyer"] else "seller_archived_at"
            conn.execute(text(f"UPDATE app.conversations SET {col} = CASE WHEN :a THEN now() END WHERE id = :c"), {"a": action == "archive", "c": conv_id})
    return {"ok": True}


class ReportMessageIn(StrictModel):
    reason_id: UUID
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None


@router.post("/me/messages/{message_id}/report", status_code=201)
def report_message(message_id: UUID, body: ReportMessageIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit(ratelimit.REPORT_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx) as conn:
        if not scalar(conn, "SELECT 1 FROM app.messages WHERE id = :m AND sender_user_id <> :u", {"m": message_id, "u": user.id}):   # RLS: solo participantes
            raise err(404, "NO_ENCONTRADA", "No encontramos ese mensaje.")
        rid = scalar(conn, """INSERT INTO app.reports (reporter_user_id, target, message_id, reason_id, description)
                              VALUES (:u, 'message', :m, :r, :d) RETURNING id""",
                     {"u": user.id, "m": message_id, "r": body.reason_id, "d": clean_text(body.description)})
    return {"id": rid, "status": "pending"}


@router.delete("/me/messages/{message_id}")
def delete_message(message_id: UUID, user: CurrentUser = Depends(current_user)):
    with unit_of_work("app", user.id, user.ctx) as conn:
        n = conn.execute(text("UPDATE app.messages SET deleted_at = now() WHERE id = :m AND sender_user_id = :u AND deleted_at IS NULL"),
                         {"m": message_id, "u": user.id}).rowcount
    if not n:
        raise err(404, "NO_ENCONTRADA", "No encontramos ese mensaje.")
    return {"ok": True}


# --------------------------------------------------------------------------- moderación de mensajes reportados
@router.get("/admin/reported-messages")
def reported_messages(user: CurrentUser = Depends(MOD)):
    ratelimit.hit(ratelimit.ADMIN_USER, str(user.id))
    with unit_of_work("app", user.id, user.ctx, reason="Revisión de mensajes reportados") as conn:
        return {"items": rows(conn, """SELECT r.id AS report_id, r.status::text AS report_status, r.description, rr.label AS reason, r.created_at AS reported_at,
                                              m.id AS message_id, m.conversation_id, m.body, m.visibility::text AS visibility, m.created_at, m.sender_user_id
                                         FROM app.reports r JOIN app.messages m ON m.id = r.message_id JOIN app.report_reasons rr ON rr.id = r.reason_id
                                        WHERE r.target = 'message' ORDER BY (r.status = 'pending') DESC, r.created_at DESC LIMIT 200""")}


@router.post("/admin/messages/{message_id}/{action}")
def moderate_message(message_id: UUID, action: Literal["hide", "restore"], user: CurrentUser = Depends(MOD)):
    with unit_of_work("app", user.id, user.ctx, reason=f"Mensaje reportado: {action}") as conn:
        n = conn.execute(text("UPDATE app.messages SET visibility = CAST(:v AS app.message_visibility) WHERE id = :m"),
                         {"v": "hidden_by_moderation" if action == "hide" else "visible", "m": message_id}).rowcount
        if not n:
            raise err(404, "NO_ENCONTRADA", "El mensaje no existe o no tiene un reporte que habilite verlo.")
        conn.execute(text("""INSERT INTO app.audit_logs (actor_user_id, actor_type, action, entity_type, entity_id, reason)
                             VALUES (:u, 'staff', :a, 'message', :m, 'Moderación de mensaje reportado')"""),
                     {"u": user.id, "a": f"message.{action}", "m": message_id})
    return {"ok": True}
