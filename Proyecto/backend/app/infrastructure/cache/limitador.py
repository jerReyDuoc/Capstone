"""
Contadores con ventana fija para los límites contra abuso de la encuesta pública (HU-19).

Implementación en Redis (el mismo que usa ARQ): cada clave es un contador que vence
solo. La creación es atómica (SET NX EX + INCR en una transacción), así dos peticiones
simultáneas no pueden pasarse del límite.

Las claves nunca llevan la IP en claro: quien llama pasa una huella HMAC (ver
app/api/dependencias/identificacion_cliente.py).

Si Redis no responde se lanza LimitadorNoDisponibleError y la ruta responde 503:
fallar "cerrado" es lo correcto aquí, porque fallar "abierto" dejaría crear
evaluaciones y gastar LLM sin límite justo cuando algo anda mal.

En las pruebas (tests/conftest.py) se usa LimitadorMemoria: mismo contrato, sin Redis.
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import settings
from app.domain.ports.limitador_port import Consumo, Limitador, LimitadorNoDisponibleError

logger = logging.getLogger(__name__)

_PREFIJO = "cai:lim:"

# Corrección 18-11 (falso "Estás respondiendo muy rápido"): antes `devolver` hacía DECR sin mirar si la clave
# seguía viva. Si la ventana ya había vencido (una respuesta de la IA que tarda 70 s contra una ventana de
# ráfaga de 60 s), Redis RECREABA la clave en -1 y SIN vencimiento; el SET NX EX de `consumir` ya no le ponía
# TTL y el contador "por minuto" quedaba para siempre: tras 6 preguntas en total, la cuenta recibía 429 en
# su primera pregunta de cualquier día. Ahora las dos operaciones son atómicas (Lua):
#   consumir: crea la clave con su ventana; si encuentra una SIN vencimiento (dañada por la versión anterior)
#             la reinicia con su ventana: las cuentas ya afectadas se reparan solas en su próxima consulta.
#   devolver: descuenta solo si la clave existe y es > 0 (DECR conserva el TTL); nunca crea claves.
_LUA_CONSUMIR = """
local reparada = 0
redis.call('SET', KEYS[1], 0, 'EX', ARGV[1], 'NX')
if redis.call('TTL', KEYS[1]) == -1 then
  redis.call('SET', KEYS[1], 0, 'EX', ARGV[1])
  reparada = 1
end
local usados = redis.call('INCR', KEYS[1])
return {usados, redis.call('TTL', KEYS[1]), reparada}
"""
_LUA_DEVOLVER = """
local v = tonumber(redis.call('GET', KEYS[1]) or '0')
if v > 0 then return redis.call('DECR', KEYS[1]) end
return 0
"""


def _resultado(usados: int, limite: int, ttl: int, ventana_s: int) -> Consumo:
    return Consumo(
        permitido=usados <= limite,
        usados=min(usados, limite),
        limite=limite,
        reintentar_en_s=max(1, ttl if ttl and ttl > 0 else ventana_s),
    )


class LimitadorRedis:
    def __init__(self, url: str):
        self._url = url
        self._redis = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _cliente(self):
        # El cliente queda atado al event loop que lo creó: si el loop cambia (otro
        # proceso de prueba, un asyncio.run nuevo) se crea uno nuevo en vez de fallar.
        loop = asyncio.get_running_loop()
        if self._redis is None or self._loop is not loop:
            from redis import asyncio as aioredis

            self._redis = aioredis.from_url(self._url, decode_responses=True, socket_timeout=2)
            self._loop = loop
        return self._redis

    async def consumir(self, clave: str, limite: int, ventana_s: int) -> Consumo:
        k = _PREFIJO + clave
        try:
            usados, ttl, reparada = await self._cliente().eval(_LUA_CONSUMIR, 1, k, int(ventana_s))
        except Exception as e:  # noqa: BLE001
            logger.error("Limitador Redis no disponible (%s)", type(e).__name__)
            raise LimitadorNoDisponibleError() from e
        if int(reparada):
            logger.warning("Limitador: la clave %s no tenía vencimiento; se reinició su ventana (%s s)", clave, ventana_s)
        return _resultado(int(usados), limite, int(ttl), ventana_s)

    async def devolver(self, clave: str) -> None:
        k = _PREFIJO + clave
        try:
            await self._cliente().eval(_LUA_DEVOLVER, 1, k)
        except Exception:  # noqa: BLE001  (devolver es "mejor esfuerzo")
            logger.warning("No se pudo devolver un consumo del limitador")

    async def usados(self, clave: str) -> int:
        try:
            valor = await self._cliente().get(_PREFIJO + clave)
        except Exception as e:  # noqa: BLE001
            raise LimitadorNoDisponibleError() from e
        return int(valor or 0)

    async def restante_s(self, clave: str) -> int:
        """HU-28: segundos que faltan para que la ventana de `clave` se reinicie (0 si no existe)."""
        try:
            ttl = await self._cliente().ttl(_PREFIJO + clave)
        except Exception as e:  # noqa: BLE001
            raise LimitadorNoDisponibleError() from e
        return max(0, int(ttl or 0))

    async def reiniciar(self, clave: str) -> None:
        """HU-28: borra el contador (p. ej. los fallos de una cuenta tras entrar bien)."""
        try:
            await self._cliente().delete(_PREFIJO + clave)
        except Exception:  # noqa: BLE001  (mejor esfuerzo, como devolver)
            logger.warning("No se pudo reiniciar un contador del limitador")


class LimitadorMemoria:
    """Mismo contrato que LimitadorRedis, en memoria del proceso (pruebas / desarrollo)."""

    def __init__(self):
        self._datos: dict[str, tuple[int, float]] = {}

    def _vigente(self, k: str) -> tuple[int, float] | None:
        fila = self._datos.get(k)
        if fila and fila[1] <= time.monotonic():
            self._datos.pop(k, None)
            return None
        return fila

    async def consumir(self, clave: str, limite: int, ventana_s: int) -> Consumo:
        ahora = time.monotonic()
        fila = self._vigente(clave)
        usados, vence = (fila[0] + 1, fila[1]) if fila else (1, ahora + ventana_s)
        self._datos[clave] = (usados, vence)
        return _resultado(usados, limite, int(vence - ahora), ventana_s)

    async def devolver(self, clave: str) -> None:
        fila = self._vigente(clave)
        if fila:
            self._datos[clave] = (max(0, fila[0] - 1), fila[1])

    async def usados(self, clave: str) -> int:
        fila = self._vigente(clave)
        return fila[0] if fila else 0

    async def restante_s(self, clave: str) -> int:
        fila = self._vigente(clave)
        return max(0, int(fila[1] - time.monotonic())) if fila else 0

    async def reiniciar(self, clave: str) -> None:
        self._datos.pop(clave, None)

    def limpiar(self) -> None:
        self._datos.clear()


_limitador: Limitador | None = None


def obtener_limitador() -> Limitador:
    """
    Dependencia FastAPI. Redis en la aplicación; en memoria con APP_ENV=test.
    tests/conftest.py instala uno en memoria NUEVO en cada prueba (aunque el .env diga
    development, como pasa en Docker), así las pruebas no tocan el Redis real ni
    acumulan contadores entre sí; las de HU-19 lo reemplazan con dependency_overrides.
    """
    global _limitador
    if _limitador is None:
        _limitador = LimitadorMemoria() if settings.APP_ENV == "test" else LimitadorRedis(settings.REDIS_URL)
    return _limitador
