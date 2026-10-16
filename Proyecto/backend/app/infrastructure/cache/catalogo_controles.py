"""
Caché en memoria del catálogo de controles (matriz_controles + dominio + brecha).

Por qué (HU-01, C4 < 500 ms): GET /evaluaciones/{id}/controles-aplicables cargaba en
cada petición los ~40 controles como entidades ORM, con 3 consultas extra por las
relaciones lazy="selectin" (dominio, brecha y su ruta formativa), y luego validaba
cada uno con Pydantic. Con 10 usuarios simultáneos era el endpoint más lento
(p95 542 ms en el reporte live del 11-oct).

El catálogo es dato semilla (lo cambian las migraciones, no los usuarios), así que
se carga una vez, se serializa con el MISMO esquema ControlResponse y se guarda:
  * el dict de cada control (para armar listas y el progreso), y
  * el JSON ya codificado de cada combinación de controles aplicables (el filtro
    F2–F7 da como máximo 64 combinaciones).

La caché expira cada CATALOGO_TTL_SEGUNDOS y se puede invalidar a mano con
`invalidar()` (p.ej. el futuro mantenedor de la matriz, HU-24). Cada proceso de
uvicorn tiene su propia copia.
"""
import json
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.api_schemas import ControlResponse
from app.domain.models.matriz_control import MatrizControl

CATALOGO_TTL_SEGUNDOS = 300.0


@dataclass(frozen=True)
class ControlCatalogo:
    id_control: int
    codigo_control: str
    dominio_id: int | None
    dominio: str | None
    datos: dict            # ControlResponse serializado (modo JSON)


class _Catalogo:
    def __init__(self, controles: list[ControlCatalogo]):
        self.cargado_en = time.monotonic()
        self.por_codigo = {c.codigo_control: c for c in controles}
        self.por_id = {c.id_control: c for c in controles}
        self._json: dict[tuple[str, ...], bytes] = {}

    def json_de(self, codigos: tuple[str, ...]) -> bytes:
        cuerpo = self._json.get(codigos)
        if cuerpo is None:
            datos = [self.por_codigo[c].datos for c in codigos if c in self.por_codigo]
            cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._json[codigos] = cuerpo
        return cuerpo


_catalogo: _Catalogo | None = None


def invalidar() -> None:
    """Fuerza a recargar el catálogo en la próxima petición."""
    global _catalogo
    _catalogo = None


def _vigente() -> _Catalogo | None:
    c = _catalogo
    if c is not None and time.monotonic() - c.cargado_en < CATALOGO_TTL_SEGUNDOS:
        return c
    return None


async def obtener(session: AsyncSession) -> _Catalogo:
    global _catalogo
    c = _vigente()
    if c is not None:
        return c
    # Sin candado a propósito: si llegan varias peticiones con la caché vacía, cada
    # una carga el catálogo (idempotente) y la última reemplaza a las demás.
    result = await session.execute(select(MatrizControl).order_by(MatrizControl.codigo_control))
    controles = []
    for m in result.scalars().all():
        if not m.codigo_control:
            continue
        controles.append(ControlCatalogo(
            id_control=m.id_control,
            codigo_control=m.codigo_control,
            dominio_id=m.dominio_id,
            dominio=m.dominio.nombre_dominio if m.dominio else None,
            datos=ControlResponse.model_validate(m).model_dump(mode="json"),
        ))
    _catalogo = _Catalogo(controles)
    return _catalogo


async def json_controles(session: AsyncSession, codigos: list[str]) -> bytes:
    """Lista JSON (ControlResponse) de los controles indicados, en ese orden."""
    return (await obtener(session)).json_de(tuple(codigos))
