from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.pregunta_filtro import PreguntaFiltro


class PreguntaFiltroRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_activas(self) -> list[PreguntaFiltro]:
        result = await self.session.execute(
            select(PreguntaFiltro)
            .where(PreguntaFiltro.activa == True)  # noqa: E712
            .order_by(PreguntaFiltro.orden)
        )
        return list(result.scalars().all())

    async def get_by_codigo(self, codigo: str) -> PreguntaFiltro | None:
        result = await self.session.execute(
            select(PreguntaFiltro).where(PreguntaFiltro.codigo == codigo)
        )
        return result.scalar_one_or_none()