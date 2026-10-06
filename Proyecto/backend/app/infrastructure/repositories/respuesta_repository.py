from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.respuesta import Respuesta
from app.domain.models.matriz_control import MatrizControl

class RespuestaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, respuesta: Respuesta) -> Respuesta:
        self.session.add(respuesta)
        await self.session.commit()
        await self.session.refresh(respuesta)
        return respuesta

    async def get(self, respuesta_id: int) -> Respuesta | None:
        result = await self.session.execute(
            select(Respuesta)
            .options(selectinload(Respuesta.evidencias))
            .where(Respuesta.id == respuesta_id)
        )
        return result.scalar_one_or_none()

    async def update(self, respuesta: Respuesta) -> Respuesta:
        await self.session.commit()
        await self.session.refresh(respuesta)
        return respuesta

    async def get_control(self, control_id: int) -> MatrizControl | None:
        result = await self.session.execute(
            select(MatrizControl).where(MatrizControl.id_control == control_id)
        )
        return result.scalar_one_or_none()