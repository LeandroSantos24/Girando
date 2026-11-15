"""Errores de la API con formato único: {"error": {"code", "message", "detail"}}.

Los errores de reglas de negocio que lanza la base (SQLSTATE GR403/GR409/GR422/GR429)
se traducen a HTTP para que el frontend pueda manejarlos (p.ej. 409 LIMITE_ALCANZADO).
"""
from __future__ import annotations

import logging
import re

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

log = logging.getLogger("girando.errors")

GR_STATUS = {"GR403": 403, "GR409": 409, "GR422": 422, "GR429": 429}
PG_STATUS = {"23505": 409, "23514": 422, "23503": 422, "23502": 422, "22P02": 422, "42501": 403, "22001": 422, "22003": 422}

# Mensajes legibles para los códigos de negocio más comunes
MESSAGES = {
    "LIMITE_ALCANZADO": "Llegaste al límite de publicaciones activas de tu plan.",
    "TRANSICION_NO_PERMITIDA": "Esa acción no está permitida en el estado actual.",
    "CAMPO_NO_EDITABLE": "No podés modificar ese dato.",
    "MOTIVO_OBLIGATORIO": "Indicá el motivo.",
    "VEHICULO_INCOMPLETO": "Completá marca, modelo, versión, motor y año del catálogo.",
    "ANIO_FUERA_DE_RANGO": "El año no corresponde a la versión elegida.",
    "MAXIMO_FOTOS": "Máximo 6 fotos por publicación.",
    "PUBLICACION_CERRADA": "La publicación está cerrada (vendida o eliminada).",
    "PUBLICACION_NO_DISPONIBLE": "La publicación no está disponible.",
    "RENOVACION_NO_DISPONIBLE": "Podés renovar solo en los últimos días antes del vencimiento.",
    "FECHA_DE_VENTA_INVALIDA": "La fecha de venta no es válida.",
    "SIN_COTIZACION_USD": "No hay cotización del dólar cargada para esa fecha; registrá la venta en pesos o esperá la sincronización.",
    "VERSION_INACTIVA": "Esa versión del catálogo ya no está disponible.",
    "NO_AUTORIZADO": "No tenés permiso para esta acción.",
    # ---- fase 4
    "REQUIERE_CUENTA_COMERCIAL": "Servicios y repuestos se publican desde una cuenta comercial (prestador o casa de repuestos).",
    "RUBRO_NO_PERMITIDO": "Tu cuenta no puede publicar en esa sección.",
    "REQUIERE_PAGO_Y_VERIFICACION": "Para publicar repuestos hacen falta la suscripción paga vigente y la verificación presencial aprobada.",
    "PAGO_REQUERIDO_ANTES_DE_VERIFICAR": "Primero tiene que estar aprobado el pago de la suscripción; después se coordina la verificación presencial.",
    "FICHA_DUPLICADA": "Ya tenés una ficha de ese rubro en esa zona.",
    "PUBLICACION_INCOMPLETA": "Completá los datos de la publicación antes de enviarla a revisión.",
    "SOLO_GIRANDO_VERIFICA": "El sello de verificación lo otorga solo el equipo de Girando.",
    "SOLO_MODERACION_APRUEBA": "Las ofertas de financiación las aprueba Moderación.",
    "OFERTA_DE_OTRA_AGENCIA": "Esa oferta de financiación es de otra agencia.",
    "OFERTA_NO_DISPONIBLE": "Esa oferta de financiación no está disponible.",
    "PLAN_INVALIDO": "Elegí un plan vigente para el rubro de tu cuenta.",
    "NO_ES_UNA_MEJORA": "Ese plan no es una mejora del que ya tenés. Para bajar de plan usá “Bajar de plan”: rige al renovar.",
    "SOLO_BAJA_DE_PLAN": "Desde acá solo podés dejar pendiente una baja de plan.",
    "SIN_SUSCRIPCION_VIGENTE": "La cuenta no tiene una suscripción vigente.",
    "NO_PODES_CONSULTAR_TU_PUBLICACION": "No podés escribirte por tu propia publicación.",
    "USUARIO_BLOQUEADO": "No podés escribirle a esa persona.",
    "CONVERSACION_BLOQUEADA": "La conversación está bloqueada.",
    "NO_PARTICIPANTE": "No sos parte de esa conversación.",
    "MENSAJE_REPETIDO": "Ya enviaste ese mismo mensaje.",
    "LIMITE_MENSAJES_POR_HORA": "Enviaste muchos mensajes seguidos. Esperá un rato y probá de nuevo.",
    "LIMITE_CONVERSACIONES_DIARIAS": "Llegaste al máximo de conversaciones nuevas por hoy.",
    "VERTICAL_INCORRECTA": "Los datos no corresponden a esa sección.",
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None, detail=None):
        self.status, self.code, self.message, self.detail = status, code, message or MESSAGES.get(code, code), detail


def err(status: int, code: str, message: str | None = None, detail=None) -> AppError:
    return AppError(status, code, message, detail)


def _payload(code: str, message: str, detail=None, request_id: str | None = None):
    body = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    if request_id:
        body["error"]["request_id"] = request_id
    return body


async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(_payload(exc.code, exc.message, exc.detail, getattr(request.state, "request_id", None)),
                        status_code=exc.status, headers={"Retry-After": str(exc.detail.get("retry_after"))} if isinstance(exc.detail, dict) and exc.detail.get("retry_after") else None)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    detail = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
    return JSONResponse(_payload("VALIDACION", "Revisá los datos enviados.", detail, getattr(request.state, "request_id", None)), status_code=422)


def translate_db_error(exc: DBAPIError) -> AppError:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or ""
    diag = getattr(orig, "diag", None)
    primary = (getattr(diag, "message_primary", None) or str(orig or exc)).strip()
    if sqlstate in GR_STATUS:
        code = re.split(r"[\s:]", primary, maxsplit=1)[0]
        return AppError(GR_STATUS[sqlstate], code, MESSAGES.get(code, primary), getattr(diag, "message_detail", None))
    if sqlstate in PG_STATUS:
        constraint = getattr(diag, "constraint_name", None)
        log.info("db_rule_violation", extra={"sqlstate": sqlstate, "constraint": constraint, "db_message": primary[:200]})
        code = {"23505": "DUPLICADO", "42501": "NO_AUTORIZADO"}.get(sqlstate, "DATO_INVALIDO")
        msg = MESSAGES.get(code, "El dato no es válido." if sqlstate != "23505" else "Ya existe un registro con esos datos.")
        if "row-level security" in primary:
            code, msg = "NO_AUTORIZADO", MESSAGES["NO_AUTORIZADO"]
        return AppError(PG_STATUS[sqlstate], code, msg, {"constraint": constraint} if constraint else None)
    log.exception("db_error", extra={"sqlstate": sqlstate})
    return AppError(500, "ERROR_INTERNO", "Ocurrió un error inesperado.")


async def db_error_handler(request: Request, exc: DBAPIError):
    e = translate_db_error(exc)
    return JSONResponse(_payload(e.code, e.message, e.detail, getattr(request.state, "request_id", None)), status_code=e.status)


async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("unhandled_error")
    return JSONResponse(_payload("ERROR_INTERNO", "Ocurrió un error inesperado.", None, getattr(request.state, "request_id", None)), status_code=500)
