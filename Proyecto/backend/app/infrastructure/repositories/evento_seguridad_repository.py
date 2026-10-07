from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.models.evento_seguridad import EventoSeguridad


class EventoSeguridadRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, evento: EventoSeguridad) -> EventoSeguridad:
        self.session.add(evento)
        await self.session.commit()
        await self.session.refresh(evento)
        return evento

    async def get(self, evento_id: int) -> EventoSeguridad | None:
        return await self.session.get(EventoSeguridad, evento_id)

    async def list(self, solo_pendientes: bool = False, limit: int = 100) -> list[EventoSeguridad]:
        q = select(EventoSeguridad).order_by(EventoSeguridad.fecha.desc()).limit(limit)
        if solo_pendientes:
            q = q.where(EventoSeguridad.revisado.is_(False))
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update(self, evento: EventoSeguridad) -> EventoSeguridad:
        await self.session.commit()
        await self.session.refresh(evento)
        return evento
