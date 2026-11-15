"""Almacenamiento de fotos de publicaciones.

- CloudinaryImageStorage: implementación de producción (subida firmada directa desde el
  cliente + confirmación verificada contra la Admin API). Requiere credenciales.
- LocalDevImageStorage: SOLO desarrollo. Guarda en disco (MEDIA_ROOT) y sirve en /media.
  Nunca se presenta como Cloudinary: la fila queda con storage_provider = 'local_dev'.

En ambos casos: validación por contenido (no por extensión), máx. 10 MB, JPG/PNG/WEBP,
dimensiones mínimas, y re-codificación que elimina metadatos EXIF (ubicación GPS, etc.).
"""
from __future__ import annotations

import hashlib
import io
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import err
from app.integrations import NotConfigured

MAX_BYTES = 10 * 1024 * 1024
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_SIDE = 2560
Image.MAX_IMAGE_PIXELS = 60_000_000  # defensa contra "decompression bombs"


@dataclass
class StoredImage:
    provider: str
    public_id: str
    secure_url: str
    format: str
    width: int
    height: int
    bytes: int
    etag: str
    provider_version: int | None = None
    provider_asset_id: str | None = None


def validate_and_clean(data: bytes) -> tuple[bytes, str, int, int]:
    """Valida por contenido y re-codifica sin metadatos. Devuelve (bytes, formato, ancho, alto)."""
    if len(data) > MAX_BYTES:
        raise err(413, "ARCHIVO_DEMASIADO_GRANDE", "La foto pesa más de 10 MB.")
    if len(data) < 100:
        raise err(422, "ARCHIVO_INVALIDO", "El archivo está vacío o dañado.")
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise err(422, "FORMATO_INVALIDO", "Formato no válido. Usá JPG, PNG o WEBP.") from None
    if fmt not in FORMATS:
        raise err(422, "FORMATO_INVALIDO", "Formato no válido. Usá JPG, PNG o WEBP.")
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.width < 320 or img.height < 240:
        raise err(422, "IMAGEN_CHICA", "La foto es demasiado chica (mínimo 320×240).")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    elif fmt == "WEBP":
        img.save(out, "WEBP", quality=85, method=4)
    else:
        img.save(out, "PNG", optimize=True)
    return out.getvalue(), FORMATS[fmt], img.width, img.height


class LocalDevImageStorage:
    provider = "local_dev"

    def __init__(self):
        s = get_settings()
        if s.env == "production":
            raise RuntimeError("LocalDevImageStorage no se permite en producción")
        self.root = Path(s.media_root)

    def save(self, listing_id, data: bytes) -> StoredImage:
        clean, fmt, w, h = validate_and_clean(data)
        key = f"listings/{listing_id}/{uuid.uuid4().hex}.{fmt}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(clean)
        return StoredImage("local_dev", key, f"/media/{key}", fmt, w, h, len(clean), hashlib.md5(clean, usedforsecurity=False).hexdigest())

    def delete(self, public_id: str) -> None:
        p = (self.root / public_id).resolve()
        if self.root.resolve() in p.parents and p.exists():
            p.unlink()


class CloudinaryImageStorage:
    """Subida firmada directa (el archivo no pasa por la API) + confirmación server-side."""
    provider = "cloudinary"

    def __init__(self):
        s = get_settings()
        if not (s.cloudinary_cloud_name and s.cloudinary_api_key and s.cloudinary_api_secret):
            raise NotConfigured("Cloudinary", "Definí CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET.")
        self.cloud, self.key, self.secret = s.cloudinary_cloud_name, s.cloudinary_api_key, s.cloudinary_api_secret

    def _sign(self, params: dict) -> str:
        to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
        return hashlib.sha1((to_sign + self.secret).encode(), usedforsecurity=False).hexdigest()

    def upload_signature(self, listing_id) -> dict:
        params = {"timestamp": int(time.time()), "folder": f"girando/listings/{listing_id}",
                  "public_id": uuid.uuid4().hex, "allowed_formats": "jpg,png,webp", "tags": f"listing_{listing_id}"}
        return {"cloud_name": self.cloud, "api_key": self.key, "upload_url": f"https://api.cloudinary.com/v1_1/{self.cloud}/image/upload",
                "params": params, "signature": self._sign(params)}

    def confirm(self, listing_id, public_id: str, version: int, signature: str) -> StoredImage:
        if not public_id.startswith(f"girando/listings/{listing_id}/"):
            raise err(422, "IMAGEN_AJENA", "La imagen no corresponde a esta publicación.")
        expected = self._sign({"public_id": public_id, "version": version})
        if expected != signature:
            raise err(422, "FIRMA_INVALIDA", "No pudimos validar la subida.")
        r = httpx.get(f"https://api.cloudinary.com/v1_1/{self.cloud}/resources/image/upload/{public_id}",
                      auth=(self.key, self.secret), timeout=15)
        r.raise_for_status()
        d = r.json()
        if d.get("format") not in ("jpg", "jpeg", "png", "webp") or d.get("bytes", 0) > MAX_BYTES or d.get("width", 0) < 320 or d.get("height", 0) < 240:
            self.delete(public_id)
            raise err(422, "FORMATO_INVALIDO", "Formato o tamaño no válido.")
        return StoredImage("cloudinary", public_id, d["secure_url"], d["format"], d["width"], d["height"], d["bytes"],
                           d.get("etag", ""), d.get("version"), d.get("asset_id"))

    def delete(self, public_id: str) -> None:
        params = {"public_id": public_id, "timestamp": int(time.time()), "invalidate": "true"}
        httpx.post(f"https://api.cloudinary.com/v1_1/{self.cloud}/image/destroy",
                   data={**params, "api_key": self.key, "signature": self._sign(params)}, timeout=15).raise_for_status()


def get_storage():
    return CloudinaryImageStorage() if get_settings().image_storage == "cloudinary" else LocalDevImageStorage()


def storage_for(provider: str):
    return CloudinaryImageStorage() if provider == "cloudinary" else LocalDevImageStorage()
