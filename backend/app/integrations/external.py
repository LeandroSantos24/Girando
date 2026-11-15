"""Servicios externos preparados. Sin credenciales → NotConfigured (sin datos simulados)."""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.integrations import NotConfigured

log = logging.getLogger("girando.integrations")


class MercadoPagoService:
    """Suscripciones (preapproval) + webhook. La activación SOLO ocurre por webhook validado."""
    API = "https://api.mercadopago.com"

    def __init__(self):
        self.token = get_settings().mercadopago_access_token
        self.webhook_secret = get_settings().mercadopago_webhook_secret

    def _require(self):
        if not self.token:
            raise NotConfigured("Mercado Pago", "Definí MERCADOPAGO_ACCESS_TOKEN (sandbox) para habilitar el checkout.")

    def create_preapproval(self, *, reason: str, amount: Decimal, currency: str, payer_email: str,
                           external_reference: str, back_url: str) -> dict:
        self._require()
        body = {"reason": reason, "external_reference": external_reference, "payer_email": payer_email,
                "back_url": back_url, "status": "pending",
                "auto_recurring": {"frequency": 1, "frequency_type": "months", "transaction_amount": float(amount), "currency_id": currency}}
        r = httpx.post(f"{self.API}/preapproval", json=body, headers={"Authorization": f"Bearer {self.token}"}, timeout=15)
        r.raise_for_status()
        return r.json()

    def create_preference(self, *, title: str, amount: Decimal, currency: str, payer_email: str,
                          external_reference: str, back_url: str) -> dict:
        """Pago único (Checkout Pro): mejora de plan o promoción. El aviso llega por webhook con topic `payment`."""
        self._require()
        body = {"items": [{"title": title, "quantity": 1, "unit_price": float(amount), "currency_id": currency}],
                "payer": {"email": payer_email}, "external_reference": external_reference,
                "back_urls": {"success": back_url, "pending": back_url, "failure": back_url}}
        r = httpx.post(f"{self.API}/checkout/preferences", json=body, headers={"Authorization": f"Bearer {self.token}"}, timeout=15)
        r.raise_for_status()
        return r.json()

    def update_preapproval_amount(self, preapproval_id: str, amount: Decimal, currency: str) -> dict:
        """Cambia el importe del próximo cobro recurrente (baja de plan que rige al renovar)."""
        self._require()
        r = httpx.put(f"{self.API}/preapproval/{preapproval_id}", headers={"Authorization": f"Bearer {self.token}"}, timeout=15,
                      json={"auto_recurring": {"transaction_amount": float(amount), "currency_id": currency}})
        r.raise_for_status()
        return r.json()

    def cancel_preapproval(self, preapproval_id: str) -> None:
        self._require()
        httpx.put(f"{self.API}/preapproval/{preapproval_id}", json={"status": "cancelled"},
                  headers={"Authorization": f"Bearer {self.token}"}, timeout=15).raise_for_status()

    def get_resource(self, topic: str, resource_id: str) -> dict:
        self._require()
        path = {"payment": f"/v1/payments/{resource_id}", "subscription_preapproval": f"/preapproval/{resource_id}",
                "subscription_authorized_payment": f"/authorized_payments/{resource_id}"}[topic]
        r = httpx.get(f"{self.API}{path}", headers={"Authorization": f"Bearer {self.token}"}, timeout=15)
        r.raise_for_status()
        return r.json()

    def verify_signature(self, x_signature: str | None, x_request_id: str | None, data_id: str) -> bool:
        """Valida x-signature: ts=...,v1=HMAC_SHA256(secret, 'id:{data.id};request-id:{x-request-id};ts:{ts};')."""
        if not self.webhook_secret or not x_signature:
            return False
        parts = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts, v1 = parts.get("ts"), parts.get("v1")
        if not ts or not v1:
            return False
        manifest = f"id:{data_id.lower()};request-id:{x_request_id or ''};ts:{ts};"
        expected = hmac.new(self.webhook_secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1)


class GoogleService:
    """Google Places: solo rating, cantidad y enlace. Sin API key no se muestra nada."""

    def __init__(self):
        self.key = get_settings().google_places_api_key

    def place_rating(self, place_id: str) -> dict:
        if not self.key:
            raise NotConfigured("Google Places", "Definí GOOGLE_PLACES_API_KEY.")
        r = httpx.get(f"https://places.googleapis.com/v1/places/{place_id}",
                      headers={"X-Goog-Api-Key": self.key, "X-Goog-FieldMask": "rating,userRatingCount,googleMapsUri"}, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {"rating": d.get("rating"), "review_count": d.get("userRatingCount"), "source_url": d.get("googleMapsUri")}


class ExchangeRateService:
    """Cotización USD→ARS. Fuente elegida: BCRA, Comunicación A 3500 (tipo de cambio de referencia
    mayorista), API pública oficial de Estadísticas Cambiarias. Se usa SOLO para normalizar precios
    (orden/filtros cruzados y estadísticas); nunca para mostrar un precio que el vendedor no puso."""

    BCRA_URL = "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD"

    def fetch_usd(self, day: date) -> Decimal:
        if get_settings().exchange_rate_provider != "bcra":
            raise NotConfigured("Cotización USD", "EXCHANGE_RATE_PROVIDER=none")
        r = httpx.get(self.BCRA_URL, params={"fechadesde": day.isoformat(), "fechahasta": day.isoformat()}, timeout=15)
        r.raise_for_status()
        results = r.json().get("results") or []
        for res in results:
            for det in res.get("detalle", []):
                if det.get("codigoMoneda") == "USD" and det.get("tipoCotizacion"):
                    return Decimal(str(det["tipoCotizacion"]))
        raise LookupError(f"BCRA sin cotización USD para {day}")
