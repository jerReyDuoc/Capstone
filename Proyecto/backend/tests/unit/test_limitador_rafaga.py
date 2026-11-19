"""
Corrección 18-11 · falso "Estás respondiendo muy rápido" (ASISTENTE_RAFAGA).

Causa: `LimitadorRedis.devolver` hacía DECR sobre una clave ya vencida; Redis la recreaba SIN vencimiento y el
contador "por minuto" quedaba para siempre. Las pruebas de Redis necesitan un Redis real (se omiten si no hay):
    docker compose exec api pytest tests/unit/test_limitador_rafaga.py
"""
import asyncio
import os
import time
import uuid
from types import SimpleNamespace

import pytest

from app.application.rat.casos_uso.asistente_rat.sesion_asistente import SesionMixin
from app.infrastructure.cache.limitador import _PREFIJO, LimitadorMemoria, LimitadorRedis

URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")


def _redis_disponible() -> bool:
    async def ping():
        from redis import asyncio as aioredis

        r = aioredis.from_url(URL, socket_timeout=1)
        try:
            return bool(await r.ping())
        finally:
            await r.aclose()

    try:
        return asyncio.run(ping())
    except Exception:  # noqa: BLE001
        return False


requiere_redis = pytest.mark.skipif(not _redis_disponible(), reason="sin Redis disponible")


def _clave() -> str:
    return f"prueba:rafaga:{uuid.uuid4().hex}"


@requiere_redis
def test_devolver_despues_de_vencida_la_ventana_no_deja_la_clave_sin_vencimiento():
    async def caso():
        lim, clave = LimitadorRedis(URL), _clave()
        await lim.consumir(clave, 6, 1)
        await asyncio.sleep(1.5)          # la ventana venció (la IA tardó más que la ventana)
        await lim.devolver(clave)         # antes: DECR recreaba la clave en -1 sin TTL
        r = lim._cliente()
        existe = await r.exists(_PREFIJO + clave)
        await r.delete(_PREFIJO + clave)
        return existe

    assert asyncio.run(caso()) == 0


@requiere_redis
def test_consumir_repara_una_clave_danada_sin_vencimiento():
    async def caso():
        lim, clave = LimitadorRedis(URL), _clave()
        r = lim._cliente()
        await r.set(_PREFIJO + clave, 99)            # como la dejaba la versión anterior: sin TTL, contador alto
        consumo = await lim.consumir(clave, 6, 60)
        ttl = await r.ttl(_PREFIJO + clave)
        await r.delete(_PREFIJO + clave)
        return consumo, ttl

    consumo, ttl = asyncio.run(caso())
    assert consumo.permitido and consumo.usados == 1
    assert 0 < ttl <= 60


@requiere_redis
def test_devolver_no_baja_de_cero_y_conserva_el_vencimiento():
    async def caso():
        lim, clave = LimitadorRedis(URL), _clave()
        await lim.consumir(clave, 6, 60)
        await lim.devolver(clave)
        await lim.devolver(clave)
        r = lim._cliente()
        valor, ttl = await r.get(_PREFIJO + clave), await r.ttl(_PREFIJO + clave)
        await r.delete(_PREFIJO + clave)
        return valor, ttl

    valor, ttl = asyncio.run(caso())
    assert int(valor) == 0 and 0 < ttl <= 60


def test_memoria_tiene_el_mismo_contrato_tras_vencer():
    async def caso():
        lim, clave = LimitadorMemoria(), _clave()
        await lim.consumir(clave, 6, 1)
        lim._datos[clave] = (1, time.monotonic() - 1)   # vencida
        await lim.devolver(clave)
        return await lim.usados(clave)

    assert asyncio.run(caso()) == 0


def test_la_rafaga_es_por_usuario_y_no_solo_por_empresa():
    a = SimpleNamespace(empresa_id=7, usuario_id=1)
    b = SimpleNamespace(empresa_id=7, usuario_id=2)
    assert SesionMixin._clave_rafaga(a) == "asistente:min:7:1"
    assert SesionMixin._clave_rafaga(a) != SesionMixin._clave_rafaga(b)
