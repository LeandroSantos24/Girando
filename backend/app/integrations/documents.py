"""Documentos privados (verificaciones): bucket S3-compatible PRIVADO. Decisión: Cloudflare R2.

- Nunca públicos, nunca en web/, nunca con URL permanente: solo URLs firmadas (SigV4) de vida corta,
  emitidas por la API después de verificar que quien pide es el titular o staff autorizado.
- R2: sin costo de egreso, compatible S3, bucket privado por defecto. Cualquier S3 sirve cambiando el endpoint.
- Sin credenciales → NotConfigured (la subida de documentos queda deshabilitada, no simulada).
"""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

from app.core.config import get_settings
from app.integrations import NotConfigured

MAX_TTL = 600  # segundos
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9/_\-.]{5,200}$")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


class DocumentStorage:
    def __init__(self):
        s = get_settings()
        self.bucket, self.endpoint = s.documents_bucket, s.documents_endpoint_url
        self.key_id, self.secret = s.documents_access_key_id, s.documents_secret_access_key
        if not all((self.bucket, self.endpoint, self.key_id, self.secret)):
            raise NotConfigured("Documentos privados", "Definí DOCUMENTS_BUCKET, DOCUMENTS_ENDPOINT_URL y las credenciales del bucket (R2).")

    def presign(self, method: str, object_key: str, ttl: int = 300, region: str = "auto", now: datetime | None = None) -> str:
        """URL firmada SigV4 (query string) para GET o PUT de un objeto puntual."""
        if method not in ("GET", "PUT"):
            raise ValueError("método no permitido")
        if not KEY_RE.match(object_key) or ".." in object_key:
            raise ValueError("clave de objeto inválida")
        ttl = max(1, min(int(ttl), MAX_TTL))
        now = now or datetime.now(UTC)
        amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        host = urlparse(self.endpoint).netloc
        path = f"/{self.bucket}/{quote(object_key, safe='/')}"
        scope = f"{day}/{region}/s3/aws4_request"
        params = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{self.key_id}/{scope}", "X-Amz-Date": amz_date,
                  "X-Amz-Expires": str(ttl), "X-Amz-SignedHeaders": "host"}
        qs = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(params.items()))
        canonical = f"{method}\n{path}\n{qs}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
        to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
        k = _sign(_sign(_sign(_sign(("AWS4" + self.secret).encode(), day), region), "s3"), "aws4_request")
        sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
        return f"https://{host}{path}?{qs}&X-Amz-Signature={sig}"
