"""HU-16 · Consultas y escrituras de los borradores de documentos (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.borrador_modelo import BorradorDocumento, EstadoBorrador
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.rubro import Rubro


class BorradoresRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def borrador(self, borrador_id: int) -> Any | None:
        return await self.session.get(BorradorDocumento, borrador_id)

    async def listar(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(BorradorDocumento).where(BorradorDocumento.empresa_id == empresa_id)
            .order_by(BorradorDocumento.fecha_actualizacion.desc(), BorradorDocumento.id.desc())
        )).scalars().all())

    async def contar_en_revision(self, empresa_id: int) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(BorradorDocumento).where(
                BorradorDocumento.empresa_id == empresa_id,
                BorradorDocumento.estado == EstadoBorrador.EN_REVISION.value)
        ) or 0

    async def fuentes_de_controles(self, codigos: list[str]) -> list[tuple]:
        return list((await self.session.execute(
            select(MatrizControl.codigo_control, MatrizControl.framework_fuente, MatrizControl.articulo_referencia)
            .where(MatrizControl.codigo_control.in_(sorted(codigos)))
        )).all())

    async def rubro(self, rubro_id: int) -> Any | None:
        return await self.session.get(Rubro, rubro_id)

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)

    async def eliminar(self, entidad: Any) -> None:
        await self.session.delete(entidad)
