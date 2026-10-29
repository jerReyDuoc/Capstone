"""
HU-15 · Persistencia de las conversaciones del Agente IA Tutor.

Toda consulta de una conversación filtra por `empresa_id`: una empresa nunca ve (ni
sabe si existe) la conversación de otra. Los mensajes se borran explícitamente antes que
su conversación (SQLite de las pruebas no aplica ON DELETE CASCADE por defecto).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.tutor import ConversacionTutor, MensajeTutor


class TutorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ conversaciones
    async def obtener(self, conversacion_id: int, empresa_id: int) -> ConversacionTutor | None:
        return (await self.session.execute(
            select(ConversacionTutor).where(ConversacionTutor.id == conversacion_id,
                                            ConversacionTutor.empresa_id == empresa_id)
        )).scalar_one_or_none()

    async def listar(self, empresa_id: int, limite: int = 50) -> list[ConversacionTutor]:
        return list((await self.session.execute(
            select(ConversacionTutor).where(ConversacionTutor.empresa_id == empresa_id)
            .order_by(ConversacionTutor.fecha_ultimo_mensaje.desc(), ConversacionTutor.id.desc()).limit(limite)
        )).scalars().all())

    async def contar(self, empresa_id: int) -> int:
        return int(await self.session.scalar(
            select(func.count()).select_from(ConversacionTutor).where(ConversacionTutor.empresa_id == empresa_id)
        ) or 0)

    def agregar(self, fila) -> None:
        self.session.add(fila)

    # ------------------------------------------------------------------ mensajes
    async def mensajes(self, conversacion_id: int) -> list[MensajeTutor]:
        return list((await self.session.execute(
            select(MensajeTutor).where(MensajeTutor.conversacion_id == conversacion_id)
            .order_by(MensajeTutor.fecha, MensajeTutor.id)
        )).scalars().all())

    async def historial(self, conversacion_id: int, n: int) -> list[MensajeTutor]:
        """Últimos `n` mensajes NO bloqueados (texto ya anonimizado), del más antiguo al más nuevo."""
        if n <= 0:
            return []
        filas = (await self.session.execute(
            select(MensajeTutor)
            .where(MensajeTutor.conversacion_id == conversacion_id, MensajeTutor.bloqueado.is_(False))
            .order_by(MensajeTutor.fecha.desc(), MensajeTutor.id.desc()).limit(n)
        )).scalars().all()
        return list(reversed(filas))

    # ------------------------------------------------------------------ borrado
    async def _borrar(self, ids_conversaciones) -> int:
        await self.session.execute(
            delete(MensajeTutor).where(MensajeTutor.conversacion_id.in_(ids_conversaciones))
            .execution_options(synchronize_session=False))
        res = await self.session.execute(
            delete(ConversacionTutor).where(ConversacionTutor.id.in_(ids_conversaciones))
            .execution_options(synchronize_session=False))
        return res.rowcount or 0

    async def eliminar(self, conversacion_id: int) -> int:
        return await self._borrar([conversacion_id])

    async def eliminar_de_usuario(self, usuario_definitivo_id: int) -> int:
        """Supresión ARCOP del usuario definitivo: TODAS sus conversaciones."""
        ids = list((await self.session.execute(
            select(ConversacionTutor.id).where(ConversacionTutor.usuario_definitivo_id == usuario_definitivo_id)
        )).scalars().all())
        return await self.eliminar_ids(ids)

    async def inactivas_desde(self, limite: datetime) -> list[int]:
        return list((await self.session.execute(
            select(ConversacionTutor.id).where(ConversacionTutor.fecha_ultimo_mensaje < limite)
            .order_by(ConversacionTutor.id)
        )).scalars().all())

    async def eliminar_ids(self, ids: list[int]) -> int:
        return await self._borrar(ids) if ids else 0
