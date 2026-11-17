"""Repositorio de las evaluaciones de la empresa cliente: historial y reevaluación (HU-29)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import ESTADOS_CERRADOS, ORIGEN_EMPRESA, Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.usuario_temporal import UsuarioTemporal


class HistorialEmpresaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def evaluacion_mas_reciente(self, empresa_id: int, solo_completadas: bool) -> int | None:
        q = select(Evaluacion.id).where(
            Evaluacion.empresa_id == empresa_id, Evaluacion.id.in_(select(Resumen.evaluacion_id))
        )
        if solo_completadas:
            q = q.where(Evaluacion.estado_progreso.in_(ESTADOS_CERRADOS))
        return await self.session.scalar(q.order_by(Evaluacion.id.desc()).limit(1))

    async def evaluacion_en_curso(self, empresa_id: int) -> Evaluacion | None:
        return await self.session.scalar(
            select(Evaluacion).where(
                Evaluacion.empresa_id == empresa_id,
                Evaluacion.origen == ORIGEN_EMPRESA,
                Evaluacion.estado_progreso.not_in(ESTADOS_CERRADOS),
            ).order_by(Evaluacion.id.desc()).limit(1)
        )

    async def rubro_de_empresa(self, empresa_id: int) -> int | None:
        return await self.session.scalar(select(Empresa.rubro_id).where(Empresa.id == empresa_id))

    async def rubro_de_usuario_temporal(self, usuario_temporal_id: int) -> int | None:
        return await self.session.scalar(
            select(UsuarioTemporal.rubro_id).where(UsuarioTemporal.id == usuario_temporal_id))

    async def evaluaciones_de_empresa(self, empresa_id: int) -> list[Evaluacion]:
        filas = (await self.session.execute(
            select(Evaluacion).where(Evaluacion.empresa_id == empresa_id).order_by(Evaluacion.id)
        )).scalars().all()
        return list(filas)

    async def resumenes_con_dominio(self, evaluaciones_ids: list[int]) -> list[tuple[Resumen, Dominio]]:
        filas = (await self.session.execute(
            select(Resumen, Dominio).join(Dominio, Resumen.dominio_id == Dominio.id)
            .where(Resumen.evaluacion_id.in_(evaluaciones_ids))
        )).all()
        return [(r, d) for r, d in filas]

    async def bloquear_empresa(self, empresa_id: int) -> None:
        await self.session.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

    def agregar_evaluacion(self, evaluacion: Evaluacion) -> None:
        self.session.add(evaluacion)
