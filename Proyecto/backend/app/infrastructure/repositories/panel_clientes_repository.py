"""Consultas de lectura del panel interno: evaluaciones con rubro, puntaje y empresa."""
from __future__ import annotations

from sqlalchemy import false as sa_false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.domain.ports.repositorios_admin import DatosEvaluacionPanel, PaginaEvaluacionesPanel


class PanelClientesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def datos_evaluacion(self, evaluacion_id: int) -> DatosEvaluacionPanel | None:
        db = self.session
        fila = (await db.execute(
            select(Evaluacion, Rubro.id, Rubro.nombre_rubro)
            .outerjoin(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
            .outerjoin(Rubro, UsuarioTemporal.rubro_id == Rubro.id)
            .where(Evaluacion.id == evaluacion_id)
        )).first()
        if fila is None:
            return None
        ev, rubro_id, rubro = fila
        puntaje = await db.scalar(select(func.avg(Resumen.puntaje_obtenido)).where(Resumen.evaluacion_id == ev.id))
        return DatosEvaluacionPanel(evaluacion=ev, rubro_id=rubro_id, rubro=rubro, puntaje=puntaje)

    async def listar_evaluaciones(self, *, estado: str | None, origen: str | None, empresa_id: int | None,
                                  incluir_prueba: bool, page: int, size: int) -> PaginaEvaluacionesPanel:
        db = self.session
        filtros = []
        if estado:
            filtros.append(Evaluacion.estado_progreso == estado)
        if origen:
            filtros.append(Evaluacion.origen == origen)
        if empresa_id is not None:
            filtros.append(Evaluacion.empresa_id == empresa_id)
        if not incluir_prueba:
            filtros.append(Evaluacion.es_prueba == sa_false())
        total = (await db.execute(select(func.count()).select_from(Evaluacion).where(*filtros))).scalar_one()
        puntaje = (
            select(Resumen.evaluacion_id, func.avg(Resumen.puntaje_obtenido).label("puntaje"))
            .group_by(Resumen.evaluacion_id).subquery()
        )
        filas = (await db.execute(
            select(Evaluacion, Rubro.nombre_rubro, Empresa.razon_social, puntaje.c.puntaje)
            .outerjoin(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
            .outerjoin(Rubro, UsuarioTemporal.rubro_id == Rubro.id)
            .outerjoin(Empresa, Evaluacion.empresa_id == Empresa.id)
            .outerjoin(puntaje, puntaje.c.evaluacion_id == Evaluacion.id)
            .where(*filtros)
            .order_by(Evaluacion.id.desc()).offset((page - 1) * size).limit(size)
        )).all()
        conteo = dict((await db.execute(
            select(Evaluacion.estado_progreso, func.count()).where(Evaluacion.es_prueba == sa_false())
            .group_by(Evaluacion.estado_progreso)
        )).all())
        return PaginaEvaluacionesPanel(
            filas=[DatosEvaluacionPanel(evaluacion=ev, rubro_id=None, rubro=rubro, puntaje=p,
                                        empresa_razon_social=razon) for ev, rubro, razon, p in filas],
            total=total, conteo_por_estado=conteo)

    async def obtener_empresa(self, empresa_id: int) -> Empresa | None:
        return await self.session.get(Empresa, empresa_id)
