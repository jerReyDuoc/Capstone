"""
HU-06 — Columnas de texto cifradas en reposo (excepción documentada para ARCOP).

Los textos de una solicitud ARCOP (descripción del titular, comentarios del
historial y respuesta del responsable) pueden contener datos personales que se
NECESITAN para atender el derecho (p. ej. el dato correcto en una rectificación),
así que no se pueden reemplazar por etiquetas. Decisión del PO (16-oct): se guardan
cifrados con Fernet (subclave "arcop" derivada de ENTITY_MAP_KEY) y solo se
descifran al leerlos por el ORM, es decir, para el titular dueño y para el admin
a través de la API. En la BD, en los respaldos y en los logs nunca quedan en claro.

Uso en un modelo:  mapped_column("descripcion", TextoCifrado, nullable=False)

- La columna sigue siendo TEXT: no requiere migración de esquema.
- Lo que no lleva el prefijo "enc:v1:" se lee tal cual (filas anteriores a HU-06);
  scripts/migrar_pii_hu06.py las cifra.
- Sin ENTITY_MAP_KEY no se puede escribir (fail-closed): nunca se guarda en claro.
"""
import logging
from functools import lru_cache

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings
from app.infrastructure.security.cifrado import CifradorDatos, ClaveCifradoInvalida

logger = logging.getLogger("cifrado")

TEXTO_ILEGIBLE = "[texto cifrado ilegible]"


@lru_cache(maxsize=4)
def _cifrador(clave: str) -> CifradorDatos:
    return CifradorDatos(clave, "arcop")


def cifrador_arcop() -> CifradorDatos:
    if not settings.ENTITY_MAP_KEY:
        raise ClaveCifradoInvalida(
            "ENTITY_MAP_KEY no configurada: los textos ARCOP se guardan cifrados (HU-06) "
            "y sin clave no se pueden escribir."
        )
    return _cifrador(settings.ENTITY_MAP_KEY)


class TextoCifrado(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return cifrador_arcop().cifrar_texto(str(value))

    def process_result_value(self, value, dialect):
        if value is None or not CifradorDatos.esta_cifrado(value):
            return value
        try:
            return cifrador_arcop().descifrar_texto(value)
        except ClaveCifradoInvalida:
            # No se rompe el listado completo por una fila; el error queda en el log (sin el texto).
            logger.error("No se pudo descifrar un texto ARCOP (¿cambió ENTITY_MAP_KEY?)")
            return TEXTO_ILEGIBLE
