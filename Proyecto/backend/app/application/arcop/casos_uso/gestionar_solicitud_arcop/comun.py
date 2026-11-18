"""Constantes, errores y utilidades compartidas del ciclo de vida de solicitudes ARCOP."""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.domain.calendario import sumar_dias_habiles

from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    SolicitudARCOP,
)

logger = logging.getLogger("arcop")

MIN_DESCRIPCION, MAX_DESCRIPCION = 10, 5000
MAX_COMENTARIO = 2000
MIN_RESPUESTA, MAX_RESPUESTA = 10, 10000

# Estados que admin_therion fija con PATCH /estado. Los finales tienen su propio
# endpoint (resolución / cancelación) porque exigen datos adicionales.
ESTADOS_GESTION = {
    Estado.EN_REVISION.value,
    Estado.PENDIENTE_INFORMACION.value,
    Estado.EN_PROCESO.value,
}
RESULTADOS_RESOLUCION = {Estado.RESUELTA.value, Estado.RECHAZADA.value}


class SolicitudNoEncontradaError(Exception):
    pass


class OperacionNoPermitidaError(Exception):
    pass


class TransicionInvalidaError(Exception):
    def __init__(self, actual: str, nuevo: str, mensaje: str | None = None):
        self.actual, self.nuevo = actual, nuevo
        super().__init__(mensaje or f"No se puede pasar de '{actual}' a '{nuevo}'.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _texto(valor: str | None, campo: str, minimo: int = 0, maximo: int = MAX_COMENTARIO,
           obligatorio: bool = False) -> str | None:
    texto = (valor or "").strip()
    if not texto:
        if obligatorio:
            raise ValueError(f"El campo '{campo}' es obligatorio.")
        return None
    if len(texto) < minimo:
        raise ValueError(f"El campo '{campo}' debe tener al menos {minimo} caracteres.")
    if len(texto) > maximo:
        raise ValueError(f"El campo '{campo}' no puede superar {maximo} caracteres.")
    return texto


def plazo_vencido(solicitud: SolicitudARCOP, ahora: datetime | None = None) -> bool:
    """True si la solicitud sigue abierta y pasó alguno de sus plazos."""
    if solicitud.estado in Estado.finales():
        return False
    ahora = ahora or _ahora()
    if solicitud.fecha_limite_respuesta and solicitud.fecha_limite_respuesta < ahora:
        return True
    return bool(
        solicitud.estado == Estado.PENDIENTE_INFORMACION.value
        and solicitud.fecha_limite_informacion
        and solicitud.fecha_limite_informacion < ahora
    )


def _sumar_dias(desde: datetime, dias: int | None) -> datetime | None:
    """Días CORRIDOS. None o 0 = sin plazo."""
    return desde + timedelta(days=dias) if dias else None


def _sumar_dias_habiles(desde: datetime, dias: int | None, feriados=None) -> datetime | None:
    """
    Días HÁBILES: lunes a viernes, descontando los feriados de Chile (settings.FERIADOS_CL).
    Wrapper de la función pura app/domain/calendario.sumar_dias_habiles; inyecta el calendario.
    Un año sin feriados cargados avisa (una vez) y cuenta solo fines de semana.
    """
    if not dias:
        return None
    return sumar_dias_habiles(desde, dias, settings.FERIADOS_CL if feriados is None else feriados)


_ALFABETO_CODIGO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32 (sin I, L, O, U)
_TRADUCCION_CODIGO = str.maketrans({"O": "0", "I": "1", "L": "1"})


def nuevo_codigo_seguimiento() -> str:
    """ARC-XXXX-XXXX: 8 caracteres al azar (40 bits). No revela el id ni el orden."""
    c = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(8))
    return f"ARC-{c[:4]}-{c[4:]}"


def normalizar_codigo(codigo: str) -> str:
    """Acepta minúsculas, espacios, sin guiones y confusiones O/0, I/L/1."""
    limpio = "".join(ch for ch in (codigo or "").upper() if ch.isalnum()).translate(_TRADUCCION_CODIGO)
    if limpio.startswith("ARC"):
        limpio = limpio[3:]
    if len(limpio) != 8:
        return ""
    return f"ARC-{limpio[:4]}-{limpio[4:]}"
