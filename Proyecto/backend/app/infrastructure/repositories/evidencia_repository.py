from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.evidencia import Evidencia

class EvidenciaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, evidencia: Evidencia) -> Evidencia:
        self.session.add(evidencia)
        await self.session.commit()
        await self.session.refresh(evidencia)
        return evidencia

    async def get(self, evidencia_id: int) -> Evidencia | None:
        result = await self.session.execute(
            select(Evidencia).where(Evidencia.id_evidencia == evidencia_id)
        )
        return result.scalar_one_or_none()

    async def update(self, evidencia: Evidencia) -> Evidencia:
        await self.session.commit()
        await self.session.refresh(evidencia)
        return evidencia

    async def list_by_respuesta(self, respuesta_id: int) -> list[Evidencia]:
        result = await self.session.execute(
            select(Evidencia).where(Evidencia.respuesta_id == respuesta_id)
        )
        return list(result.scalars().all())