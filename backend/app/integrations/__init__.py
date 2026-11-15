"""Integraciones externas detrás de interfaces.

Regla: si una integración no está configurada, se informa `NotConfigured` o se deja
el registro en estado pendiente. Nunca se inventan respuestas (ni "enviado", ni
ratings, ni pagos aprobados, ni cotizaciones).
"""


class NotConfigured(Exception):
    """La integración no tiene credenciales/configuración en este entorno."""

    def __init__(self, service: str, hint: str = ""):
        super().__init__(f"{service} no está configurado. {hint}".strip())
        self.service = service
