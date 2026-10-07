from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.respuesta_filtro import RespuestaFiltro


class RespuestaFiltroRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_create(self, respuestas: list[RespuestaFiltro]) -> list[RespuestaFiltro]:
        for r in respuestas:
            self.session.add(r)
        await self.session.commit()
        return respuestas

    async def list_by_evaluacion(self, evaluacion_id: int) -> list[RespuestaFiltro]:
        result = await self.session.execute(
            select(RespuestaFiltro)
            .options(selectinload(RespuestaFiltro.pregunta))
            .where(RespuestaFiltro.evaluacion_id == evaluacion_id)
            .order_by(RespuestaFiltro.id_respuesta_filtro)
        )
        return list(result.scalars().all())

    async def delete_by_evaluacion(self, evaluacion_id: int) -> None:
        respuestas = await self.list_by_evaluacion(evaluacion_id)
        for r in respuestas:
            await self.session.delete(r)
        await self.session.commit()