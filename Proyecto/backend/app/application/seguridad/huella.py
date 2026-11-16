"""Huella HMAC-SHA256 truncada de un dato personal (IP, correo) para contadores y límites."""
import hashlib
import hmac

from app.core.config import settings


def huella(valor: str) -> str:
    clave = (settings.AUTH_SECRET or settings.ENTITY_MAP_KEY or "complianceai-dev").encode()
    return hmac.new(clave, valor.encode(), hashlib.sha256).hexdigest()[:32]
