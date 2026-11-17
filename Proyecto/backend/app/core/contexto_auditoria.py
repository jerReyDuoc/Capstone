"""
HU-09 · Origen (IP) de cada registro del audit_log.

El criterio 2 exige la IP en TODO registro. Para no pasar la IP a mano por los ~40 lugares
que registran acciones, un middleware ASGI
(app/api/middleware/fijar_ip_auditoria.py) la deja en una variable de contexto al comenzar
cada petición y `BitacoraRepository.registrar()` la toma de ahí.

  - Petición HTTP: la IP del visitante, calculada igual que en el resto de la API
    (app/api/dependencias/identificacion_cliente.py): la que reenvía el BFF de Next.js en `X-Cliente-IP` si trae el
    `X-BFF-Secret` correcto, o la de la conexión. Se valida y normaliza con `ipaddress`
    (un encabezado con otra cosa nunca llega al log).
  - Fuera de una petición (worker de ARQ, scripts): "sistema:worker" o "sistema:cli".
    Los procesos fijan su origen al arrancar con `fijar_origen_por_defecto()`.

La IP es un dato personal: solo se guarda en audit_log (excepción documentada en el
catálogo de datos personales de T-06). Los límites de intentos siguen usando su huella.
"""
from __future__ import annotations

import contextvars
import ipaddress
from contextvars import ContextVar

ORIGEN_WORKER = "sistema:worker"
ORIGEN_CLI = "sistema:cli"
ORIGEN_INTERNO = "sistema:interno"
IP_DESCONOCIDA = "desconocida"

_ip_actual: ContextVar[str | None] = ContextVar("audit_ip_actual", default=None)
_origen_por_defecto = ORIGEN_INTERNO


def normalizar_ip(valor: str | None) -> str:
    """IPv4/IPv6 normalizada (IPv4 mapeada a IPv6 -> IPv4); cualquier otra cosa -> 'desconocida'."""
    texto = (valor or "").strip()
    if not texto:
        return IP_DESCONOCIDA
    try:
        ip = ipaddress.ip_address(texto.split("%", 1)[0])  # sin zona de enlace local (fe80::1%eth0)
    except ValueError:
        return IP_DESCONOCIDA
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.compressed


def fijar_origen_por_defecto(origen: str) -> None:
    """Origen de los registros hechos fuera de una petición HTTP (worker, CLI)."""
    global _origen_por_defecto
    _origen_por_defecto = origen


def ip_actual() -> str:
    return _ip_actual.get() or _origen_por_defecto


def fijar_ip_peticion(ip: str | None) -> contextvars.Token:
    """Fija la IP (ya normalizada con normalizar_ip) de la petición en curso."""
    return _ip_actual.set(normalizar_ip(ip))


def restablecer_ip_peticion(token: contextvars.Token) -> None:
    _ip_actual.reset(token)
