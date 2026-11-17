"""Mapa de datos: lectura del mapa, la vista completa y el dominio."""
from __future__ import annotations

from sqlalchemy import select

from app.application.mapa_datos.casos_uso.comun import _iso, elemento_de_fila, flujo_de_fila
from app.core.config import settings
from app.domain.catalogos import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis
from app.domain.mapa_datos.modelo import Elemento, Flujo
from app.domain.models.mapa_datos import MapaDatos, MapaElemento, MapaFlujo


class LecturaMixin:
    """Depende de los atributos que fija MapaDatosCasos.__init__ (db, actor, empresa_id, bitacora, ...)."""

    # ================================================================ lectura
    async def _mapa(self, bloquear: bool = False) -> MapaDatos | None:
        q = select(MapaDatos).where(MapaDatos.empresa_id == self.empresa_id)
        if bloquear:
            q = q.with_for_update()
        return (await self.db.execute(q)).scalar_one_or_none()

    async def _filas(self, mapa_id: int) -> tuple[list[MapaElemento], list[MapaFlujo]]:
        el = (await self.db.execute(
            select(MapaElemento).where(MapaElemento.mapa_id == mapa_id).order_by(MapaElemento.id))).scalars().all()
        fl = (await self.db.execute(
            select(MapaFlujo).where(MapaFlujo.mapa_id == mapa_id).order_by(MapaFlujo.id))).scalars().all()
        return list(el), list(fl)

    async def rubro(self) -> str | None:
        from app.domain.models.rubro import Rubro

        if self.rubro_id is None:
            return None
        return (await self.db.execute(select(Rubro.nombre_rubro).where(Rubro.id == self.rubro_id))).scalar_one_or_none()

    def _armar_vista(self, mapa: MapaDatos | None, el_filas: list[MapaElemento], fl_filas: list[MapaFlujo]) -> dict:
        els = [elemento_de_fila(r) for r in el_filas]
        fls = [flujo_de_fila(r) for r in fl_filas]
        por_id = {e.id: e for e in els}
        fechas_e = {r.id: (r.fecha_creacion, r.fecha_actualizacion) for r in el_filas}
        fechas_f = {r.id: (r.fecha_creacion, r.fecha_actualizacion) for r in fl_filas}
        hall = analisis.hallazgos(els, fls)
        return {
            "mapa": {
                "version": mapa.version if mapa else 0,
                "fecha_actualizacion": _iso(mapa.fecha_actualizacion) if mapa and mapa.version else None,
                "iniciado": bool(els),
                "plantilla_inicial": mapa.plantilla_inicial if mapa else None,
            },
            "elementos": [
                {**e.como_dict(), "incluye_nna": e.incluye_nna,
                 "fecha_creacion": _iso(fechas_e[e.id][0]), "fecha_actualizacion": _iso(fechas_e[e.id][1]),
                 "derivados": analisis.derivados_elemento(e, fls)}
                for e in els
            ],
            "flujos": [
                {**f.como_dict(), "incluye_nna": f.incluye_nna,
                 "fecha_creacion": _iso(fechas_f[f.id][0]), "fecha_actualizacion": _iso(fechas_f[f.id][1]),
                 "derivados": analisis.derivados_flujo(f, por_id).como_dict()}
                for f in fls
            ],
            "resumen": analisis.resumen(els, fls),
            "hallazgos": [h.como_dict() for h in hall],
            "conteo_hallazgos": analisis.contar_hallazgos(hall),
            "completitud": analisis.completitud(els, fls),
            "limites": {"max_elementos": settings.MAPA_MAX_ELEMENTOS, "max_flujos": settings.MAPA_MAX_FLUJOS},
            "catalogo_version": cat.VERSION_CATALOGO,
        }

    async def vista(self) -> dict:
        mapa = await self._mapa()
        el, fl = await self._filas(mapa.id) if mapa else ([], [])
        return self._armar_vista(mapa, el, fl)

    async def dominio(self) -> tuple[MapaDatos | None, list[Elemento], list[Flujo]]:
        mapa = await self._mapa()
        el, fl = await self._filas(mapa.id) if mapa else ([], [])
        return mapa, [elemento_de_fila(r) for r in el], [flujo_de_fila(r) for r in fl]
