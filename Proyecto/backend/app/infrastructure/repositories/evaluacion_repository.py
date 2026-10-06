from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.evaluacion import Evaluacion

class EvaluacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, evaluacion_id: int) -> Evaluacion | None:
        result = await self.session.execute(
            select(Evaluacion).where(Evaluacion.id == evaluacion_id)
        )
        return result.scalar_one_or_none()