"""
HU-24 · Acceso a BD de la matriz normativa versionada.

  - lee la versión publicada, el borrador y cualquier versión;
  - arma el contenido desde las tablas (cuando aún no hay ninguna versión guardada, p. ej.
    una BD nueva o la SQLite de las pruebas);
  - al publicar, APLICA el contenido a las tablas que usa el resto del sistema
    (matriz_controles, catalogo_brechas, ruta_formativa, preguntas_filtro y
    regla_aplicabilidad), dando id real a los elementos nuevos.

Nunca borra filas de catálogo: lo retirado queda con activo=false.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.matriz.contenido import CAMPOS, construir, copiar, normalizar, reglas_de
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.matriz_version import (
    ESTADO_BORRADOR, ESTADO_PUBLICADA, MatrizVersion, ReglaAplicabilidad,
)
from app.domain.models.pregunta_filtro import PreguntaFiltro
from app.domain.models.ruta_formativa import RutaFormativa

# entidad del contenido -> (modelo, columna de id, {campo del contenido: atributo del modelo})
_MAPEO = {
    "rutas": (RutaFormativa, "id", {k: k for k in CAMPOS["rutas"]} | {"activo": "activo"}),
    "brechas": (CatalogoBrechas, "id_brecha", {k: k for k in CAMPOS["brechas"]} | {"activo": "activo"}),
    "preguntas_filtro": (PreguntaFiltro, "id_pregunta",
                         {k: k for k in CAMPOS["preguntas_filtro"]} | {"activa": "activa"}),
    "controles": (MatrizControl, "id_control",
                  {k: ("catalogo_brechas_id_brecha" if k == "brecha_id" else k)
                   for k in CAMPOS["controles"] if k not in ("aplica_siempre", "filtros")} | {"activo": "activo"}),
}
_ORDEN_APLICAR = ("rutas", "brechas", "preguntas_filtro", "controles")


def _columnas(modelo) -> list[str]:
    return [c.key for c in modelo.__mapper__.column_attrs]


async def _filas(session: AsyncSession, modelo) -> list[dict]:
    objetos = (await session.execute(select(modelo))).scalars().all()
    cols = _columnas(modelo)
    return [{c: getattr(o, c) for c in cols} for o in objetos]


class MatrizRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ lectura
    async def publicada(self) -> MatrizVersion | None:
        return (await self.session.execute(
            select(MatrizVersion).where(MatrizVersion.estado == ESTADO_PUBLICADA)
        )).scalar_one_or_none()

    async def borrador(self) -> MatrizVersion | None:
        return (await self.session.execute(
            select(MatrizVersion).where(MatrizVersion.estado == ESTADO_BORRADOR)
        )).scalar_one_or_none()

    async def obtener(self, version_id: int) -> MatrizVersion | None:
        return await self.session.get(MatrizVersion, version_id)

    async def listar(self) -> list[MatrizVersion]:
        return list((await self.session.execute(
            select(MatrizVersion).order_by(MatrizVersion.id.desc())
        )).scalars().all())

    async def evaluaciones_por_version(self) -> dict[int, int]:
        filas = (await self.session.execute(
            select(Evaluacion.matriz_version_id, func.count())
            .where(Evaluacion.matriz_version_id.is_not(None))
            .group_by(Evaluacion.matriz_version_id)
        )).all()
        return {int(v): int(n) for v, n in filas}

    async def contenido_desde_tablas(self) -> dict:
        """El contenido tal como lo reflejan hoy las tablas (reglas de la BD o, si no hay, la semilla)."""
        reglas = [(r.control_id, r.pregunta_filtro_id) for r in
                  (await self.session.execute(select(ReglaAplicabilidad))).scalars().all()]
        controles = await _filas(self.session, MatrizControl)
        preguntas = await _filas(self.session, PreguntaFiltro)
        if not reglas:
            reglas, compuertas = _reglas_semilla(controles, preguntas)
            for p in preguntas:
                if p["codigo"] in compuertas:
                    p["es_compuerta"] = True
        return construir(
            dominios=await _filas(self.session, Dominio),
            rutas=await _filas(self.session, RutaFormativa),
            brechas=await _filas(self.session, CatalogoBrechas),
            controles=controles,
            preguntas=preguntas,
            reglas=reglas,
        )

    # ------------------------------------------------------------------ publicación
    async def aplicar(self, contenido: dict) -> dict:
        """
        Deja las tablas iguales al contenido y devuelve el contenido con los id reales.
        Lo que está en las tablas y no en el contenido se retira (activo=false).
        Debe correr dentro de la transacción de la publicación (no hace commit).
        """
        real = copiar(contenido)
        mapas: dict[str, dict[int, int]] = {e: {} for e in _ORDEN_APLICAR}

        def _ref(entidad: str, valor):
            if valor is None:
                return None
            return mapas[entidad].get(int(valor), int(valor))

        for entidad in _ORDEN_APLICAR:
            modelo, col_id, campos = _MAPEO[entidad]
            existentes = {getattr(o, col_id): o for o in
                          (await self.session.execute(select(modelo))).scalars().all()}
            vistos: set[int] = set()
            for item in real.get(entidad, []):
                # referencias a entidades ya aplicadas (ids negativos → reales)
                if entidad == "brechas":
                    item["ruta_formativa_id"] = _ref("rutas", item.get("ruta_formativa_id"))
                if entidad == "controles":
                    item["brecha_id"] = _ref("brechas", item.get("brecha_id"))
                    item["filtros"] = sorted({_ref("preguntas_filtro", f) for f in (item.get("filtros") or [])})
                valores = {attr: item.get(clave) for clave, attr in campos.items()}
                if entidad == "preguntas_filtro":
                    valores["es_compuerta"] = bool(item.get("es_compuerta"))
                temporal = int(item["id"])
                if temporal > 0 and temporal in existentes:
                    obj = existentes[temporal]
                    for attr, v in valores.items():
                        if getattr(obj, attr) != v:
                            setattr(obj, attr, v)
                    vistos.add(temporal)
                else:
                    obj = modelo(**valores)
                    self.session.add(obj)
                    await self.session.flush()
                    nuevo_id = int(getattr(obj, col_id))
                    mapas[entidad][temporal] = nuevo_id
                    item["id"] = nuevo_id
                    vistos.add(nuevo_id)
            # Lo que el contenido no menciona queda retirado (nunca se borra)
            clave_activo = "activa" if entidad == "preguntas_filtro" else "activo"
            for item_id, obj in existentes.items():
                if item_id not in vistos and getattr(obj, clave_activo):
                    setattr(obj, clave_activo, False)

        await self.session.execute(delete(ReglaAplicabilidad))
        for control_id, pregunta_id in reglas_de(real):
            self.session.add(ReglaAplicabilidad(control_id=control_id, pregunta_filtro_id=pregunta_id))
        await self.session.flush()
        return normalizar(real)


def _reglas_semilla(controles: list[dict], preguntas: list[dict]) -> tuple[list[tuple[int, int | None]], set[str]]:
    """El árbol fijo de control_tree.py traducido a ids (BD sin reglas guardadas)."""
    from app.application.filters.control_tree import ARBOL_POR_DEFECTO

    ids_control = {c["codigo_control"]: c["id_control"] for c in controles if c.get("codigo_control")}
    ids_pregunta = {p["codigo"]: p["id_pregunta"] for p in preguntas}
    reglas: list[tuple[int, int | None]] = [
        (ids_control[c], None) for c in sorted(ARBOL_POR_DEFECTO.base) if c in ids_control
    ]
    for filtro, codigos in sorted(ARBOL_POR_DEFECTO.por_filtro.items()):
        if filtro in ids_pregunta:
            reglas.extend((ids_control[c], ids_pregunta[filtro]) for c in sorted(codigos) if c in ids_control)
    return reglas, set(ARBOL_POR_DEFECTO.compuertas)
