"""
Cifrado y huellas de datos personales (Ley 21.719). Todo parte de ENTITY_MAP_KEY.

- Huella de cada valor anonimizado: HMAC-SHA256 con una subclave derivada. Permite
  buscar "¿en qué evidencias aparece este RUT?" sin guardar el valor. Un SHA-256
  simple NO sirve: el espacio de RUTs es pequeño y se revierte por fuerza bruta.
- Mapa de entidades (valores originales): Fernet. HU-06 (decisión del PO, 16-oct):
  por defecto YA NO se guarda (GUARDAR_MAPA_ENTIDADES_CIFRADO=false) para que la
  anonimización sea irreversible; queda el código por si el PO lo reactiva.
- Subclaves por propósito (HKDF-SHA256), para no reutilizar la misma clave en
  contextos distintos:
    "evidencias" -> archivos de evidencia en disco hasta que el worker los anonimiza
    "arcop"      -> textos de las solicitudes ARCOP (excepción documentada en HU-06)

Generar una clave:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Rotar ENTITY_MAP_KEY deja ilegibles los textos ARCOP y los archivos aún no procesados
cifrados con la clave anterior: rotarla exige recifrarlos (ver CAMBIOS_HU06.md).
"""
import base64
import hashlib
import hmac
import json

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class ClaveCifradoInvalida(ValueError):
    pass


def _bytes_clave(clave: str) -> bytes:
    if not clave:
        raise ClaveCifradoInvalida("ENTITY_MAP_KEY no configurada")
    try:
        crudo = base64.urlsafe_b64decode(clave)
    except (ValueError, TypeError) as e:
        raise ClaveCifradoInvalida(
            "ENTITY_MAP_KEY inválida: debe ser una clave Fernet (32 bytes en base64 url-safe)"
        ) from e
    if len(crudo) != 32:
        raise ClaveCifradoInvalida("ENTITY_MAP_KEY inválida: debe decodificar a 32 bytes")
    return crudo


def derivar_clave(clave_maestra: str, proposito: str) -> str:
    """Subclave Fernet independiente para `proposito` (HKDF-SHA256 sobre la clave maestra)."""
    sub = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=f"complianceai/{proposito}/v1".encode(),
    ).derive(_bytes_clave(clave_maestra))
    return base64.urlsafe_b64encode(sub).decode()


class CifradorDatos:
    """
    Fernet con un prefijo reconocible, para textos (columnas) y bytes (archivos).
    El prefijo permite distinguir lo cifrado de lo antiguo en claro y migrar sin
    romper lecturas: lo que no lleva prefijo se devuelve tal cual.
    """
    PREFIJO_TEXTO = "enc:v1:"
    PREFIJO_BYTES = b"CAIENC1\n"

    def __init__(self, clave_maestra: str, proposito: str):
        self._fernet = Fernet(derivar_clave(clave_maestra, proposito))

    # ---- textos
    def cifrar_texto(self, texto: str) -> str:
        if texto.startswith(self.PREFIJO_TEXTO):
            return texto  # ya cifrado (p. ej. una fila que se vuelve a guardar)
        return self.PREFIJO_TEXTO + self._fernet.encrypt(texto.encode("utf-8")).decode()

    def descifrar_texto(self, valor: str) -> str:
        if not valor.startswith(self.PREFIJO_TEXTO):
            return valor  # fila antigua sin cifrar
        try:
            return self._fernet.decrypt(valor[len(self.PREFIJO_TEXTO):].encode()).decode("utf-8")
        except InvalidToken as e:
            raise ClaveCifradoInvalida("No se pudo descifrar (clave distinta o dato alterado)") from e

    @classmethod
    def esta_cifrado(cls, valor) -> bool:
        if isinstance(valor, bytes):
            return valor.startswith(cls.PREFIJO_BYTES)
        return isinstance(valor, str) and valor.startswith(cls.PREFIJO_TEXTO)

    # ---- bytes (archivos)
    def cifrar_bytes(self, contenido: bytes) -> bytes:
        return self.PREFIJO_BYTES + self._fernet.encrypt(contenido)

    def descifrar_bytes(self, contenido: bytes) -> bytes:
        if not contenido.startswith(self.PREFIJO_BYTES):
            return contenido  # archivo antiguo o ya reemplazado por el texto anonimizado
        try:
            return self._fernet.decrypt(contenido[len(self.PREFIJO_BYTES):])
        except InvalidToken as e:
            raise ClaveCifradoInvalida("No se pudo descifrar el archivo (clave distinta o dato alterado)") from e


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
