"""Consultas del espacio de la empresa del usuario definitivo (HU-28/29/30)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.formacion import AvanceFormativo
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.usuario_definitivo import UsuarioDefinitivo


class EspacioEmpresaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def empresa_de_usuario(self, usuario_id: int) -> Any | None:
        usuario = await self.session.get(UsuarioDefinitivo, usuario_id)
        return await self.session.get(Empresa, usuario.empresa_id) if usuario else None

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        return await self.session.scalar(select(Rubro.nombre_rubro).where(Rubro.id == rubro_id))

    async def evaluaciones_con_puntaje(self, empresa_id: int) -> list[tuple[Any, float | None]]:
        puntaje = (
            select(Resumen.evaluacion_id, func.avg(Resumen.puntaje_obtenido).label("puntaje"))
            .group_by(Resumen.evaluacion_id).subquery()
        )
        return (await self.session.execute(
            select(Evaluacion, puntaje.c.puntaje)
            .outerjoin(puntaje, puntaje.c.evaluacion_id == Evaluacion.id)
            .where(Evaluacion.empresa_id == empresa_id)
            .order_by(Evaluacion.id.desc())  # HU-29: la más reciente primero (ver historial_empresa.py)
        )).all()

    async def avances_con_constancia(self, empresa_id: int) -> list[tuple[Any, str | None]]:
        return (await self.session.execute(
            select(AvanceFormativo, RutaFormativa.nombre)
            .join(RutaFormativa, RutaFormativa.id == AvanceFormativo.ruta_formativa_id)
            .where(AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.codigo_constancia.is_not(None))
            .order_by(AvanceFormativo.fecha_completado.desc())
        )).all()
