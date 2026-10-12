"""
Cifrado del mapa de entidades (auditoría Ley 21.719).

- Valores originales: Fernet (AES-128-CBC + HMAC-SHA256) con ENTITY_MAP_KEY.
- Huella de cada valor: HMAC-SHA256 con una subclave derivada. Permite buscar
  "¿en qué evidencias aparece este RUT?" sin descifrar nada. Un SHA-256 simple
  NO sirve: el espacio de RUTs es pequeño y se revierte por fuerza bruta.

Generar una clave:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import base64
import hashlib
import hmac
import json

from cryptography.fernet import Fernet, InvalidToken


class ClaveCifradoInvalida(ValueError):
    pass


class CifradorEntidades:
    def __init__(self, clave: str):
        if not clave:
            raise ClaveCifradoInvalida("ENTITY_MAP_KEY no configurada")
        try:
            self._fernet = Fernet(clave.encode() if isinstance(clave, str) else clave)
            crudo = base64.urlsafe_b64decode(clave)
        except (ValueError, TypeError) as e:
            raise ClaveCifradoInvalida(
                "ENTITY_MAP_KEY inválida: debe ser una clave Fernet (32 bytes en base64 url-safe)"
            ) from e
        self._clave_hmac = hashlib.sha256(b"complianceai/entity-hmac/v1|" + crudo).digest()

    def cifrar_json(self, datos) -> str:
        return self._fernet.encrypt(json.dumps(datos, ensure_ascii=False).encode("utf-8")).decode()

    def descifrar_json(self, token: str):
        try:
            return json.loads(self._fernet.decrypt(token.encode()).decode("utf-8"))
        except InvalidToken as e:
            raise ClaveCifradoInvalida("No se pudo descifrar el mapa (clave distinta o dato alterado)") from e

    def huella(self, valor: str) -> str:
        """HMAC del valor normalizado (sin espacios, puntos ni guiones, en minúscula)."""
        normal = "".join(c for c in valor.lower() if c.isalnum() or c == "@")
        return hmac.new(self._clave_hmac, normal.encode("utf-8"), hashlib.sha256).hexdigest()
