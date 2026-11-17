"""Adaptador de `ConsultaEvaluacionesPort`: lecturas de evaluaciones y respuestas (A-41)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evaluacion import ORIGEN_EMPRESA, ORIGEN_PUBLICA, Evaluacion
from app.domain.models.respuesta import Respuesta
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.ports.repositorios_consultas import (
    ALCANCE_EMPRESA,
    ALCANCE_EVALUACION,
    ALCANCE_REFERENTE,
    ALCANCE_SIN_PUBLICAS,
    ALCANCE_TODO,
    AlcanceEvaluaciones,
)


def _filtro_alcance(alcance: AlcanceEvaluaciones):
    if alcance.tipo == ALCANCE_SIN_PUBLICAS:
        return Evaluacion.origen.not_in((ORIGEN_PUBLICA, ORIGEN_EMPRESA))
    if alcance.tipo == ALCANCE_EVALUACION:
        return Evaluacion.id == alcance.valor
    if alcance.tipo == ALCANCE_REFERENTE:
        return (Evaluacion.usuario_temporal_id == alcance.valor) & (Evaluacion.origen != ORIGEN_PUBLICA)
    if alcance.tipo == ALCANCE_EMPRESA:
        return (Evaluacion.empresa_id == alcance.valor) if alcance.valor is not None else (Evaluacion.id == -1)
    if alcance.tipo == ALCANCE_TODO:
        return None
    return Evaluacion.id == -1  # nunca "todo" por omisión


class ConsultaEvaluacionesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def empresa_del_usuario_definitivo(self, usuario_id: int) -> int | None:
        return await self.session.scalar(select(UsuarioDefinitivo.empresa_id).where(UsuarioDefinitivo.id == usuario_id))

    async def listar_evaluaciones(self, *, alcance: AlcanceEvaluaciones, estado_progreso: str | None,
                                  offset: int, limit: int) -> tuple[list[Evaluacion], int]:
        query = select(Evaluacion).order_by(Evaluacion.id.desc())
        count_query = select(func.count()).select_from(Evaluacion)
        if estado_progreso:
            query = query.where(Evaluacion.estado_progreso == estado_progreso)
            count_query = count_query.where(Evaluacion.estado_progreso == estado_progreso)
        filtro = _filtro_alcance(alcance)
        if filtro is not None:
            query = query.where(filtro)
            count_query = count_query.where(filtro)
        total = (await self.session.execute(count_query)).scalar() or 0
        result = await self.session.execute(query.offset(offset).limit(limit))
        return list(result.scalars().all()), total

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        result = await self.session.execute(select(Evaluacion).where(Evaluacion.id == evaluacion_id))
        return result.scalar_one_or_none()

    async def existe_evaluacion(self, evaluacion_id: int) -> bool:
        r = await self.session.execute(
            select(func.count()).select_from(Evaluacion).where(Evaluacion.id == evaluacion_id)
        )
        return (r.scalar() or 0) > 0

    async def listar_respuestas(self, evaluacion_id: int, *, estado_final: str | None, fuente: str | None,
                                offset: int, limit: int) -> tuple[list[Respuesta], int]:
        query = select(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id).order_by(Respuesta.id.desc())
        count_query = select(func.count()).select_from(Respuesta).where(Respuesta.evaluacion_id == evaluacion_id)
        if estado_final:
            query = query.where(Respuesta.estado_clasificacion_final == estado_final)
            count_query = count_query.where(Respuesta.estado_clasificacion_final == estado_final)
        if fuente:
            query = query.where(Respuesta.fuente_clasificacion == fuente)
            count_query = count_query.where(Respuesta.fuente_clasificacion == fuente)
        total = (await self.session.execute(count_query)).scalar() or 0
        result = await self.session.execute(query.offset(offset).limit(limit))
        return list(result.scalars().all()), total
